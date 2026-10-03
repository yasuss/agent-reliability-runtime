"""Fixed source-document recall gate with rank diagnostics and sensitivity controls."""

from collections.abc import Sequence
from dataclasses import dataclass

from agent_reliability_runtime.retrieval.contracts import (
    Evidence,
    validate_citations,
    validate_current_digest,
)


@dataclass(frozen=True)
class QueryScore:
    recall_at_6: float
    hit_at_1: float
    reciprocal_rank: float


def score_query(expected_source: str, retrieved: Sequence[Evidence]) -> QueryScore:
    rank = next(
        (
            i
            for i, item in enumerate(retrieved[:6], 1)
            if item.source_path == expected_source
        ),
        None,
    )
    return QueryScore(
        float(rank is not None), float(rank == 1), 1 / rank if rank else 0.0
    )


def require_gates(recall_at_6: float, citation_validity: float) -> None:
    # Fail closed on NaN as well as values below the locked gate.
    if not 0.90 <= recall_at_6 <= 1 or citation_validity != 1:
        raise ValueError("retrieval acceptance gate failed")


def calibrate_checkers(pool: Sequence[Evidence]) -> dict[str, bool]:
    """Requires >6 distinct synthetic documents; never changes canonical fixtures."""
    if len(pool) <= 6 or len({item.document_id for item in pool}) <= 6:
        raise ValueError("calibration requires more than six distinct documents")
    expected = pool[-1]
    good = (expected, *pool[:5])
    broken = pool[:6]
    alternate = (*pool[:5], expected)
    require_gates(score_query(expected.source_path, good).recall_at_6, 1)
    require_gates(score_query(expected.source_path, alternate).recall_at_6, 1)
    try:
        require_gates(score_query(expected.source_path, broken).recall_at_6, 1)
    except ValueError:
        broken_rejected = True
    else:
        raise AssertionError("arbitrary top-six oracle is insensitive")
    validate_citations((expected.evidence_id,), good)
    validate_citations((good[-1].evidence_id, expected.evidence_id), alternate)
    try:
        validate_citations((pool[5].evidence_id,), good)
    except ValueError:
        citation_rejected = True
    else:
        raise AssertionError("non-retrieved citation oracle is insensitive")
    validate_current_digest(good, expected.document_id, expected.document_digest)
    stale = expected.model_copy(update={"document_digest": "0" * 64})
    try:
        validate_current_digest(
            (stale,), expected.document_id, expected.document_digest
        )
    except ValueError:
        stale_rejected = True
    else:
        raise AssertionError("stale-digest oracle is insensitive")
    return {
        "good": True,
        "valid_alternate": True,
        "arbitrary_top_six_rejected": broken_rejected,
        "non_retrieved_citation_rejected": citation_rejected,
        "reintroduced_stale_digest_rejected": stale_rejected,
    }
