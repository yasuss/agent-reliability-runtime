"""Eval authority, measurement sensitivity and strict canonical receipt profile."""

import json
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_reliability_runtime.evals.calibration import calibrate, controls, replace
from agent_reliability_runtime.evals.contracts import (
    AnswerQualityReview,
    TrialEvidence,
    TrialResult,
)
from agent_reliability_runtime.evals.harness import evaluate
from agent_reliability_runtime.evals.receipts import make_receipt, validate_receipt
from agent_reliability_runtime.evals.scenarios import (
    IDS,
    RELATIVE,
    ROOT,
    load_scenarios,
    lockfile_digests,
)
from agent_reliability_runtime.replay import (
    accepted_receipt,
    export_replay,
    locked_validate,
)


def good_receipt() -> dict[str, Any]:
    evidence, expected = controls("a" * 40)
    result = evaluate(load_scenarios()[0][8], evidence, expected)
    return make_receipt(result, lambda: datetime(2026, 10, 4, tzinfo=UTC))


def test_exact_scenarios_digest_copy_and_byte_mutation(tmp_path: Path) -> None:
    definitions, digest = load_scenarios()
    assert tuple(s.id for s in definitions) == IDS
    assert len({s.id for s in definitions}) == 12
    assert digest == "ad14a89fb5816f2eea2ab700394df4b231191cb466e4b326437d035e34f475f9"
    shutil.copytree(ROOT / RELATIVE, tmp_path / RELATIVE)
    assert load_scenarios(tmp_path)[1] == digest
    path = tmp_path / RELATIVE / (IDS[0] + ".json")
    path.write_bytes(path.read_bytes() + b"\n")
    assert load_scenarios(tmp_path)[1] != digest
    obj = json.loads(path.read_bytes())
    obj = dict(reversed(list(obj.items())))
    path.write_text(json.dumps(obj))
    assert load_scenarios(tmp_path)[0][0] == definitions[0]
    assert lockfile_digests() == lockfile_digests()


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "extra",
        "duplicate",
        "boolean",
        "pattern",
        "extra_field",
        "unknown_entry",
    ],
)
def test_loader_fails_closed(tmp_path: Path, defect: str) -> None:
    shutil.copytree(ROOT / RELATIVE, tmp_path / RELATIVE)
    path = tmp_path / RELATIVE / (IDS[0] + ".json")
    obj = json.loads(path.read_bytes())
    if defect == "missing":
        path.unlink()
    elif defect == "extra":
        (path.parent / "extra.json").write_text(json.dumps(obj))
    elif defect == "unknown_entry":
        (path.parent / "directory").mkdir()
    else:
        if defect == "duplicate":
            obj["id"] = IDS[1]
        elif defect == "boolean":
            obj["model_required"] = 1
        elif defect == "pattern":
            obj["id"] = "invalid"
        elif defect == "extra_field":
            obj["unexpected"] = True
        path.write_text(json.dumps(obj))
    with pytest.raises(ValueError):
        load_scenarios(tmp_path)


def test_all_calibrations_and_mandatory_meta_defects() -> None:
    report = calibrate("a" * 40)
    assert report.passed
    assert {
        "approval_exactness",
        "duplicate_effect",
        "citation_subset",
        "secret_replay",
    } <= {c.checker for c in report.cases}
    assert all(
        c.good_passed and c.broken_failed_for_reason and c.alternate_passed
        for c in report.cases
    )
    assert report == calibrate("a" * 40)


def test_hard_precedence_review_and_expected_failure() -> None:
    scenarios, _ = load_scenarios()
    e, x = controls("a" * 40)
    bad = replace(e, physical_effect_counts={e.receipts[0].logical_identity: 2})
    result = evaluate(scenarios[8], bad, x)
    assert (
        result.layers[-1].status == "PASS"
        and "duplicate_effect" in result.hard_invariant_failures
    )
    assert not result.task_success and not result.hard_invariants_passed
    with pytest.raises(ValueError):
        make_receipt(result)
    with pytest.raises(ValueError):
        TrialResult.model_validate(result.model_dump() | {"task_success": True})
    unreviewed = evaluate(scenarios[8], replace(e, review=None), x)
    assert unreviewed.review_state == "NOT_REVIEWED" and not unreviewed.task_success
    with pytest.raises(ValueError):
        make_receipt(unreviewed)
    review = AnswerQualityReview(
        task_addressed="FAIL",
        evidence_grounded="PASS",
        material_uncertainty_surfaced="PASS",
        citations_useful="PASS",
        reviewer="human",
    )
    quality_bad = evaluate(scenarios[8], replace(e, review=review), x)
    assert quality_bad.hard_invariants_passed and not quality_bad.task_success
    assert "task_addressed" in quality_bad.failed_checks
    with pytest.raises(ValidationError):
        AnswerQualityReview(
            task_addressed="PASS",
            evidence_grounded="PASS",
            material_uncertainty_surfaced="PASS",
            citations_useful="PASS",
        )
    provider = replace(
        e,
        scenario_id=IDS[11],
        actions=[],
        approvals=[],
        trajectory=[],
        receipts=[],
        physical_effect_counts={},
        before={},
        after={},
        terminal_status="FAILED",
        replay_json=None,
    )
    expected = x.model_copy(
        update={
            "retrieval_applies": False,
            "answer_quality_applies": False,
            "expected_mutations": {},
            "expected_effects": 0,
            "required_tools": [],
            "required_approval_states": [],
            "terminal_statuses": ["FAILED"],
        }
    )
    failure_result = evaluate(scenarios[11], provider, expected)
    assert (
        failure_result.task_success
        and failure_result.layers[1].status == "NOT_APPLICABLE"
    )
    assert failure_result.layers[4].status == "NOT_APPLICABLE"
    receipt = make_receipt(failure_result, lambda: datetime(2026, 10, 4, tzinfo=UTC))
    assert (
        receipt["gates"]["L1_RETRIEVAL"]
        == receipt["gates"]["L4_ANSWER_QUALITY"]
        == "NOT_APPLICABLE"
    )
    validate_receipt(receipt, "a" * 40)


