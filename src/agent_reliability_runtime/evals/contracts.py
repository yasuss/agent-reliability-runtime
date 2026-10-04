"""Bounded evidence snapshots, objective constraints and review artifacts.

Evidence is measured input, never policy authorization. Raw arguments, credentials
and hidden reasoning are deliberately absent; the adapter validates authoritative
records before projecting digests and schema observations.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from agent_reliability_runtime.contracts.domain import (
    Counter,
    Digest,
    Identifier,
    Record,
)
from agent_reliability_runtime.observability import canonical, public_safe

Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$", strict=True)]
Text = Annotated[str, Field(max_length=2048, strict=True)]
Status = Literal["PASS", "FAIL", "NOT_APPLICABLE", "NOT_REVIEWED"]
Layer = Literal["L0", "L1", "L2", "L3", "L4"]


class ScenarioDefinition(Record):
    id: Identifier
    title: Identifier
    model_required: Annotated[bool, Field(strict=True)]
    input: dict[str, JsonValue]
    faults: list[dict[str, JsonValue]]
    expected_invariants: list[Identifier]
    tags: list[Identifier] = Field(default_factory=list)


class ActionBinding(Record):
    run_id: Identifier
    action_id: Identifier
    tool_name: Identifier
    policy_version: Identifier
    action_digest: Digest
    args_digest: Digest
    wire_fields: list[Identifier]
    schema_valid: Annotated[bool, Field(strict=True)]


class ApprovalBinding(Record):
    approval_id: Identifier
    action: ActionBinding
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "CONSUMED"]


class RetrievedEvidence(Record):
    evidence_id: Digest
    document_id: Digest
    document_digest: Digest
    source_path: Identifier


class Step(Record):
    sequence: Annotated[int, Field(gt=0, strict=True)]
    event_type: Identifier
    tool_name: Identifier | None = None
    action_id: Identifier | None = None
    action_digest: Digest | None = None
    approval_id: Identifier | None = None
    approval_status: Identifier | None = None
    receipt_id: Identifier | None = None
    replayed: Annotated[bool, Field(strict=True)] = False


class EffectReceipt(Record):
    receipt_id: Identifier
    run_id: Identifier
    tool_name: Identifier
    logical_identity: Digest
    action_digest: Digest
    result_digest: Digest


class AnswerQualityReview(Record):
    task_addressed: Status
    evidence_grounded: Status
    material_uncertainty_surfaced: Status
    citations_useful: Status
    reviewer: Text | None = None

    @model_validator(mode="after")
    def attributable(self) -> Self:
        values = list(self.model_dump(exclude={"reviewer"}).values())
        if any(v in {"PASS", "FAIL"} for v in values) and not self.reviewer:
            raise ValueError("reviewed rubric requires reviewer")
        return self


class TrialExpectations(Record):
    retrieval_applies: Annotated[bool, Field(strict=True)] = False
    expected_sources: list[Identifier] = Field(default_factory=list)
    required_tools: list[Identifier] = Field(default_factory=list)
    forbidden_tools: list[Identifier] = Field(default_factory=list)
    required_approval_states: list[Identifier] = Field(default_factory=list)
    partial_order: list[tuple[Identifier, Identifier]] = Field(default_factory=list)
    required_action_sequence: list[tuple[Identifier, Digest | None]] = Field(
        default_factory=list
    )
    max_retries: Counter = 2
    required_retries: Counter | None = None
    minimum_citations: Counter = 0
    max_model_steps: Annotated[int, Field(ge=0, le=12, strict=True)] = 8
    max_tool_steps: Counter = 12
    terminal_statuses: list[Identifier] = Field(default_factory=lambda: ["COMPLETED"])
    expected_mutations: dict[str, Literal["added", "changed", "deleted"]] = Field(
        default_factory=dict
    )
    expected_after_digests: dict[str, Digest] = Field(default_factory=dict)
    expected_effects: Counter = 0
    answer_quality_applies: Annotated[bool, Field(strict=True)] = False


class TrialEvidence(Record):
    subject_sha: Sha
    scenario_id: Identifier
    trial_id: Identifier
    run_id: Identifier
    retrieved: list[RetrievedEvidence] = Field(default_factory=list)
    current_document_digests: dict[str, Digest] = Field(default_factory=dict)
    cited_ids: list[Digest] = Field(default_factory=list)
    actions: list[ActionBinding] = Field(default_factory=list)
    approvals: list[ApprovalBinding] = Field(default_factory=list)
    trajectory: list[Step] = Field(default_factory=list)
    model_steps: Counter = 0
    tool_steps: Counter = 0
    retries: Counter = 0
    terminal_status: Identifier
    before: dict[str, Digest] = Field(default_factory=dict)
    after: dict[str, Digest] = Field(default_factory=dict)
    physical_effect_counts: dict[str, Counter] = Field(default_factory=dict)
    receipts: list[EffectReceipt] = Field(default_factory=list)
    replay_json: Annotated[str, Field(max_length=65536, strict=True)] | None = None
    final_answer: Text = ""
    review: AnswerQualityReview | None = None

    @model_validator(mode="after")
    def bounded_public(self) -> Self:
        data = canonical(self.model_dump(mode="json"))
        if len(data) > 262144:
            raise ValueError("trial evidence exceeds bound")
        # replay bytes are intentionally checked by L0, including broken controls.
        public_safe(canonical(self.model_dump(mode="json", exclude={"replay_json"})))
        return self


class CheckResult(Record):
    check_id: Identifier
    status: Status
    hard: Annotated[bool, Field(strict=True)]
    metric: float | None = None


class LayerResult(Record):
    layer: Layer
    status: Status
    checks: list[CheckResult]

    @model_validator(mode="after")
    def consistent_layer(self) -> Self:
        if len({c.check_id for c in self.checks}) != len(self.checks):
            raise ValueError("duplicate check identity")
        if not self.checks:
            if self.status not in {"NOT_APPLICABLE", "NOT_REVIEWED"}:
                raise ValueError("empty layer cannot claim PASS")
            return self
        expected = (
            "FAIL"
            if any(c.status == "FAIL" for c in self.checks)
            else "NOT_REVIEWED"
            if any(c.status == "NOT_REVIEWED" for c in self.checks)
            else "NOT_APPLICABLE"
            if all(c.status == "NOT_APPLICABLE" for c in self.checks)
            else "PASS"
        )
        if self.status != expected:
            raise ValueError("layer status contradicts checks")
        return self


class TrialResult(Record):
    subject_sha: Sha
    scenario_id: Identifier
    trial_id: Identifier
    run_id: Identifier
    layers: list[LayerResult]
    failed_checks: list[Identifier]
    hard_invariant_failures: list[Identifier]
    hard_invariants_passed: Annotated[bool, Field(strict=True)]
    task_success: Annotated[bool, Field(strict=True)]
    review_state: Status

    @model_validator(mode="after")
    def consistent(self) -> Self:
        failed = [
            c.check_id
            for layer in self.layers
            for c in layer.checks
            if c.status == "FAIL"
        ]
        hard = [
            c.check_id
            for layer in self.layers
            for c in layer.checks
            if c.status == "FAIL" and c.hard
        ]
        if self.failed_checks != failed or self.hard_invariant_failures != hard:
            raise ValueError("inconsistent failed-check projection")
        if self.hard_invariants_passed != (not hard):
            raise ValueError("inconsistent hard-invariant flag")
        if self.task_success and (failed or not self.hard_invariants_passed):
            raise ValueError("hard failure cannot be task success")
        if [layer.layer for layer in self.layers] != ["L0", "L1", "L2", "L3", "L4"]:
            raise ValueError("exact five layers required")
        for layer in self.layers:
            if any(c.hard != (layer.layer != "L4") for c in layer.checks):
                raise ValueError("layer hard-check ownership mismatch")
            if layer.layer in {"L0", "L2", "L3"} and layer.status not in {
                "PASS",
                "FAIL",
            }:
                raise ValueError("objective mechanism layer is always applicable")
        success = not failed and all(
            layer.status in {"PASS", "NOT_APPLICABLE"} for layer in self.layers
        )
        if self.task_success != success or self.review_state != self.layers[-1].status:
            raise ValueError("inconsistent success/review projection")
        return self


class CalibrationCase(Record):
    checker: Identifier
    good_passed: bool
    broken_failed_for_reason: bool
    alternate_passed: bool


class SuiteCalibrationResult(Record):
    subject_sha: Sha
    scenario_ids: list[Identifier]
    scenario_set_digest: Digest
    lockfile_digests: dict[str, Digest]
    cases: list[CalibrationCase]
    passed: bool
    mode: Literal["calibration_only"] = "calibration_only"
