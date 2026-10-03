"""Evidence snapshots and pure fail-closed checks; text confers no authority."""

from collections.abc import Sequence
from typing import Annotated, Self

from pydantic import Field, model_validator

from agent_reliability_runtime.contracts.domain import Digest, Identifier, Record


class Evidence(Record):
    evidence_id: Digest
    document_id: Digest
    chunk_id: Digest
    document_digest: Digest
    title: Identifier
    source_path: Identifier
    content: Identifier
    lexical_rank: Annotated[int, Field(gt=0, strict=True)] | None
    vector_rank: Annotated[int, Field(gt=0, strict=True)] | None
    rrf_score: Annotated[float, Field(gt=0)]

    @model_validator(mode="after")
    def exact_identity(self) -> Self:
        if self.evidence_id != self.chunk_id:
            raise ValueError("evidence identity must equal chunk identity")
        if self.lexical_rank is None and self.vector_rank is None:
            raise ValueError("evidence must belong to at least one retrieval lane")
        return self


def validate_citations(cited_ids: Sequence[str], retrieved: Sequence[Evidence]) -> None:
    allowed = {item.evidence_id for item in retrieved}
    if any(item not in allowed for item in cited_ids):
        raise ValueError("citation does not belong to the exact retrieval result")


def validate_current_digest(
    retrieved: Sequence[Evidence], document_id: str, expected_digest: str
) -> None:
    if any(
        item.document_id == document_id and item.document_digest != expected_digest
        for item in retrieved
    ):
        raise ValueError("stale document digest in retrieval result")
