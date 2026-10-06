"""Atomic source replacement and exact PostgreSQL hybrid retrieval."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from pgvector import Vector
from sqlalchemy import Connection, Engine, delete, func, literal_column, select, text

from agent_reliability_runtime.persistence.schema import (
    knowledge_chunks as chunks,
)
from agent_reliability_runtime.persistence.schema import (
    knowledge_documents as documents,
)
from agent_reliability_runtime.providers.contracts import (
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
)
from agent_reliability_runtime.retrieval.contracts import Evidence
from agent_reliability_runtime.retrieval.text import SourcePlan

DIMENSION = 1024
LANE_LIMIT = 20
FINAL_LIMIT = 6
RRF_K = 60


def validated_vectors(
    result: EmbeddingResult, count: int
) -> tuple[tuple[float, ...], ...]:
    # Revalidate even a model_construct/mutated provider snapshot before DB mutation.
    checked = EmbeddingResult.model_validate(result.model_dump())
    if checked.dimension != DIMENSION or len(checked.vectors) != count:
        raise ValueError("retrieval requires one 1024-d vector per input")
    converted = []
    for vector in checked.vectors:
        if not all(
            math.isfinite(x) and abs(x) <= 3.4028234663852886e38 for x in vector
        ):
            raise ValueError("retrieval requires finite float32 vectors")
        stored = Vector(list(vector)).to_list()
        if not any(stored):
            raise ValueError("cosine retrieval requires nonzero vectors")
        converted.append(tuple(stored))
    return tuple(converted)


def complete_version(connection: Connection, plan: SourcePlan) -> bool:
    current = connection.scalar(
        select(documents.c.content_digest).where(
            documents.c.document_id == plan.document.document_id
        )
    )
    if current != plan.document.content_digest:
        return False
    rows = connection.execute(
        select(chunks.c.chunk_id, chunks.c.embedding).where(
            chunks.c.document_id == plan.document.document_id
        )
    ).all()
    return {row.chunk_id for row in rows} == {c.chunk_id for c in plan.chunks} and all(
        row.embedding is not None for row in rows
    )


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    document_digest: str
    chunk_count: int
    changed: bool


async def ingest(
    engine: Engine, provider: EmbeddingProvider, plan: SourcePlan
) -> IngestResult:
    # The plan is built before any writes; a no-op needs no provider call.
    with engine.connect() as connection:
        complete = complete_version(connection, plan)
    if complete:
        return IngestResult(
            plan.document.document_id,
            plan.document.content_digest,
            len(plan.chunks),
            False,
        )
    vectors = validated_vectors(
        await provider.embed(
            EmbeddingRequest(inputs=tuple(c.content for c in plan.chunks))
        ),
        len(plan.chunks),
    )
    with engine.begin() as connection:
        # Serialize same-source writes including first insertion, without holding
        # a database transaction open across a model/network call.
        key = int(plan.document.document_id[:16], 16)
        if key >= 2**63:
            key -= 2**64
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        if complete_version(connection, plan):
            changed = False
        else:
            connection.execute(
                delete(chunks).where(chunks.c.document_id == plan.document.document_id)
            )
            values = plan.document.model_dump()
            exists = connection.scalar(
                select(documents.c.document_id).where(
                    documents.c.document_id == plan.document.document_id
                )
            )
            if exists:
                connection.execute(
                    documents.update()
                    .where(documents.c.document_id == plan.document.document_id)
                    .values(**values)
                )
            else:
                connection.execute(documents.insert().values(**values))
            connection.execute(
                chunks.insert(),
                [
                    dict(chunk.model_dump(), embedding=list(vector))
                    for chunk, vector in zip(plan.chunks, vectors, strict=True)
                ],
            )
            changed = True
    return IngestResult(
        plan.document.document_id,
        plan.document.content_digest,
        len(plan.chunks),
        changed,
    )


def fuse(
    lexical: Sequence[str], vector: Sequence[str]
) -> list[tuple[str, int | None, int | None, float]]:
    if len(set(lexical)) != len(lexical) or len(set(vector)) != len(vector):
        raise ValueError("retrieval lanes must contain distinct chunks")
    lex = {key: rank for rank, key in enumerate(lexical, 1)}
    vec = {key: rank for rank, key in enumerate(vector, 1)}
    scored = [
        (
            key,
            lex.get(key),
            vec.get(key),
            (1 / (RRF_K + lex[key]) if key in lex else 0)
            + (1 / (RRF_K + vec[key]) if key in vec else 0),
        )
        for key in lex.keys() | vec.keys()
    ]
    return sorted(scored, key=lambda row: (-row[3], row[0]))[:FINAL_LIMIT]


async def retrieve(
    engine: Engine, provider: EmbeddingProvider, query: str
) -> tuple[Evidence, ...]:
    vector = validated_vectors(
        await provider.embed(EmbeddingRequest(inputs=(query,))), 1
    )[0]
    tsquery = func.websearch_to_tsquery(literal_column("'english'::regconfig"), query)
    joined = chunks.join(
        documents,
        (chunks.c.document_id == documents.c.document_id)
        & (chunks.c.document_digest == documents.c.content_digest),
    )
    # One repeatable-read snapshot binds lanes and source evidence to one version.
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as con:
        with con.begin():
            lexical = list(
                con.scalars(
                    select(chunks.c.chunk_id)
                    .select_from(joined)
                    .where(chunks.c.search_vector.op("@@")(tsquery))
                    .order_by(
                        func.ts_rank_cd(chunks.c.search_vector, tsquery).desc(),
                        chunks.c.chunk_id,
                    )
                    .limit(LANE_LIMIT)
                )
            )
            semantic = list(
                con.scalars(
                    select(chunks.c.chunk_id)
                    .select_from(joined)
                    .where(chunks.c.embedding.is_not(None))
                    .order_by(
                        chunks.c.embedding.cosine_distance(list(vector)),
                        chunks.c.chunk_id,
                    )
                    .limit(LANE_LIMIT)
                )
            )
            ranked = fuse(lexical, semantic)
            rows = {
                row.chunk_id: row
                for row in con.execute(
                    select(
                        chunks.c.chunk_id,
                        chunks.c.document_id,
                        chunks.c.document_digest,
                        chunks.c.content,
                        documents.c.title,
                        documents.c.source_path,
                    )
                    .select_from(joined)
                    .where(chunks.c.chunk_id.in_([r[0] for r in ranked]))
                ).all()
            }
    return tuple(
        Evidence(
            evidence_id=key,
            chunk_id=key,
            document_id=rows[key].document_id,
            document_digest=rows[key].document_digest,
            content=rows[key].content,
            title=rows[key].title,
            source_path=rows[key].source_path,
            lexical_rank=lex_rank,
            vector_rank=vec_rank,
            rrf_score=score,
        )
        for key, lex_rank, vec_rank, score in ranked
    )
