"""Exact-head B50 acceptance. Requires a fresh disposable migrated DB."""

import argparse
import asyncio
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select, text

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.policy import TOOL_RISK, VERSION
from scripts.opsdesk_proof_support import digest
from scripts.policy_proof_support import stdio_proof


async def proof() -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    ).strip(), "clean exact-head required"
    assert importlib.metadata.version("mcp") == "2.3.0"
    engine = create_engine(database_url())
    try:
        with engine.connect() as con:
            assert all(
                con.scalar(select(func.count()).select_from(t)) == 0
                for t in schema.metadata.tables.values()
            )
            db = {
                "version": con.scalar(text("SHOW server_version")),
                "migration": con.scalar(
                    text("SELECT version_num FROM alembic_version")
                ),
                "pgvector": con.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='vector'")
                ),
            }
        client = OpsDeskMCPClient(
            Path.cwd(), database_url().render_as_string(hide_password=False)
        )
        async with client:
            result = {
                "subject_sha": head,
                "policy_version": VERSION,
                "registry": dict(TOOL_RISK),
                "mcp_version": importlib.metadata.version("mcp"),
                "mcp_types_version": importlib.metadata.version("mcp-types"),
                "protocol": client.protocol_version,
                "server": client.server_info,
                "database": db,
                "wire_tools": [
                    t.model_dump(mode="json", by_alias=True)
                    for t in client.wire_tools.values()
                ],
                "model_tools": [t.model_dump(mode="json") for t in client.model_tools],
                "stdio": await stdio_proof(engine, client),
            }
        try:
            await client.read("get_service_status", {"service_id": "checkout-api"})
        except RuntimeError:
            result["official_context_closed"] = True
        else:
            raise AssertionError("stdio connection remains open")
        result["result_digest"] = digest(result)
        return result
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(proof())
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"wire_tools", "model_tools"}},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