@pytest.mark.parametrize(
    "defect",
    [
        "weak",
        "sha",
        "scenario",
        "lock",
        "missing_gate",
        "fail",
        "not_run",
        "hard_na",
        "task_na",
        "empty_time",
        "naive_time",
        "wrong_offset",
    ],
)
def test_receipt_rejection_before_any_export_access(
    tmp_path: Path, defect: str
) -> None:
    receipt = deepcopy(good_receipt())
    if defect == "weak":
        receipt["gates"] = {"arbitrary": "PASS"}
    elif defect == "sha":
        receipt["git_sha"] = "b" * 40
    elif defect == "scenario":
        receipt["scenario_set_digest"] = "b" * 64
    elif defect == "lock":
        receipt["lockfile_digests"]["uv.lock"] = "c" * 64
    elif defect == "missing_gate":
        receipt["gates"].pop("L2_TRAJECTORY")
    elif defect in {"fail", "not_run"}:
        receipt["gates"]["L1_RETRIEVAL"] = "FAIL" if defect == "fail" else "NOT_RUN"
    elif defect in {"hard_na", "task_na"}:
        receipt["gates"][
            "HARD_INVARIANTS" if defect == "hard_na" else "TASK_SUCCESS"
        ] = "NOT_APPLICABLE"
    elif defect == "empty_time":
        receipt["created_at"] = ""
    elif defect == "naive_time":
        receipt["created_at"] = "2026-10-04T00:00:00"
    elif defect == "wrong_offset":
        receipt["created_at"] = "2026-10-04T00:00:00+01:00"
    locked_validate(receipt, "acceptance_receipt")
    with pytest.raises(ValueError):
        accepted_receipt(receipt, "a" * 40)
    # Invalid canonical profile must reject before touching a DB or writing files.
    from sqlalchemy import create_engine

    with pytest.raises(ValueError):
        export_replay(
            create_engine("sqlite://"), "r", receipt, "a" * 40, tmp_path / "out.json"
        )
    assert list(tmp_path.iterdir()) == []


def test_receipt_deterministic_clock_and_profile() -> None:
    first = good_receipt()
    assert first == good_receipt()
    validate_receipt(first, "a" * 40)
    other = first | {"created_at": "2026-10-04T00:00:01Z"}
    assert validate_receipt(first, "a" * 40) != validate_receipt(other, "a" * 40)


