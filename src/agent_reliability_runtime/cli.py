"""Narrow developer ingestion command; no agent, model answers or execution tools."""

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
    args = parser.parse_args()
    asyncio.run(ingest_paths(Path.cwd(), args.sources))


if __name__ == "__main__":
    main()
