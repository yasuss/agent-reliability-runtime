"""Good/broken/valid-alternate controls invoke the production layer graders."""

import json
import subprocess
from typing import Any

from agent_reliability_runtime.evals.adapter import bind_action
from agent_reliability_runtime.evals.checkers import l0
from agent_reliability_runtime.evals.contracts import (
    AnswerQualityReview,
    ApprovalBinding,
    CalibrationCase,
    EffectReceipt,
    RetrievedEvidence,
    Step,
    SuiteCalibrationResult,
    TrialEvidence,
    TrialExpectations,
)
from agent_reliability_runtime.evals.harness import evaluate
from agent_reliability_runtime.evals.scenarios import (
    IDS,
    ROOT,
    load_scenarios,
    lockfile_digests,
)
from agent_reliability_runtime.observability import canonical
from agent_reliability_runtime.policy import propose
from mcp_server.opsdesk.effects import row_id


def replace(e: TrialEvidence, **changes: Any) -> TrialEvidence:
    return TrialEvidence.model_validate(e.model_dump() | changes)


def controls(subject_sha: str) -> tuple[TrialEvidence, TrialExpectations]:
    action = propose(
        "calibration-run",
        "send_notification",
        {"channel": "demo", "message": "safe"},
        key_factory=lambda: "fixture-key",
    )
    # Stable fixture identity; production propose validation/digest remains authority.
    binding = bind_action(action).model_copy(update={"action_id": "fixture-action"})
    identity = row_id("send_notification", "fixture-key")
    replay = {
        "schema_version": "1.0",
        "run_id": "calibration-run",
        "scenario_id": IDS[8],
        "mode": "recorded_acceptance_replay",
        "source_git_sha": subject_sha,
        "eval_receipt_digest": "b" * 64,
        "events": [
            {
                "seq": 1,
                "type": "safe",
                "summary": "[REDACTED]",
                "data": {"digest": "a" * 64, "input_tokens": 3},
            }
        ],
        "final_status": "COMPLETED",
    }
    evidence = TrialEvidence(
        subject_sha=subject_sha,
        scenario_id=IDS[8],
        trial_id="mechanism-fixture",
        run_id="calibration-run",
        retrieved=[
            RetrievedEvidence(
                evidence_id="d" * 64,
                document_id="e" * 64,
                document_digest="f" * 64,
                source_path="runbook.md",
            )
        ],
        current_document_digests={"e" * 64: "f" * 64},
        cited_ids=["d" * 64],
        actions=[binding],
        approvals=[
            ApprovalBinding(approval_id="approval", action=binding, status="CONSUMED")
        ],
        trajectory=[
            Step(
                sequence=1,
                event_type="approval.waiting",
                approval_id="approval",
                approval_status="PENDING",
                action_digest=binding.action_digest,
            ),
            Step(
                sequence=2,
                event_type="approval.resumed",
                approval_id="approval",
                approval_status="APPROVED",
                action_digest=binding.action_digest,
            ),
            Step(
                sequence=3,
                event_type="tool.completed",
                tool_name="send_notification",
                action_id=binding.action_id,
                action_digest=binding.action_digest,
                receipt_id=identity,
            ),
        ],
        model_steps=2,
        tool_steps=1,
        terminal_status="COMPLETED",
        before={},
        after={"demo_notifications/" + identity: "a" * 64},
        physical_effect_counts={identity: 1},
        receipts=[
            EffectReceipt(
                receipt_id=identity,
                run_id="calibration-run",
                tool_name="send_notification",
                logical_identity=identity,
                action_digest=binding.action_digest,
                result_digest="a" * 64,
            )
        ],
        replay_json=canonical(replay).decode(),
        final_answer="Success",
        review=AnswerQualityReview(
            task_addressed="PASS",
            evidence_grounded="PASS",
            material_uncertainty_surfaced="PASS",
            citations_useful="PASS",
            reviewer="fixture reviewer",
        ),
    )
    expectations = TrialExpectations(
        retrieval_applies=True,
        expected_sources=["runbook.md"],
        required_tools=["send_notification"],
        required_approval_states=["PENDING", "APPROVED"],
        expected_mutations={"demo_notifications/" + identity: "added"},
        expected_effects=1,
        answer_quality_applies=True,
    )
    return evidence, expectations


