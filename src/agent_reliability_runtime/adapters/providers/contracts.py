"""Adapter-private embedding capability; not an ARR core port."""

from typing import Protocol

from agent_reliability_runtime.core.contracts.model import (
    EmbeddingRequest,
    EmbeddingResult,
)


class EmbeddingProvider(Protocol):
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
