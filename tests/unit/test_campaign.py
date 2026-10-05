"""G8 population/per-case/hard precedence and immutable failure calibration."""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent_reliability_runtime.evals.campaign import (
    CASES,
    POPULATION,
    aggregate,
    next_trial,
    write_once,
)


def test_drift_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_reliability_runtime.evals import campaign

    identity = {
        "subject_sha": "a" * 40,
        "scenario_set_digest": "b" * 64,
        "lockfile_digests": {},
    }
    models = {
        "chat_digest": campaign.CHAT_DIGEST,
        "embedding_digest": campaign.EMBED_DIGEST,
        "ollama_version": "0.35.1",
    }
    config = campaign.configuration()
    import hashlib

    from agent_reliability_runtime.observability import canonical

    frozen = (
        identity
        | models
        | {
            "configuration": config,
            "configuration_digest": hashlib.sha256(canonical(config)).hexdigest(),
        }
    )
    campaign.write_once(tmp_path / "freeze.json", frozen)
    campaign.write_once(tmp_path / "knowledge-ready.json", {"ready": True})
    monkeypatch.setattr(campaign, "subject", lambda: identity)
    monkeypatch.setattr(campaign, "models", AsyncMock(return_value=models))
    assert asyncio.run(campaign.revalidate(tmp_path)) == frozen
    monkeypatch.setattr(
        campaign, "models", AsyncMock(return_value=models | {"chat_digest": "0" * 64})
    )
    with pytest.raises(ValueError, match="drift"):
        asyncio.run(campaign.revalidate(tmp_path))
    monkeypatch.setattr(campaign, "models", AsyncMock(return_value=models))
    monkeypatch.setattr(
        campaign, "subject", lambda: identity | {"subject_sha": "c" * 40}
    )
    with pytest.raises(ValueError, match="drift"):
        asyncio.run(campaign.revalidate(tmp_path))
    monkeypatch.setattr(campaign, "subject", lambda: identity)
    assert asyncio.run(campaign.revalidate(tmp_path)) == frozen
    changed = json.loads((tmp_path / "freeze.json").read_bytes())
    changed["configuration"]["temperature"] = 0
    (tmp_path / "freeze.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="drift"):
        asyncio.run(campaign.revalidate(tmp_path))


def test_environment_content_calibration() -> None:
    from agent_reliability_runtime.evals.calibration import controls, replace
    from agent_reliability_runtime.evals.contracts import TrialExpectations
    from agent_reliability_runtime.evals.harness import evaluate
    from agent_reliability_runtime.evals.scenarios import load_scenarios

    evidence, expected = controls("a" * 40)
    expected = TrialExpectations.model_validate(
        expected.model_dump() | {"expected_after_digests": evidence.after}
    )
    scenario = load_scenarios()[0][8]
    assert evaluate(scenario, evidence, expected).task_success
    key = next(iter(evidence.after))
    broken = replace(evidence, after=evidence.after | {key: "0" * 64})
    assert "environment_content" in evaluate(scenario, broken, expected).failed_checks
    assert evaluate(
        scenario,
        replace(evidence, after=dict(reversed(list(evidence.after.items())))),
        expected,
    ).task_success


def verdicts(counts: list[int]) -> list[dict[str, Any]]:
    return [
        dict(
            t,
            subject_sha="a" * 40,
            task_success=(i % 3 < counts[i // 3]),
            hard_invariant_failures=[],
            unauthorized_effects=0,
            duplicate_physical_effects=0,
        )
        for i, t in enumerate(POPULATION)
    ]


def test_action_sequence_calibration() -> None:
    from agent_reliability_runtime.evals.calibration import controls, replace
    from agent_reliability_runtime.evals.contracts import TrialExpectations
    from agent_reliability_runtime.evals.harness import evaluate
    from agent_reliability_runtime.evals.scenarios import load_scenarios

    evidence, expected = controls("a" * 40)
    binding = evidence.actions[0]
    expected = TrialExpectations.model_validate(
        expected.model_dump()
        | {"required_action_sequence": [(binding.tool_name, binding.args_digest)]}
    )
    scenario = load_scenarios()[0][8]
    assert evaluate(scenario, evidence, expected).task_success
    bad = TrialExpectations.model_validate(
        expected.model_dump()
        | {"required_action_sequence": [(binding.tool_name, "0" * 64)]}
    )
    assert "required_action_sequence" in evaluate(scenario, evidence, bad).failed_checks
    assert evaluate(
        scenario, replace(evidence, actions=list(reversed(evidence.actions))), expected
    ).task_success


def test_valid_bounded_retry_alternate() -> None:
    from agent_reliability_runtime.evals.calibration import controls, replace
    from agent_reliability_runtime.evals.execution import expectations
    from agent_reliability_runtime.evals.harness import evaluate
    from agent_reliability_runtime.evals.scenarios import load_scenarios

    scenario = load_scenarios()[0][8]
    evidence, _ = controls("a" * 40)
    expected = expectations(scenario.id, "fixture-key")
    assert evaluate(scenario, evidence, expected).task_success
    assert evaluate(scenario, replace(evidence, retries=1), expected).task_success
    assert (
        "retry_bound"
        in evaluate(scenario, replace(evidence, retries=2), expected).failed_checks
    )
    assert expectations("S07_TRANSIENT_TIMEOUT", "fixture-key").required_retries == 1


def test_g8_calibration() -> None:
    good = verdicts([2, 3, 2, 2, 3])
    assert aggregate(good)["G8"] == "PASS"
    assert aggregate(verdicts([3, 3, 3, 3, 0]))["G8"] == "FAIL"
    broken = verdicts([3, 3, 3, 3, 3])
    broken[0]["hard_invariant_failures"] = ["approval_exactness"]
    assert aggregate(broken)["G8"] == "FAIL"
    alternate = verdicts([3, 2, 3, 2, 2])
    assert aggregate(alternate)["G8"] == "PASS"
    replacement = copy.deepcopy(good)
    replacement[0]["trial_id"] += "-replacement-4"
    with pytest.raises(ValueError, match="population"):
        aggregate(replacement)
    for field in ["unauthorized_effects", "duplicate_physical_effects"]:
        negative = verdicts([3] * 5)
        negative[0][field] = 1
        assert aggregate(negative)["G8"] == "FAIL"


def test_started_failed_trial_never_replaced(tmp_path: Path) -> None:
    trial = next_trial(tmp_path)
    path = tmp_path / trial["trial_id"]
    path.mkdir()
    write_once(path / "started.json", trial)
    # Pending review/sealed execution never blocks the next population member.
    assert next_trial(tmp_path) == POPULATION[1]
    write_once(path / "verdict.json", {"task_success": False})
    assert next_trial(tmp_path) == POPULATION[1]
    with pytest.raises(FileExistsError):
        write_once(path / "verdict.json", {"task_success": True})
    for t in POPULATION[1:]:
        p = tmp_path / t["trial_id"]
        p.mkdir()
        write_once(p / "started.json", t)
        write_once(p / "verdict.json", {"task_success": False})
    with pytest.raises(ValueError, match="replacements forbidden"):
        next_trial(tmp_path)
    assert CASES == tuple(dict.fromkeys(t["scenario_id"] for t in POPULATION))
