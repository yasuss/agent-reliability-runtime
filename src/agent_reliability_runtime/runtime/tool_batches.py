"""Prevalidation without minting actions, approvals or effect keys."""

from uuid import uuid4

from agent_reliability_runtime.mcp.contracts import INPUTS, RUNTIME_FIELDS
from agent_reliability_runtime.policy import TOOL_RISK, PolicyError
from agent_reliability_runtime.providers.contracts import ToolCall

MAX_CALLS = 4


def validate_calls(calls: tuple[ToolCall, ...]) -> tuple[ToolCall, ...]:
    if not 1 <= len(calls) <= MAX_CALLS:
        raise PolicyError("invalid tool batch size")
    normalized = tuple(
        ToolCall.model_validate(c.model_dump() | {"call_id": c.call_id or uuid4().hex})
        for c in calls
    )
    if len({c.call_id for c in normalized}) != len(normalized):
        raise PolicyError("duplicate tool call ID")
    for call in normalized:
        if call.name not in TOOL_RISK:
            raise PolicyError("unknown tool")
        owned = set(INPUTS[call.name].model_fields) - RUNTIME_FIELDS.get(
            call.name, set()
        )
        if set(call.arguments) != owned:
            raise PolicyError("model field ownership mismatch")
        args = dict(call.arguments)
        if TOOL_RISK[call.name] == "SIDE_EFFECT":
            args["idempotency_key"] = "validation-only"
        INPUTS[call.name].model_validate(args)
    return normalized
