"""Real migrations/FTS/cosine/atomic replacement with deterministic fake embeddings."""

import asyncio
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event, func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from agent_reliability_runtime.persistence.schema import knowledge_chunks as chunks
from agent_reliability_runtime.persistence.schema import (
    knowledge_documents as documents,
)
from agent_reliability_runtime.providers.contracts import (
    EmbeddingRequest,
    EmbeddingResult,
)
from agent_reliability_runtime.retrieval.contracts import (
    validate_citations,
    validate_current_digest,
)
from agent_reliability_runtime.retrieval.evaluation import (
    calibrate_checkers,
    score_query,
)
from agent_reliability_runtime.retrieval.service import ingest, retrieve
from agent_reliability_runtime.retrieval.text import plan_source

pytestmark = pytest.mark.integration


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.dimension = 1024

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError("deliberate embedding failure")
        vectors = tuple(
            ((1.0, 0.0) if "target" in value else (0.0, 1.0))
            + (0.0,) * (self.dimension - 2)
            for value in request.inputs
        )
        return EmbeddingResult(provider_id="fake", model_id="fake", vectors=vectors)


def test_b20_b30_roundtrip_without_provider(isolated_db: tuple[Engine, Config]) -> None:
    engine, cfg = isolated_db
    command.downgrade(cfg, "0002_domain")
    # A real pre-B30 persisted row upgrades without model inference/backfill.
    plan = plan_source("legacy.md", b"# Legacy\ncheckout")
    with engine.begin() as con:
        con.execute(documents.insert(), plan.document.model_dump())
        values = plan.chunks[0].model_dump()
        con.execute(
            text(
                "INSERT INTO knowledge_chunks "
                "(chunk_id,document_id,document_digest,ordinal,content) "
                "VALUES (:chunk_id,:document_id,:document_digest,:ordinal,:content)"
            ),
            values,
        )
    command.upgrade(cfg, "head")
    with engine.connect() as con:
        assert con.scalar(select(chunks.c.embedding)) is None
        assert "checkout" in str(con.scalar(select(chunks.c.search_vector)))
        assert (
            con.scalar(
                text(
                    "SELECT format_type(atttypid,atttypmod) FROM pg_attribute "
                    "WHERE attrelid='knowledge_chunks'::regclass "
                    "AND attname='embedding'"
                )
            )
            == "vector(1024)"
        )
        indexes = inspect(con).get_indexes("knowledge_chunks")
        assert any(
            i["name"] == "ix_knowledge_chunks_search_vector"
            and i["dialect_options"]["postgresql_using"] == "gin"
            for i in indexes
        )
        assert not any(
            i.get("dialect_options", {}).get("postgresql_using") in {"hnsw", "ivfflat"}
            for i in indexes
        )
    provider = FakeEmbeddings()
    assert asyncio.run(ingest(engine, provider, plan)).changed
    command.downgrade(cfg, "0002_domain")
    command.upgrade(cfg, "head")
    assert asyncio.run(ingest(engine, provider, plan)).changed


