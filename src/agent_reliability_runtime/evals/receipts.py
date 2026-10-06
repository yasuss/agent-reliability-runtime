"""Strict eval-trial-v1 receipt profile over the unchanged locked JSON schema."""

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent_reliability_runtime.evals.contracts import TrialResult
from agent_reliability_runtime.evals.scenarios import load_scenarios, lockfile_digests
from agent_reliability_runtime.observability import canonical
from agent_reliability_runtime.replay import locked_validate

GATES = (
    "L0_SCHEMA_MECHANISM",
    "L1_RETRIEVAL",
    "L2_TRAJECTORY",
    "L3_ENVIRONMENT",
    "L4_ANSWER_QUALITY",
    "HARD_INVARIANTS",
    "TASK_SUCCESS",
)


def validate_receipt(receipt: dict[str, Any], subject_sha: str) -> str:
    locked_validate(receipt, "acceptance_receipt")
    _, digest = load_scenarios()
    if (
        not re.fullmatch(r"[0-9a-f]{40}", subject_sha)
        or receipt["git_sha"] != subject_sha
    ):
        raise ValueError("receipt subject SHA mismatch")
    if (
        receipt["scenario_set_digest"] != digest
        or receipt["lockfile_digests"] != lockfile_digests()
    ):
        raise ValueError("receipt scenario/lock binding mismatch")
    gates = receipt["gates"]
    if set(gates) != set(GATES) or not set(gates.values()) <= {
        "PASS",
        "NOT_APPLICABLE",
    }:
        raise ValueError("receipt trial gate profile mismatch")
    if any(
        gates[g] != "PASS"
        for g in (
            "L0_SCHEMA_MECHANISM",
            "L2_TRAJECTORY",
            "L3_ENVIRONMENT",
            "HARD_INVARIANTS",
            "TASK_SUCCESS",
        )
    ):
        raise ValueError("required objective trial gates must pass")
    try:
        at = datetime.fromisoformat(receipt["created_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("receipt timestamp malformed") from error
    offset = at.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("receipt timestamp must be UTC")
    return hashlib.sha256(canonical(receipt)).hexdigest()


def make_receipt(
    result: TrialResult, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> dict[str, Any]:
    # Revalidate snapshots; model_copy is not a validation boundary.
    result = TrialResult.model_validate(result.model_dump())
    if not result.task_success or not result.hard_invariants_passed:
        raise ValueError("failed trial cannot issue accepted receipt")
    if result.scenario_id not in {s.id for s in load_scenarios()[0]}:
        raise ValueError("unknown trial scenario")
    at = clock()
    if at.utcoffset() is None:
        raise ValueError("receipt clock must be timezone-aware")
    _, digest = load_scenarios()
    gates = {
        gate: layer.status for gate, layer in zip(GATES[:5], result.layers, strict=True)
    }
    receipt = {
        "schema_version": "1.0",
        "git_sha": result.subject_sha,
        "scenario_set_digest": digest,
        "lockfile_digests": lockfile_digests(),
        "gates": gates | {"HARD_INVARIANTS": "PASS", "TASK_SUCCESS": "PASS"},
        "created_at": at.astimezone(UTC).isoformat(),
    }
    validate_receipt(receipt, result.subject_sha)
    return receipt