def test_cli_real_determinism_and_failure_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    command = [
        sys.executable,
        "-m",
        "agent_reliability_runtime.cli",
        "eval",
        "--calibrate",
    ]
    first = subprocess.run(
        command, cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    second = subprocess.run(
        command, cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    assert first == second and json.loads(first)["passed"] is True
    monkeypatch.setattr(
        "agent_reliability_runtime.evals.checkers.approval_exactness",
        lambda evidence: True,
    )
    # Mutate the actual oracle to accept approval bypass. Production calibration
    # must detect the missing intended failure and make the CLI exit nonzero.
    assert not calibrate("a" * 40).passed
    monkeypatch.setattr(
        sys,
        "argv",
        ["arr", "eval", "--calibrate", "--output", str(tmp_path / "bad.json")],
    )
    from agent_reliability_runtime.cli import main

    with pytest.raises(SystemExit) as stopped:
        main()
    assert (
        stopped.value.code == 1
        and json.loads(capsys.readouterr().out)["passed"] is False
    )


def test_evidence_bounds_no_raw_secret_or_hidden_reasoning() -> None:
    evidence, _ = controls("a" * 40)
    with pytest.raises(ValueError):
        replace(evidence, final_answer="x" * 2049)
    with pytest.raises(ValueError):
        replace(evidence, final_answer="ARR_" + "FORBIDDEN_SECRET_raw")
    with pytest.raises(ValueError):
        TrialEvidence.model_validate(evidence.model_dump() | {"reasoning": "hidden"})


def test_partial_order_alternate_read_and_exact_approval_binding() -> None:
    from agent_reliability_runtime.evals.contracts import Step

    e, x = controls("a" * 40)
    scenario = load_scenarios()[0][8]
    x = x.model_copy(
        update={"partial_order": [("approval.waiting", "approval.resumed")]}
    )
    valid = replace(
        e,
        trajectory=[
            e.trajectory[0],
            Step(sequence=2, event_type="tool.completed", tool_name="get_incident"),
            e.trajectory[1].model_copy(update={"sequence": 3}),
            e.trajectory[2].model_copy(update={"sequence": 4}),
        ],
        tool_steps=2,
    )
    assert evaluate(scenario, valid, x).task_success
    drift = e.approvals[0].model_copy(
        update={"action": e.actions[0].model_copy(update={"args_digest": "b" * 64})}
    )
    assert (
        "approval_exactness"
        in evaluate(scenario, replace(e, approvals=[drift]), x).hard_invariant_failures
    )
    assert (
        "duplicate_effect"
        in evaluate(
            scenario, replace(e, receipts=e.receipts * 2), x
        ).hard_invariant_failures
    )
    reordered = [
        e.trajectory[1].model_copy(update={"sequence": 1}),
        e.trajectory[0].model_copy(update={"sequence": 2}),
        e.trajectory[2],
    ]
    assert (
        "trajectory_constraints"
        in evaluate(
            scenario, replace(e, trajectory=reordered), x
        ).hard_invariant_failures
    )
    bad_digest = replace(e, current_document_digests={})
    assert "stale_digest" in evaluate(scenario, bad_digest, x).hard_invariant_failures
    disguised = replace(
        e,
        trajectory=e.trajectory[:-1]
        + [e.trajectory[-1].model_copy(update={"tool_name": "get_incident"})],
    )
    assert (
        "approval_exactness" in evaluate(scenario, disguised, x).hard_invariant_failures
    )
    assert evaluate(
        scenario,
        replace(e, model_steps=12),
        x.model_copy(update={"max_model_steps": 12}),
    ).task_success
    with pytest.raises(ValueError):
        evaluate(scenario, e, x.model_copy(update={"max_model_steps": 13}))


def test_malformed_result_and_review_projections() -> None:
    from agent_reliability_runtime.evals.contracts import LayerResult

    e, x = controls("a" * 40)
    result = evaluate(load_scenarios()[0][8], e, x)
    with pytest.raises(ValueError):
        LayerResult(layer="L0", status="PASS", checks=[])
    with pytest.raises(ValueError):
        TrialResult.model_validate(result.model_dump() | {"review_state": "FAIL"})
    with pytest.raises(ValueError):
        TrialResult.model_validate(result.model_dump() | {"task_success": False})


def test_cli_rejects_oracle_that_rejects_valid_alternate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent_reliability_runtime.evals.checkers.approval_exactness",
        lambda evidence: False,
    )
    assert not calibrate("a" * 40).passed
    monkeypatch.setattr(sys, "argv", ["arr", "eval", "--calibrate"])
    from agent_reliability_runtime.cli import main

    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 1


def test_locked_subject_tool_attempt_and_receipt_identity_consistency() -> None:
    from agent_reliability_runtime.evals.contracts import Step

    e, x = controls("a" * 40)
    scenario = load_scenarios()[0][8]
    changed = scenario.model_copy(update={"input": {"task": "different task"}})
    assert "trial_identity" in evaluate(changed, e, x).hard_invariant_failures
    foreign = replace(
        e, receipts=[e.receipts[0].model_copy(update={"logical_identity": "b" * 64})]
    )
    assert "effect_identity" in evaluate(scenario, foreign, x).hard_invariant_failures
    unknown = replace(
        e,
        trajectory=e.trajectory
        + [Step(sequence=4, event_type="tool.failed", tool_name="unknown_tool")],
    )
    assert "action_schema" in evaluate(scenario, unknown, x).hard_invariant_failures
    attempted = replace(
        e,
        trajectory=e.trajectory
        + [Step(sequence=4, event_type="tool.failed", tool_name="restart_service")],
    )
    assert (
        "forbidden_tools"
        in evaluate(
            scenario,
            attempted,
            x.model_copy(update={"forbidden_tools": ["restart_service"]}),
        ).hard_invariant_failures
    )
    result = evaluate(scenario, e, x)
    with pytest.raises(ValueError):
        make_receipt(result.model_copy(update={"scenario_id": "S99_FOREIGN"}))
