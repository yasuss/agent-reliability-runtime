"""Local scoped memory list/delete and liveness; no enterprise auth claim."""

from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from agent_reliability_runtime.contracts.domain import (
    AuditEvent,
    Identifier,
    Memory,
    Record,
    Run,
)
from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.memory import MemoryStore
from agent_reliability_runtime.observability import AuditTrail, read_run
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.policy import Approvals, PolicyError
from agent_reliability_runtime.runtime.local import RunRequest, local_runtime
from agent_reliability_runtime.runtime.service import DurableRuntime


class ApprovalDecision(Record):
    decision: Literal["APPROVE", "REJECT"]


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


def create_app(
    engine: Engine | None = None,
    *,
    runtime_factory: Callable[
        [Engine], AbstractAsyncContextManager[DurableRuntime]
    ] = local_runtime,
) -> FastAPI:
    application = FastAPI(title="Agent Reliability Runtime")

    def store() -> Iterator[MemoryStore]:
        owned = engine is None
        selected = engine if engine is not None else create_engine(database_url())
        try:
            yield MemoryStore(selected)
        finally:
            if owned:
                selected.dispose()

    @application.post("/api/v1/runs", response_model=Run)
    async def post_run(
        body: RunRequest, memories: Annotated[MemoryStore, Depends(store)]
    ) -> Run:
        run = body.run()
        async with runtime_factory(memories.engine) as runtime:
            await runtime.start(run)
        with memories.engine.connect() as con:
            persisted = read_run(con, run.run_id)
        assert persisted is not None
        return persisted

    @application.post(
        "/api/v1/runs/{run_id}/approvals/{approval_id}", response_model=Run
    )
    async def post_approval(
        run_id: Identifier,
        approval_id: Identifier,
        body: ApprovalDecision,
        memories: Annotated[MemoryStore, Depends(store)],
    ) -> Run:
        try:
            approval = Approvals(memories.engine).read(approval_id)
        except PolicyError:
            raise HTTPException(status_code=404, detail="Approval not found") from None
        if approval.run_id != run_id:
            raise HTTPException(status_code=404, detail="Approval not found")
        unavailable = False
        async with runtime_factory(memories.engine) as runtime:
            try:
                snapshot = await runtime.inspect(run_id)
                if (
                    not snapshot.interrupts
                    or snapshot.values.get("approval_id") != approval_id
                ):
                    raise PolicyError("matching interrupted approval required")
                runtime.context.gateway.approvals.decide(
                    approval_id, approved=body.decision == "APPROVE"
                )
                await runtime.resume(run_id, "continue")
            except PolicyError:
                unavailable = True
        if unavailable:
            raise HTTPException(
                status_code=409, detail="Approval decision unavailable"
            ) from None
        with memories.engine.connect() as con:
            persisted = read_run(con, run_id)
        assert persisted is not None
        return persisted

    @application.get("/healthz", response_model=Health)
    def health() -> Health:
        return Health(status="ok")

    @application.get("/api/v1/runs/{run_id}", response_model=Run)
    def get_run(
        run_id: Identifier, memories: Annotated[MemoryStore, Depends(store)]
    ) -> Run:
        with memories.engine.connect() as con:
            run = read_run(con, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    @application.get("/api/v1/runs/{run_id}/events", response_model=list[AuditEvent])
    def get_events(
        run_id: Identifier, memories: Annotated[MemoryStore, Depends(store)]
    ) -> list[AuditEvent]:
        try:
            return AuditTrail(memories.engine).list(run_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Run not found") from None

    @application.get("/readyz", response_model=Health)
    def ready(memories: Annotated[MemoryStore, Depends(store)]) -> Health:
        try:
            with memories.engine.connect() as con:
                con.execute(text("SELECT 1"))
                inspector = inspect(con)
                required = set(schema.metadata.tables) | {
                    "checkpoints",
                    "checkpoint_blobs",
                    "checkpoint_writes",
                    "checkpoint_migrations",
                }
                if not all(inspector.has_table(name) for name in required):
                    raise HTTPException(status_code=503, detail="Not ready")
            return Health(status="ready")
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="Not ready") from None

    @application.get("/api/v1/memory", response_model=list[Memory])
    def list_memory(
        workspace_id: Annotated[Identifier, Query()],
        user_id: Annotated[Identifier, Query()],
        memories: Annotated[MemoryStore, Depends(store)],
    ) -> list[Memory]:
        return memories.list(workspace_id, user_id)

    @application.delete("/api/v1/memory/{memory_id}", status_code=204)
    def delete_memory(
        memory_id: Identifier,
        workspace_id: Annotated[Identifier, Query()],
        user_id: Annotated[Identifier, Query()],
        memories: Annotated[MemoryStore, Depends(store)],
    ) -> Response:
        if not memories.delete(workspace_id, user_id, memory_id):
            raise HTTPException(status_code=404, detail="Memory not found")
        return Response(status_code=204)

    return application


app = create_app()
