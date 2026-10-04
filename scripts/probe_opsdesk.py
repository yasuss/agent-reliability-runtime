"""Exact-head B40 stdio/state proof. Only target a fresh disposable migrated DB."""

import argparse
import asyncio
import copy
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

from opsdesk_proof_support import digest, state_proof
from sqlalchemy import create_engine, func, select, text

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.mcp.client import (
    OpsDeskError,
    OpsDeskMCPClient,
    catalog,
    validate_model_view,
)
from agent_reliability_runtime.persistence import schema


async def proof(root: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("exact-head proof requires a clean tree")
    assert importlib.metadata.version("mcp") == "2.3.0"
    engine = create_engine(database_url())
    try:
        with engine.connect() as con:
            assert all(
                con.scalar(select(func.count()).select_from(table)) == 0
                for table in schema.metadata.tables.values()
            )
            database = {
                "version": con.scalar(text("SHOW server_version")),
                "migration": con.scalar(
                    text("SELECT version_num FROM alembic_version")
                ),
                "pgvector": con.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='vector'")
                ),
            }
        client = OpsDeskMCPClient(
            root, database_url().render_as_string(hide_password=False)
        )
        async with client:
            payload = {
                "subject_sha": head,
                "mcp_version": "2.3.0",
                "mcp_types_version": importlib.metadata.version("mcp-types"),
                "protocol": client.protocol_version,
                "server": client.server_info,
                "database": database,
                "transport": "stdio subprocess",
                "python_command": "current sys.executable",
                "args": client.parameters.args,
                "cwd": client.parameters.cwd,
                "explicit_env_keys": sorted(client.parameters.env or {}),
                "wire_tools": [
                    tool.model_dump(mode="json", by_alias=True)
                    for tool in client.wire_tools.values()
                ],
                "model_tools": [
                    tool.model_dump(mode="json") for tool in client.model_tools
                ],
            }
            payload["state_proof"] = await state_proof(
                engine, client.raw_wire_call_for_testing
            )
            # All five adversarial annotations must leave ownership unchanged.
            spoofed = copy.deepcopy(list(client.wire_tools.values()))
            for tool in spoofed:
                if tool.annotations:
                    tool.annotations.read_only_hint = True
                    tool.annotations.idempotent_hint = True
                    tool.annotations.open_world_hint = True
            _, models = catalog(spoofed)
            validate_model_view(models)
            assert [m.parameters for m in models] == [
                m.parameters for m in client.model_tools
            ]
            calibration = {
                "forged_readonly_ownership_unchanged": True,
                "good_model_view": True,
            }
            for kind in ("expose_runtime", "remove_model_owned"):
                bad = list(models)
                index = next(
                    i for i, t in enumerate(bad) if t.name == "restart_service"
                )
                parameters: dict[str, Any] = copy.deepcopy(bad[index].parameters)
                if kind == "expose_runtime":
                    parameters["properties"]["idempotency_key"] = {
                        "type": "string",
                        "minLength": 1,
                    }
                    parameters["required"].append("idempotency_key")
                else:
                    del parameters["properties"]["reason"]
                    parameters["required"].remove("reason")
                bad[index] = bad[index].model_copy(update={"parameters": parameters})
                try:
                    validate_model_view(bad)
                except OpsDeskError:
                    calibration[kind + "_rejected"] = True
                else:
                    raise AssertionError("model ownership oracle insensitive")
            alternate = copy.deepcopy(models)
            for tool in alternate:
                tool.parameters["title"] = "harmless alternate"
            validate_model_view(alternate)
            calibration["valid_alternate"] = True
            payload["annotation_and_schema_calibration"] = calibration
        # A closed official connection rejects subsequent requests; no live child
        # or protocol stream is retained by the SDK context.
        try:
            await client.read("get_service_status", {"service_id": "checkout-api"})
        except RuntimeError:
            payload["official_context_closed"] = True
        else:
            raise AssertionError("stdio connection remains open after exit")
        payload["result_digest"] = digest(payload)
        return payload
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = asyncio.run(proof(Path.cwd()))
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: payload[k]
                for k in (
                    "subject_sha",
                    "mcp_version",
                    "protocol",
                    "server",
                    "state_proof",
                    "annotation_and_schema_calibration",
                    "official_context_closed",
                    "result_digest",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
