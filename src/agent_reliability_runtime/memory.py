"""Scoped contextual memory; provenance/trust never confer tool authority."""

import builtins
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import Connection, Engine, delete, select
from sqlalchemy.sql.elements import ColumnElement

from agent_reliability_runtime.contracts.domain import (
    Identifier,
    Memory,
    MemoryKind,
    MemoryProvenance,
    MemoryTrust,
    Run,
)
from agent_reliability_runtime.observability import AuditTrail, Telemetry, memory_anchor
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import insert_snapshot
from agent_reliability_runtime.policy import TOOL_RISK


class MemoryError(ValueError):
    """Bounded profile/source error without foreign content disclosure."""


def identifier(value: str) -> str:
    return TypeAdapter(Identifier).validate_python(value)


def scope(workspace_id: str, user_id: str) -> ColumnElement[bool]:
    return (schema.memories.c.workspace_id == identifier(workspace_id)) & (
        schema.memories.c.user_id == identifier(user_id)
    )


class MemoryStore:
    def __init__(
        self,
        engine: Engine,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: uuid4().hex,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.engine, self.clock, self.id_factory = engine, clock, id_factory
        self.telemetry = telemetry or Telemetry()

    def list(self, workspace_id: str, user_id: str) -> list[Memory]:
        return self.resolve(workspace_id, user_id, None)

    def resolve(
        self, workspace_id: str, user_id: str, memory_ids: Sequence[str] | None
    ) -> builtins.list[Memory]:
        query = select(schema.memories).where(scope(workspace_id, user_id))
        if memory_ids is not None:
            query = query.where(
                schema.memories.c.memory_id.in_([identifier(i) for i in memory_ids])
            )
        query = query.order_by(
            schema.memories.c.created_at, schema.memories.c.memory_id
        )
        with self.engine.connect() as con:
            return [
                Memory.model_validate(dict(r)) for r in con.execute(query).mappings()
            ]

    def get(self, workspace_id: str, user_id: str, memory_id: str) -> Memory | None:
        rows = self.resolve(workspace_id, user_id, [memory_id])
        return rows[0] if rows else None

    def delete(self, workspace_id: str, user_id: str, memory_id: str) -> bool:
        with self.telemetry.span(
            "agent.memory.write", **{"arr.memory.operation": "delete"}
        ) as span:
            with self.engine.begin() as con:
                row = (
                    con.execute(
                        select(schema.memories)
                        .where(
                            scope(workspace_id, user_id),
                            schema.memories.c.memory_id == identifier(memory_id),
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return False
                memory = Memory.model_validate(dict(row))
                anchor = memory_anchor(con, workspace_id, user_id)
                span.set_attribute("arr.run.id", anchor)
                AuditTrail(self.engine).append_in(
                    con,
                    anchor,
                    "memory.deleted",
                    memory.model_dump(exclude={"content"}),
                )
                con.execute(
                    delete(schema.memories).where(
                        scope(workspace_id, user_id),
                        schema.memories.c.memory_id == memory_id,
                    )
                )
                return True

    def user_explicit(
        self,
        workspace_id: str,
        user_id: str,
        content: str,
        *,
        kind: MemoryKind = MemoryKind.PREFERENCE,
        source_run_id: str | None = None,
    ) -> Memory:
        if kind not in {MemoryKind.PREFERENCE, MemoryKind.VERIFIED_FACT}:
            raise MemoryError("invalid user memory kind")
        return self._create(
            workspace_id,
            user_id,
            content,
            kind,
            MemoryProvenance.USER_EXPLICIT,
            MemoryTrust.TRUSTED,
            source_run_id,
            None,
        )

    def tool_verified(
        self,
        workspace_id: str,
        user_id: str,
        content: str,
        *,
        source_run_id: str,
        source_tool_name: str,
    ) -> Memory:
        if source_tool_name not in TOOL_RISK:
            raise MemoryError("unknown memory source tool")
        return self._create(
            workspace_id,
            user_id,
            content,
            MemoryKind.VERIFIED_FACT,
            MemoryProvenance.TOOL_VERIFIED,
            MemoryTrust.TRUSTED,
            identifier(source_run_id),
            source_tool_name,
        )

    def model_observation(
        self,
        workspace_id: str,
        user_id: str,
        content: str,
        *,
        source_run_id: str,
    ) -> Memory:
        return self._create(
            workspace_id,
            user_id,
            content,
            MemoryKind.OBSERVATION,
            MemoryProvenance.MODEL_OBSERVATION,
            MemoryTrust.UNTRUSTED,
            identifier(source_run_id),
            None,
        )

    @staticmethod
    def _source(con: Connection, memory: Memory) -> None:
        if memory.source_run_id is None:
            return
        row = (
            con.execute(
                select(schema.runs).where(
                    schema.runs.c.run_id == memory.source_run_id,
                    schema.runs.c.workspace_id == memory.workspace_id,
                    schema.runs.c.user_id == memory.user_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise MemoryError("memory source run must match scope")
        Run.model_validate(dict(row))

    def _create(
        self,
        workspace_id: str,
        user_id: str,
        content: str,
        kind: MemoryKind,
        provenance: MemoryProvenance,
        trust: MemoryTrust,
        source_run_id: str | None,
        source_tool_name: str | None,
    ) -> Memory:
        now = self.clock()
        memory = Memory(
            memory_id=self.id_factory(),
            workspace_id=workspace_id,
            user_id=user_id,
            content=content,
            kind=kind,
            provenance=provenance,
            trust=trust,
            created_at=now,
            updated_at=now,
            source_run_id=source_run_id,
            source_tool_name=source_tool_name,
        )
        with self.telemetry.span(
            "agent.memory.write", **{"arr.memory.operation": "create"}
        ) as span:
            with self.engine.begin() as con:
                self._source(con, memory)
                insert_snapshot(con, memory)
                anchor = memory_anchor(con, workspace_id, user_id)
                span.set_attribute("arr.run.id", anchor)
                AuditTrail(self.engine).append_in(
                    con,
                    anchor,
                    "memory.created",
                    memory.model_dump(exclude={"content"}),
                )
        return memory
