"""Framework-neutral action identity and fail-closed integrity checks."""

from typing import Literal

from pydantic import JsonValue

from agent_reliability_runtime.core.contracts.domain import (
    Digest,
    Identifier,
    Record,
    action_digest,
)

Risk = Literal["READ_ONLY", "SIDE_EFFECT"]


class PolicyError(ValueError):
    """Fail-closed action/approval error; no untrusted diagnostics."""


class Decision(Record):
    run_id: Identifier
    tool_name: Identifier
    normalized_args: dict[str, JsonValue]
    risk_class: Risk
    policy_version: Identifier


class Action(Decision):
    action_id: Identifier
    action_digest: Digest


def validate_identity(action: Action, decision: Decision) -> Action:
    if decision.model_dump() != action.model_dump(
        exclude={"action_id", "action_digest"}
    ) or action.action_digest != action_digest(
        action.run_id,
        action.tool_name,
        decision.normalized_args,
        decision.policy_version,
    ):
        raise PolicyError("action drift")
    return action