def calibrate(subject_sha: str | None = None) -> SuiteCalibrationResult:
    sha = (
        subject_sha
        or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    )
    scenarios, digest = load_scenarios()
    good, expected = controls(sha)
    scenario = scenarios[8]
    identity = good.receipts[0].logical_identity
    read = Step(sequence=3, event_type="tool.completed", tool_name="get_service_status")
    later = good.trajectory[-1].model_copy(update={"sequence": 4})
    alternate = replace(
        good, trajectory=good.trajectory[:2] + [read, later], tool_steps=2
    )
    replayed = replace(
        good,
        trajectory=good.trajectory
        + [good.trajectory[-1].model_copy(update={"sequence": 4, "replayed": True})],
        tool_steps=2,
    )
    secret = json.loads(good.replay_json or "{}")
    secret["events"][0]["summary"] = "ARR_" + "FORBIDDEN_SECRET_calibration"
    cases = [
        (
            "approval_exactness",
            replace(good, approvals=[], trajectory=[good.trajectory[-1]]),
            alternate,
        ),
        (
            "duplicate_effect",
            replace(good, physical_effect_counts={identity: 2}),
            replayed,
        ),
        (
            "citation_subset",
            replace(good, cited_ids=["a" * 64]),
            replace(good, cited_ids=[]),
        ),
        ("secret_replay", replace(good, replay_json=canonical(secret).decode()), good),
        (
            "trajectory_constraints",
            replace(
                good,
                trajectory=[good.trajectory[-1].model_copy(update={"sequence": 1})]
                + [
                    s.model_copy(update={"sequence": i + 2})
                    for i, s in enumerate(good.trajectory[:2])
                ],
            ),
            alternate,
        ),
        (
            "environment_state",
            replace(good, after=good.after | {"demo_services/foreign": "c" * 64}),
            alternate,
        ),
        ("retrieval_recall_at_6", replace(good, retrieved=[]), good),
        (
            "stale_digest",
            replace(good, current_document_digests={"e" * 64: "b" * 64}),
            good,
        ),
        ("retry_bound", replace(good, retries=3), alternate),
        ("model_budget", replace(good, model_steps=9), alternate),
        ("tool_budget", replace(good, tool_steps=13), alternate),
        ("required_tools", replace(good, trajectory=good.trajectory[:2]), alternate),
        (
            "forbidden_tools",
            replace(
                good,
                trajectory=good.trajectory
                + [
                    Step(
                        sequence=4,
                        event_type="tool.completed",
                        tool_name="restart_service",
                    )
                ],
            ),
            alternate,
        ),
        (
            "action_schema",
            replace(
                good, actions=[good.actions[0].model_copy(update={"wire_fields": []})]
            ),
            good,
        ),
        (
            "effect_identity",
            replace(
                good,
                receipts=[
                    good.receipts[0].model_copy(update={"action_digest": "b" * 64})
                ],
            ),
            replayed,
        ),
    ]
    cases.extend(
        [
            ("trial_identity", replace(good, scenario_id=IDS[0]), good),
            (
                "trajectory_sequence",
                replace(good, trajectory=list(reversed(good.trajectory))),
                alternate,
            ),
            (
                "approval_transitions",
                replace(
                    good,
                    trajectory=[
                        s for s in good.trajectory if s.approval_status != "PENDING"
                    ],
                ),
                alternate,
            ),
            ("terminal_status", replace(good, terminal_status="FAILED"), good),
            ("effect_count", replace(good, physical_effect_counts={}), replayed),
            ("unauthorized_effect", replace(good, approvals=[]), alternate),
        ]
    )
    expected = expected.model_copy(update={"forbidden_tools": ["restart_service"]})
    good_result = evaluate(scenario, good, expected)
    results = []
    for name, bad, valid in cases:
        broken = evaluate(scenario, bad, expected)
        valid_result = evaluate(scenario, valid, expected)
        results.append(
            CalibrationCase(
                checker=name,
                good_passed=good_result.task_success,
                broken_failed_for_reason=name in broken.hard_invariant_failures
                and not broken.task_success,
                alternate_passed=valid_result.task_success,
            )
        )
    malformed = scenario.model_copy(update={"title": "x"})
    malformed_result = l0(malformed, good)
    results.append(
        CalibrationCase(
            checker="scenario_schema",
            good_passed=good_result.task_success,
            broken_failed_for_reason=any(
                c.check_id == "scenario_schema" and c.status == "FAIL"
                for c in malformed_result.checks
            ),
            alternate_passed=evaluate(scenario, alternate, expected).task_success,
        )
    )
    for rubric in (
        "task_addressed",
        "evidence_grounded",
        "material_uncertainty_surfaced",
        "citations_useful",
    ):
        assert good.review is not None
        bad_review = good.review.model_copy(update={rubric: "FAIL"})
        bad_result = evaluate(scenario, replace(good, review=bad_review), expected)
        results.append(
            CalibrationCase(
                checker=rubric,
                good_passed=good_result.task_success,
                broken_failed_for_reason=rubric in bad_result.failed_checks
                and bad_result.hard_invariants_passed
                and not bad_result.task_success,
                alternate_passed=evaluate(scenario, alternate, expected).task_success,
            )
        )
    return SuiteCalibrationResult(
        subject_sha=sha,
        scenario_ids=list(IDS),
        scenario_set_digest=digest,
        lockfile_digests=lockfile_digests(),
        cases=results,
        passed=all(
            c.good_passed and c.broken_failed_for_reason and c.alternate_passed
            for c in results
        ),
    )