def test_replacement_idempotence_failures_and_no_stale(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    provider = FakeEmbeddings()
    old = plan_source("target.md", b"# Original\ntarget approval")
    changed = plan_source("target.md", b"# Replacement\ntarget checkout")
    assert asyncio.run(ingest(engine, provider, old)).changed
    assert not asyncio.run(ingest(engine, provider, old)).changed
    assert provider.calls == 1
    provider.fail = True
    with pytest.raises(RuntimeError):
        asyncio.run(ingest(engine, provider, changed))
    provider.fail = False
    provider.dimension = 3
    with pytest.raises(ValueError):
        asyncio.run(ingest(engine, provider, changed))
    with engine.connect() as con:
        assert (
            con.scalar(select(documents.c.content_digest))
            == old.document.content_digest
        )
        assert con.scalar(select(func.count()).select_from(chunks)) == 1
    provider.dimension = 1024

    # Force a DB write failure after the old chunks were deleted; transaction
    # rollback must preserve the original source and vectors.
    def reject_insert(
        con: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        if statement.startswith("INSERT INTO knowledge_chunks"):
            raise RuntimeError("deliberate write failure")

    event.listen(engine, "before_cursor_execute", reject_insert)
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(ingest(engine, provider, changed))
    finally:
        event.remove(engine, "before_cursor_execute", reject_insert)
    with engine.connect() as con:
        assert (
            con.scalar(select(documents.c.content_digest))
            == old.document.content_digest
        )
        assert con.scalar(select(chunks.c.chunk_id)) == old.chunks[0].chunk_id
    assert asyncio.run(ingest(engine, provider, changed)).changed
    result = asyncio.run(retrieve(engine, provider, "target checkout"))
    validate_current_digest(
        result, changed.document.document_id, changed.document.content_digest
    )
    assert old.chunks[0].chunk_id not in {e.chunk_id for e in result}
    with engine.connect() as con:
        assert (
            con.scalar(
                select(func.count())
                .select_from(chunks)
                .where(chunks.c.document_digest == old.document.content_digest)
            )
            == 0
        )


def test_real_lanes_ties_and_calibration(isolated_db: tuple[Engine, Config]) -> None:
    engine, _ = isolated_db
    provider = FakeEmbeddings()
    plans = [
        plan_source(f"temporary/{i}.md", f"# Distractor {i}\nother unrelated".encode())
        for i in range(24)
    ]
    plans.append(
        plan_source(
            "temporary/target.md", b"# Target\ntarget checkout approval approval"
        )
    )
    for plan in plans:
        asyncio.run(ingest(engine, provider, plan))
    before = provider.calls
    results = asyncio.run(retrieve(engine, provider, '"target checkout" OR approval'))
    assert provider.calls == before + 1
    assert len(results) == 6
    assert results[0].source_path == "temporary/target.md"
    assert results[0].vector_rank == results[0].lexical_rank == 1
    assert all(e.vector_rank is not None and e.vector_rank <= 20 for e in results)
    assert score_query("temporary/target.md", results).recall_at_6 == 1
    # Equal cosine distances use stable chunk identity ascending.
    ties = [e.chunk_id for e in results[1:]]
    assert ties == sorted(ties)
    raw = asyncio.run(retrieve(engine, provider, '"unfinished OR : &'))
    assert all(e.lexical_rank is None for e in raw)
    validate_citations([results[0].evidence_id], results)
    outside = plans[0].chunks[0].chunk_id
    if outside in {e.evidence_id for e in results}:
        outside = next(
            p.chunks[0].chunk_id
            for p in plans
            if p.chunks[0].chunk_id not in {e.evidence_id for e in results}
        )
    with pytest.raises(ValueError):
        validate_citations(
            [outside], results
        )  # Exists in DB, absent from exact result.
    pool = []
    for plan in plans[:8]:
        retrieved = asyncio.run(
            retrieve(
                engine, provider, f'"Distractor {plan.document.title.split()[-1]}"'
            )
        )
        item = next(e for e in retrieved if e.document_id == plan.document.document_id)
        pool.append(item)
    assert all(calibrate_checkers(pool).values())


def test_generated_fts_updates_and_pg_dimension_oracle(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    provider = FakeEmbeddings()
    plan = plan_source("test.md", b"original checkout")
    asyncio.run(ingest(engine, provider, plan))
    with engine.begin() as con:
        assert "checkout" in str(con.scalar(select(chunks.c.search_vector)))
        con.execute(chunks.update().values(content="alternate billing"))
        value = str(con.scalar(select(chunks.c.search_vector)))
        assert "bill" in value and "checkout" not in value  # English stemming.
        for bad in ([1.0], [float("inf")] * 1024):
            with pytest.raises(DBAPIError), con.begin_nested():
                con.execute(chunks.update().values(embedding=bad))
