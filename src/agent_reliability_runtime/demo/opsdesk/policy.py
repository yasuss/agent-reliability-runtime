"""OpsDesk schema normalization and exact-five trusted policy."""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from pydantic import JsonValue

from agent_reliability_runtime.core.contracts.domain import action_digest
from agent_reliability_runtime.core.policy import (
    Action,
    Decision,
    PolicyError,
    Risk,
    validate_identity,
)
from agent_reliability_runtime.demo.opsdesk.contracts import INPUTS, RUNTIME_FIELDS

VERSION = "opsdesk-v1"
TOOL_RISK: MappingProxyType[str, Risk] = MappingProxyType(
    {
        "get_incident": "READ_ONLY",
        "get_service_status": "READ_ONLY",
        "add_incident_note": "SIDE_EFFECT",
        "restart_service": "SIDE_EFFECT",
        "send_notification": "SIDE_EFFECT",
    }
)


def evaluate(
    run_id: str, tool: str, arguments: dict[str, Any], version: str
) -> Decision:
    if tool not in TOOL_RISK or version != VERSION:
        raise PolicyError("unknown tool or policy version")
    args = INPUTS[tool].model_validate(arguments).model_dump(mode="json")
    return Decision(
        run_id=run_id,
        tool_name=tool,
        normalized_args=args,
        risk_class=TOOL_RISK[tool],
        policy_version=VERSION,
    )


def propose(
    run_id: str,
    tool: str,
    model_args: dict[str, Any],
    *,
    key_factory: Callable[[], str] = lambda: uuid4().hex,
) -> Action:
    if tool not in TOOL_RISK:
        raise PolicyError("unknown tool")
    # Validate the complete model-owned shape before minting anything.
    owned = set(INPUTS[tool].model_fields) - RUNTIME_FIELDS.get(tool, set())
    if set(model_args) != owned:
        raise PolicyError("model field ownership mismatch")
    candidate = dict(model_args)
    if TOOL_RISK[tool] == "SIDE_EFFECT":
        # Placeholder validates all model fields before runtime generates the key.
        INPUTS[tool].model_validate(candidate | {"idempotency_key": "validation-only"})
        candidate["idempotency_key"] = key_factory()
    decision = evaluate(run_id, tool, candidate, VERSION)
    return Action(
        **decision.model_dump(),
        action_id=uuid4().hex,
        action_digest=action_digest(run_id, tool, decision.normalized_args, VERSION),
    )


def validate_action(action: Action) -> Action:
    action = Action.model_validate(action.model_dump())
    decision = evaluate(
        action.run_id, action.tool_name, action.normalized_args, action.policy_version
    )
    return validate_identity(action, decision)


class OpsDeskPolicyEngine:
    @property
    def version(self) -> str:
        return VERSION

    def risk_for(self, tool_name: str) -> Risk:
        if tool_name not in TOOL_RISK:
            raise PolicyError("unknown tool")
        return TOOL_RISK[tool_name]

    def validate_model_args(
        self, tool_name: str, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        risk = self.risk_for(tool_name)
        owned = set(INPUTS[tool_name].model_fields) - RUNTIME_FIELDS.get(
            tool_name, set()
        )
        if set(arguments) != owned:
            raise PolicyError("model field ownership mismatch")
        candidate = dict(arguments)
        if risk == "SIDE_EFFECT":
            candidate["idempotency_key"] = "validation-only"
        INPUTS[tool_name].model_validate(candidate)
        return dict(arguments)

    def propose(
        self,
        run_id: str,
        tool_name: str,
        model_args: dict[str, JsonValue],
        *,
        key_factory: Callable[[], str],
    ) -> Action:
        return propose(run_id, tool_name, model_args, key_factory=key_factory)

    def validate(self, action: Action) -> Action:
        return validate_action(action)
