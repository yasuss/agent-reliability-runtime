"""Prevalidation without minting actions, approvals or effect keys."""

from uuid import uuid4

from agent_reliability_runtime.core.contracts.model import ToolCall
from agent_reliability_runtime.core.policy import PolicyError
from agent_reliability_runtime.core.ports import PolicyEngine

MAX_CALLS = 4


def validate_calls(
    calls: tuple[ToolCall, ...], policy: PolicyEngine
) -> tuple[ToolCall, ...]:
    if not 1 <= len(calls) <= MAX_CALLS:
        raise PolicyError("invalid tool batch size")
    normalized = tuple(
        ToolCall.model_validate(c.model_dump() | {"call_id": c.call_id or uuid4().hex})
        for c in calls
    )
    if len({c.call_id for c in normalized}) != len(normalized):
        raise PolicyError("duplicate tool call ID")
    for call in normalized:
        policy.validate_model_args(call.name, call.arguments)
    return normalized
