"""Liveness boundary only; no agent or database readiness claim."""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


app = FastAPI(title="Agent Reliability Runtime — foundation")


@app.get("/healthz", response_model=Health)
def health() -> Health:
    return Health(status="ok")
