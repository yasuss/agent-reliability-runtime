"""Small, serializable runtime-owned postcondition registry.

The registry records obligations after trusted effects.  It never dispatches a
verification read; the model must emit that read through the normal graph path.
"""

from typing import Any, TypedDict


class VerificationObligation(TypedDict):
    source_tool: str
    source_action_id: str
    source_effect_sequence: int
    verification_tool: str
    expected_arguments: dict[str, str]


def restart_obligation(
    action: dict[str, Any], effect_sequence: int
) -> VerificationObligation | None:
    """Build the only R10 obligation, after a successful restart receipt."""
    if action.get("tool_name") != "restart_service":
        return None
    service_id = action.get("normalized_args", {}).get("service_id")
    if not isinstance(service_id, str) or not service_id:
        return None
    action_id = action.get("action_id")
    if not isinstance(action_id, str) or not action_id:
        return None
    return {
        "source_tool": "restart_service",
        "source_action_id": action_id,
        "source_effect_sequence": effect_sequence,
        "verification_tool": "get_service_status",
        "expected_arguments": {"service_id": service_id},
    }


def satisfies(
    obligation: VerificationObligation | None,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    effect_sequence: int,
    result: dict[str, Any],
) -> bool:
    """Return true only for a later successful exact-bound read."""
    if obligation is None:
        return False
    if effect_sequence <= obligation["source_effect_sequence"]:
        return False
    if tool_name != obligation["verification_tool"]:
        return False
    expected = obligation["expected_arguments"]
    if arguments != expected:
        return False
    return result.get("service_id") == expected.get("service_id")
