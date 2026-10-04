"""Official in-process and canonical stdio against real migrated fictional DB."""

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from mcp import Client
from mcp.types import RequestParamsMeta
from sqlalchemy import Engine

from agent_reliability_runtime.contracts.domain import Record
from agent_reliability_runtime.mcp.client import (
    OpsDeskMCPClient,
    catalog,
    validated_result,
)
from mcp_server.opsdesk.server import create_server
from scripts.opsdesk_proof_support import NOW, state_proof

pytestmark = pytest.mark.integration


def test_in_process_fictional_state_and_sentinels(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db

    async def exercise() -> None:
        async with Client(create_server(engine, clock=lambda: NOW)) as client:
            catalog((await client.list_tools()).tools)

            async def raw(
                name: str,
                args: dict[str, Any],
                *,
                meta: RequestParamsMeta | None = None,
            ) -> Record:
                return validated_result(
                    name, await client.call_tool(name, args, meta=meta)
                )

            proof = await state_proof(engine, raw)
            assert proof["note"]["applied_at"] == "2026-10-04T00:00:00Z"
            assert proof["duplicate_receipts_replayed"] == 2

    asyncio.run(exercise())


def test_real_stdio_project_client_fictional_state(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db

    async def exercise() -> None:
        async with OpsDeskMCPClient(
            Path(__file__).resolve().parents[2], os.environ["ARR_DATABASE_URL"]
        ) as client:
            assert client.server_info["name"] == "OpsDesk"
            assert client.protocol_version
            assert len(client.wire_tools) == len(client.model_tools) == 5
            result = await state_proof(engine, client.raw_wire_call_for_testing)
            assert result["non_demo_before_digest"] == result["non_demo_after_digest"]
            assert (
                await client.read("get_service_status", {"service_id": "checkout-api"})
            ).model_dump()["status"] == "healthy"
        # Exiting the official async context closes the child transport.

    asyncio.run(exercise())
