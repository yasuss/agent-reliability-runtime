"""Sensitive-value and exact locked-schema checker sensitivity."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from agent_reliability_runtime.observability import canonical, public_safe, sanitize
from agent_reliability_runtime.replay import (
    accepted_receipt,
    locked_validate,
    write_candidate,
)


def receipt() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "git_sha": "a" * 40,
        "scenario_set_digest": "b" * 64,
        "lockfile_digests": {"uv": "c" * 64},
        "gates": {"fixture": "PASS", "other": "NOT_APPLICABLE"},
        "created_at": "fixture",
    }


def replay() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "r",
        "scenario_id": "S01",
        "mode": "recorded_acceptance_replay",
        "source_git_sha": "a" * 40,
        "eval_receipt_digest": "b" * 64,
        "events": [
            {
                "seq": 1,
                "type": "request",
                "summary": "safe",
                "data": {"nested": [1, True]},
            }
        ],
        "final_status": "COMPLETED",
    }


def test_redaction_public_checker_and_valid_alternate() -> None:
    marker = "ARR_" + "FORBIDDEN_SECRET_fixture"
    raw = {
        "Authorization": "Bearer fake",
        "nested": {"password": "x", "idempotency_key": "key"},
        "message": marker + " sk-fixtureSecret http://user:password@host/path",
        "messages": ["raw prompt"],
        "digest": "a" * 64,
        "usage": {"input_tokens": 3},
    }
    safe = sanitize(raw)
    assert safe["Authorization"] == "[REDACTED]" and safe["messages"] == "[REDACTED]"
    assert safe["usage"]["input_tokens"] == 3 and safe["digest"] == "a" * 64
    public_safe(canonical(safe))
    with pytest.raises(ValueError):
        public_safe(canonical(raw))
    public_safe(canonical(dict(reversed(list(safe.items())))))
    assert len(sanitize("a" * 3000)) == 2048
    with pytest.raises(ValueError):
        public_safe(canonical({"password": "unpatterned-value"}))


@pytest.mark.parametrize(
    "bad",
    [
        "missing",
        "extra",
        "sha",
        "status",
        "seq",
        "receipt_extra",
        "receipt_digest",
        "fail",
        "not_run",
        "empty",
        "no_pass",
        "sha_mismatch",
    ],
)
def test_locked_schema_and_receipt_failures(bad: str) -> None:
    candidate = replay()
    evidence = receipt()
    with pytest.raises(ValueError):
        if bad == "missing":
            candidate.pop("run_id")
            locked_validate(candidate, "replay")
        elif bad == "extra":
            candidate["extra"] = True
            locked_validate(candidate, "replay")
        elif bad == "sha":
            candidate["source_git_sha"] = "wrong"
            locked_validate(candidate, "replay")
        elif bad == "status":
            candidate["final_status"] = "RUNNING"
            locked_validate(candidate, "replay")
        elif bad == "seq":
            candidate["events"][0]["seq"] = True
            locked_validate(candidate, "replay")
        else:
            if bad == "receipt_extra":
                evidence["extra"] = True
            elif bad == "receipt_digest":
                evidence["lockfile_digests"]["uv"] = "wrong"
            elif bad in {"fail", "not_run"}:
                evidence["gates"]["fixture"] = "FAIL" if bad == "fail" else "NOT_RUN"
            elif bad == "empty":
                evidence["gates"] = {}
            elif bad == "no_pass":
                evidence["gates"] = {"x": "NOT_APPLICABLE"}
            accepted_receipt(evidence, "f" * 40 if bad == "sha_mismatch" else "a" * 40)


def test_schema_alternate_and_unsafe_artifact_no_write(tmp_path: Path) -> None:
    good = replay()
    locked_validate(good, "replay")
    accepted_receipt(receipt(), "a" * 40)
    alternate = deepcopy(good)
    alternate["final_status"] = "REJECTED"
    alternate["events"][0]["data"] = {"arbitrary_safe": {}}
    locked_validate(alternate, "replay")
    bad = deepcopy(good)
    bad["events"][0]["summary"] = "ARR_" + "FORBIDDEN_SECRET_calibration"
    output = tmp_path / "unsafe.json"
    with pytest.raises(ValueError):
        write_candidate(bad, {"source_run_id": "r"}, output)
    assert list(tmp_path.iterdir()) == []
