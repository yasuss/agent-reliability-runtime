"""R9 eval/review harness invariants without live model calls."""

import json
from pathlib import Path

import pytest

from agent_reliability_runtime.evals.calibration import controls
from agent_reliability_runtime.evals.campaign import (
    POPULATION,
    aggregate,
    next_trial,
    write_once,
)
from agent_reliability_runtime.evals.harness import evaluate
from agent_reliability_runtime.evals.l4_review import (
    build_review_packet,
    calibrate_l4,
)
from agent_reliability_runtime.evals.scenarios import load_scenarios


def test_r9_ids_and_first_four_fail_still_reach_fifteen(tmp_path: Path) -> None:
    assert len(POPULATION) == 15
    assert all("-r9-" in item["trial_id"] for item in POPULATION)
    for item in POPULATION[:4]:
        path = tmp_path / item["trial_id"]
        path.mkdir()
        write_once(path / "started.json", item)
        write_once(
            path / "verdict.json",
            item
            | {
                "subject_sha": "a" * 40,
                "task_success": False,
                "hard_invariant_failures": ["fixture_failure"],
                "unauthorized_effects": 0,
                "duplicate_physical_effects": 0,
            },
        )
    assert next_trial(tmp_path) == POPULATION[4]


def test_pending_review_does_not_block_next_trial(tmp_path: Path) -> None:
    path = tmp_path / POPULATION[0]["trial_id"]
    path.mkdir()
    write_once(path / "started.json", POPULATION[0])
    write_once(path / "execution-sealed.json", {"state": "EXECUTION_SEALED"})
    write_once(path / "awaiting-review.json", {"state": "AWAITING_REVIEW"})
    assert next_trial(tmp_path) == POPULATION[1]


def test_aggregate_requires_exact_fifteen() -> None:
    with pytest.raises(ValueError, match="exact 15"):
        aggregate([])


def test_l4_calibration_and_bounded_packet(tmp_path: Path) -> None:
    calibration = calibrate_l4()
    assert calibration["passed"] and calibration["exact_match"]
    definitions, _ = load_scenarios()
    evidence, expected = controls("a" * 40)
    objective = evaluate(definitions[8], evidence, expected)
    packet = build_review_packet(
        definition=definitions[8],
        evidence=evidence,
        expectations=expected,
        objective=objective,
        proof={"read_observations": [{"tool_name": "get_service_status"}]},
        output=tmp_path,
    )
    value = json.loads(Path(packet).read_bytes())
    assert value["task"]
    assert value["rubric"]["citations_useful"]
    assert value["read_observations"]
    assert "reasoning" not in json.dumps(value).lower()
