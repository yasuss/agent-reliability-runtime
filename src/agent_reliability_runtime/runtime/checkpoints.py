"""Explicit framework setup and strict Postgres checkpoint construction."""

import asyncio
import sys
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import URL

from agent_reliability_runtime.database import database_url


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    # Psycopg async connections require SelectorEventLoop on Windows.
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(coroutine)


def strict_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=None, pickle_fallback=False)


def conn_string(url: URL) -> str:
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL checkpoint persistence required")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def open_saver(url: URL | None = None) -> AsyncIterator[AsyncPostgresSaver]:
    # No implicit setup. Caller must execute explicit setup once beforehand.
    async with AsyncPostgresSaver.from_conn_string(
        conn_string(url or database_url()), serde=strict_serde()
    ) as saver:
        yield saver


async def setup_checkpoints(url: URL | None = None) -> None:
    async with open_saver(url) as saver:
        await saver.setup()
