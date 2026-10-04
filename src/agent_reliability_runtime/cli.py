"""Developer ingestion and fail-closed sanitized replay export commands."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import create_engine

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.providers.http import (
    HTTPProviderConfig,
    OllamaEmbeddingProvider,
)
from agent_reliability_runtime.replay import export_replay
from agent_reliability_runtime.retrieval.service import ingest
from agent_reliability_runtime.retrieval.text import read_source


def local_embeddings() -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider(
        HTTPProviderConfig(
            provider_id="ollama-local",
            model_id="qwen3-embedding:0.6b",
            base_url="http://127.0.0.1:11434",
            timeout_seconds=300,
        )
    )


async def ingest_paths(root: Path, paths: list[str]) -> None:
    plans = [read_source(root, path) for path in paths]
    engine = create_engine(database_url())
    try:
        for plan in plans:
            print(json.dumps(asdict(await ingest(engine, local_embeddings(), plan))))
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ingestion = sub.add_parser("ingest")
    ingestion.add_argument("sources", nargs="+")
    exporting = sub.add_parser("export-replays")
    exporting.add_argument("--run-id", required=True)
    exporting.add_argument("--receipt", type=Path, required=True)
    exporting.add_argument("--source-git-sha", required=True)
    exporting.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "export-replays":
        engine = create_engine(database_url())
        try:
            export_replay(
                engine,
                args.run_id,
                json.loads(args.receipt.read_text()),
                args.source_git_sha,
                args.output,
            )
        finally:
            engine.dispose()
    else:
        asyncio.run(ingest_paths(Path.cwd(), args.sources))


if __name__ == "__main__":
    main()
