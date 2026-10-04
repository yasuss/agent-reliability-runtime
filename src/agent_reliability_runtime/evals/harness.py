"""Layer aggregation: safety and objective outcomes precede prose."""

from agent_reliability_runtime.evals import checkers
from agent_reliability_runtime.evals.contracts import (
    ScenarioDefinition,
    TrialEvidence,
    TrialExpectations,
    TrialResult,
)


def evaluate(
    scenario: ScenarioDefinition,
    evidence: TrialEvidence,
    expectations: TrialExpectations,
) -> TrialResult:
    scenario = ScenarioDefinition.model_validate(scenario.model_dump())
    evidence = TrialEvidence.model_validate(evidence.model_dump())
    expectations = TrialExpectations.model_validate(expectations.model_dump())
    layers = [
        checkers.l0(scenario, evidence),
        checkers.l1(evidence, expectations),
        checkers.l2(evidence, expectations),
        checkers.l3(evidence, expectations),
        checkers.l4(evidence, expectations),
    ]
    failed = [
        c.check_id for layer in layers for c in layer.checks if c.status == "FAIL"
    ]
    hard = [
        c.check_id
        for layer in layers
        for c in layer.checks
        if c.status == "FAIL" and c.hard
    ]
    return TrialResult(
        subject_sha=evidence.subject_sha,
        scenario_id=evidence.scenario_id,
        trial_id=evidence.trial_id,
        run_id=evidence.run_id,
        layers=layers,
        failed_checks=failed,
        hard_invariant_failures=hard,
        hard_invariants_passed=not hard,
        task_success=not failed
        and all(item.status in {"PASS", "NOT_APPLICABLE"} for item in layers),
        review_state=layers[-1].status,
    )
