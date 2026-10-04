"""Local scoped memory list/delete and liveness; no enterprise auth claim."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, create_engine

from agent_reliability_runtime.contracts.domain import Identifier, Memory
from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.memory import MemoryStore


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
