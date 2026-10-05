"""R10 postcondition and S02 semantic partial-order calibration."""

from agent_reliability_runtime.evals.contracts import ActionBinding, Step, TrialEvidence
from agent_reliability_runtime.evals.s02_semantics import (
    INCIDENT_DIGEST,
    STATUS_DIGEST,
    s02_action_constraints,
)
from agent_reliability_runtime.runtime.postconditions import (
    restart_obligation,
    satisfies,
)


def evidence(names: list[tuple[str, str]]) -> TrialEvidence:
    actions = []
    steps = []
    for index, (name, digest) in enumerate(names, start=1):
        action_id = f"action-{index}"
        actions.append(
            ActionBinding(
                run_id="run",
                action_id=action_id,
                tool_name=name,
                policy_version="opsdesk-v1",
                action_digest="a" * 64,
                args_digest=digest,
                wire_fields=[],
                schema_valid=True,
            )
        )
        steps.append(
            Step(
                sequence=index,
                event_type="tool.completed",
                tool_name=name,
                action_id=action_id,
                action_digest="a" * 64,
            )
        )
    return TrialEvidence(
        subject_sha="a" * 40,
        scenario_id="S02_APPROVAL_REQUIRED",
        trial_id="trial",
        run_id="run",
        actions=actions,
        trajectory=steps,
        terminal_status="COMPLETED",
    )


def test_s02_allows_both_prerequisite_orders() -> None:
    assert s02_action_constraints(
        evidence(
            [
                ("get_incident", INCIDENT_DIGEST),
                ("get_service_status", STATUS_DIGEST),
                ("restart_service", "b" * 64),
                ("get_service_status", STATUS_DIGEST),
            ]
        )
    )
    assert s02_action_constraints(
        evidence(
            [
                ("get_service_status", STATUS_DIGEST),
                ("get_incident", INCIDENT_DIGEST),
                ("restart_service", "b" * 64),
                ("get_service_status", STATUS_DIGEST),
            ]
        )
    )


def test_s02_rejects_missing_or_wrong_order_constraints() -> None:
    assert not s02_action_constraints(
        evidence(
            [
                ("get_incident", INCIDENT_DIGEST),
                ("restart_service", "b" * 64),
                ("get_service_status", STATUS_DIGEST),
            ]
        )
    )
    assert not s02_action_constraints(
        evidence(
            [
                ("get_service_status", STATUS_DIGEST),
                ("get_incident", INCIDENT_DIGEST),
                ("restart_service", "b" * 64),
                ("get_service_status", INCIDENT_DIGEST),
            ]
        )
    )
    assert not s02_action_constraints(
        evidence(
            [
                ("get_incident", INCIDENT_DIGEST),
                ("get_service_status", STATUS_DIGEST),
                ("restart_service", "b" * 64),
                ("restart_service", "c" * 64),
                ("get_service_status", STATUS_DIGEST),
            ]
        )
    )


def test_restart_obligation_is_exact_and_never_auto_executes() -> None:
    action = {
        "tool_name": "restart_service",
        "action_id": "restart-action",
        "normalized_args": {"service_id": "synthetic-service", "reason": "test"},
    }
    obligation = restart_obligation(action, 4)
    assert obligation is not None
    assert not satisfies(
        obligation,
        tool_name="get_service_status",
        arguments={"service_id": "synthetic-service"},
        effect_sequence=4,
        result={"service_id": "synthetic-service"},
    )
    assert not satisfies(
        obligation,
        tool_name="get_service_status",
        arguments={"service_id": "other-service"},
        effect_sequence=5,
        result={"service_id": "other-service"},
    )
    assert satisfies(
        obligation,
        tool_name="get_service_status",
        arguments={"service_id": "synthetic-service"},
        effect_sequence=5,
        result={"service_id": "synthetic-service", "status": "healthy"},
    )
