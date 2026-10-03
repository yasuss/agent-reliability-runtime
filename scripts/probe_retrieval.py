"""Exact-candidate local B30 proof. Requires a freshly migrated disposable DB."""

import argparse
import asyncio
import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError

from agent_reliability_runtime.cli import local_embeddings
from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.persistence.schema import knowledge_chunks as chunks
from agent_reliability_runtime.persistence.schema import (
    knowledge_documents as documents,
)
from agent_reliability_runtime.providers.contracts import (
    EmbeddingRequest,
    EmbeddingResult,
)
from agent_reliability_runtime.retrieval.contracts import (
    Evidence,
    validate_citations,
    validate_current_digest,
)
from agent_reliability_runtime.retrieval.evaluation import (
    calibrate_checkers,
    require_gates,
    score_query,
)
from agent_reliability_runtime.retrieval.service import ingest, retrieve
from agent_reliability_runtime.retrieval.text import plan_source, read_source

MODEL_DIGEST = "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d"
EVAL_DIGEST = "c6dc4cbc960f6b9a22297aad2e9523bee90a3147b612b94dfedccfbfd976d8a4"


class AcceptedEmbeddings:
    def __init__(self) -> None:
        self.adapter = local_embeddings()
        self.calls: list[dict[str, Any]] = []

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        result = await self.adapter.embed(request)
        if result.model_id != "qwen3-embedding:0.6b" or result.dimension != 1024:
            raise ValueError("accepted model identity/dimension mismatch")
        self.calls.append(
            {
                "model": result.model_id,
                "dimension": result.dimension,
                "inputs": len(request.inputs),
                "input_tokens": result.input_tokens,
            }
        )
        return result


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def canonical_digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def proof(root: Path) -> dict[str, Any]:
    subject = git("rev-parse", "HEAD")
    if git("status", "--porcelain"):
        raise ValueError("exact-candidate proof requires a clean checkout")
    with httpx.Client(trust_env=False, timeout=30) as client:
        version = client.get("http://127.0.0.1:11434/api/version")
        version.raise_for_status()
        tags = client.get("http://127.0.0.1:11434/api/tags")
        tags.raise_for_status()
    model = next(
        m for m in tags.json()["models"] if m["name"] == "qwen3-embedding:0.6b"
    )
    if model["digest"] != MODEL_DIGEST:
        raise ValueError("accepted embedding artifact changed; return to Architect")
    paths = sorted((root / "data/knowledge").glob("*"))
    if len(paths) != 6:
        raise ValueError("canonical corpus must contain exactly six files")
    plans = []
    byte_digests = {}
    for path in paths:
        locked = root / "docs/project/spec/v1.0/fixtures/knowledge" / path.name
        if path.read_bytes() != locked.read_bytes():
            raise ValueError("canonical corpus differs from locked fixture")
        source = path.relative_to(root).as_posix()
        plans.append(read_source(root, source))
        byte_digests[source] = hashlib.sha256(path.read_bytes()).hexdigest()
    fixture_path = root / "evals/retrieval/fixture.json"
    if hashlib.sha256(fixture_path.read_bytes()).hexdigest() != EVAL_DIGEST:
        raise ValueError("locked retrieval eval fixture changed")
    fixture = json.loads(fixture_path.read_bytes())
    provider = AcceptedEmbeddings()
    engine = create_engine(database_url())
    try:
        with engine.connect() as con:
            if con.scalar(select(func.count()).select_from(documents)) != 0:
                raise ValueError("live proof requires an empty disposable knowledge DB")
            database = {
                "postgresql": con.scalar(text("SHOW server_version")),
                "pgvector": con.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='vector'")
                ),
                "migration": con.scalar(
                    text("SELECT version_num FROM alembic_version")
                ),
                "embedding_type": con.scalar(
                    text(
                        "SELECT format_type(atttypid,atttypmod) FROM pg_attribute "
                        "WHERE attrelid='knowledge_chunks'::regclass "
                        "AND attname='embedding'"
                    )
                ),
            }
        assert (
            database["migration"] == "0003_retrieval"
            and database["embedding_type"] == "vector(1024)"
        )
        ingested = [asdict(await ingest(engine, provider, plan)) for plan in plans]
        repeated = [asdict(await ingest(engine, provider, plan)) for plan in plans]
        assert all(row["changed"] for row in ingested)
        assert all(not row["changed"] for row in repeated)
        with engine.connect() as con:
            dimensions = list(
                con.scalars(select(func.vector_dims(chunks.c.embedding)).distinct())
            )
            assert dimensions == [1024]
            counts = {
                "documents": con.scalar(select(func.count()).select_from(documents)),
                "chunks": con.scalar(select(func.count()).select_from(chunks)),
            }
        per_query = []
        scores = []
        for case in fixture["queries"]:
            result = await retrieve(engine, provider, case["query"])
            validate_citations(tuple(e.evidence_id for e in result), result)
            for plan in plans:
                validate_current_digest(
                    result, plan.document.document_id, plan.document.content_digest
                )
            score = score_query(case["expected_source"], result)
            scores.append(score)
            per_query.append(
                case | asdict(score) | {"evidence": [e.model_dump() for e in result]}
            )
        metrics = {
            "recall_at_6": sum(s.recall_at_6 for s in scores) / len(scores),
            "hit_at_1": sum(s.hit_at_1 for s in scores) / len(scores),
            "mean_reciprocal_rank": sum(s.reciprocal_rank for s in scores)
            / len(scores),
            "citation_subset_validity": 1.0,
        }
        # Rehearsal uses a separate logical source, never edits canonical files.
        old = plan_source("rehearsal/checkout.txt", b"checkout approval old rehearsal")
        new = plan_source(
            "rehearsal/checkout.txt", b"checkout approval updated rehearsal"
        )
        await ingest(engine, provider, old)
        await ingest(engine, provider, new)
        results = await retrieve(engine, provider, "checkout approval rehearsal")
        validate_current_digest(
            results, new.document.document_id, new.document.content_digest
        )
        assert all(e.chunk_id != old.chunks[0].chunk_id for e in results)
        with engine.connect() as con:
            stale_count = con.scalar(
                select(func.count())
                .select_from(chunks)
                .where(
                    (chunks.c.document_id == old.document.document_id)
                    & (chunks.c.document_digest == old.document.content_digest)
                )
            )
        assert stale_count == 0
        # Do not disable B10's exact-version FK to manufacture stale storage.
        # A deliberate old-row reinsertion must be rejected by the real DB.
        with engine.begin() as con:
            try:
                with con.begin_nested():
                    con.execute(chunks.insert(), old.chunks[0].model_dump())
            except IntegrityError as error:
                assert (
                    error.orig.diag.constraint_name
                    == "fk_knowledge_chunks_document_version"
                )
                stale_reinsertion_rejected = True
            else:
                raise AssertionError("DB accepted a stale document-version chunk")
        # Temporary real local embeddings create >6 distinct distractor documents;
        # pure oracle calibration then checks good/broken/alternate candidate sets.
        pool = []
        for i in range(8):
            plan = plan_source(
                f"calibration/distractor-{i}.txt",
                f"temporary unrelated distractor {i}".encode(),
            )
            await ingest(engine, provider, plan)
            chunk = plan.chunks[0]
            pool.append(
                Evidence(
                    evidence_id=chunk.chunk_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    document_digest=chunk.document_digest,
                    title=plan.document.title,
                    source_path=plan.document.source_path,
                    content=chunk.content,
                    lexical_rank=None,
                    vector_rank=i + 1,
                    rrf_score=1 / (61 + i),
                )
            )
        calibration = calibrate_checkers(pool)
        payload = {
            "subject_sha": subject,
            "database": database,
            "ollama_version": version.json()["version"],
            "model": model["name"],
            "model_digest": model["digest"],
            "dimension": dimensions[0],
            "corpus_byte_digests": byte_digests,
            "corpus_digest": canonical_digest(
                {p.document.source_path: p.document.content_digest for p in plans}
            ),
            "corpus_digest_definition": (
                "SHA256 of UTF-8 compact sorted-key JSON "
                "path -> normalized-content SHA256"
            ),
            "eval_fixture_digest": EVAL_DIGEST,
            "canonical_counts": counts,
            "ingested": ingested,
            "unchanged_reingestion": repeated,
            "metrics": metrics,
            "per_query": per_query,
            "stale_digest_proof": {
                "old_digest": old.document.content_digest,
                "new_digest": new.document.content_digest,
                "old_rows": stale_count,
                "old_results": 0,
                "old_row_reinsertion_fk_rejected": stale_reinsertion_rejected,
            },
            "checker_calibration": calibration,
            "embedding_calls": provider.calls,
        }
        payload["result_digest"] = canonical_digest(payload)
        return payload
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = asyncio.run(proof(Path.cwd()))
    # Retain measured results even if the gate fails; never tune away a failure.
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: payload[key]
                for key in (
                    "subject_sha",
                    "model_digest",
                    "dimension",
                    "corpus_digest",
                    "eval_fixture_digest",
                    "metrics",
                    "stale_digest_proof",
                    "checker_calibration",
                    "result_digest",
                )
            },
            indent=2,
        )
    )
    require_gates(
        payload["metrics"]["recall_at_6"],
        payload["metrics"]["citation_subset_validity"],
    )


if __name__ == "__main__":
    main()
