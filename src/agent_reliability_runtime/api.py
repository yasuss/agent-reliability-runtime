"""Local scoped memory list/delete and liveness; no enterprise auth claim."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from agent_reliability_runtime.contracts.domain import (
    AuditEvent,
    Identifier,
    Memory,
    Run,
)
from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.memory import MemoryStore
from agent_reliability_runtime.observability import AuditTrail, read_run
from agent_reliability_runtime.persistence import schema


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


def create_app(engine: Engine | None = None) -> FastAPI:
    application = FastAPI(title="Agent Reliability Runtime")

    def store() -> Iterator[MemoryStore]:
        owned = engine is None
        selected = engine if engine is not None else create_engine(database_url())
        try:
            yield MemoryStore(selected)
        finally:
            if owned:
                selected.dispose()

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
