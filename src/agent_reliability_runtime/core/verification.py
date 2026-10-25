"""Generic, serializable obligations; verification never dispatches a read."""

from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any, TypedDict

from pydantic import JsonValue

from agent_reliability_runtime.core.policy import Action


class VerificationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"


class VerificationObligation(TypedDict):
    source_tool: str
    source_action_id: str
    source_effect_sequence: int
    verification_tool: str
    expected_arguments: dict[str, str]


class VerificationRule:
    def __init__(
        self,
        obligation_for: Callable[[dict[str, Any], int], VerificationObligation | None],
        satisfies: Callable[..., bool],
    ) -> None:
        self.obligation_for = obligation_for
        self.satisfies = satisfies


class RuleVerifier:
    def __init__(self, rules: Sequence[VerificationRule] = ()) -> None:
        self.rules = tuple(rules)

    def obligation_for(
        self, action: Action, effect_sequence: int
    ) -> VerificationObligation | None:
        for rule in self.rules:
            obligation = rule.obligation_for(
                action.model_dump(mode="json"), effect_sequence
            )
            if obligation is not None:
                return obligation
        return None

    def verify(
        self,
        obligation: VerificationObligation,
        *,
        tool_name: str,
        arguments: dict[str, JsonValue],
        effect_sequence: int,
        result: dict[str, JsonValue],
    ) -> VerificationStatus:
        for rule in self.rules:
            if rule.satisfies(
                obligation,
                tool_name=tool_name,
                arguments=arguments,
                effect_sequence=effect_sequence,
                result=result,
            ):
                return VerificationStatus.PASS
        return VerificationStatus.FAIL
