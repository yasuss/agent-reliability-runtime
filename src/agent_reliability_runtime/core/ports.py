"""ARR public structural extension contracts; planned ports execute nothing."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pydantic import JsonValue

from agent_reliability_runtime.core.approval import Approval
from agent_reliability_runtime.core.contracts.domain import (
    Identifier,
    Record,
    Timestamp,
)
from agent_reliability_runtime.core.contracts.model import ChatRequest, ChatResult
from agent_reliability_runtime.core.contracts.retrieval import Evidence
from agent_reliability_runtime.core.effects import ReceiptEnvelope, ReconciliationResult
from agent_reliability_runtime.core.policy import Action, Risk
from agent_reliability_runtime.core.verification import (
    VerificationObligation,
    VerificationStatus,
)


class ModelProvider(Protocol):
    async def complete(self, request: ChatRequest) -> ChatResult: ...


class Retriever(Protocol):
    async def retrieve(self, query: str) -> tuple[Evidence, ...]: ...


class PolicyEngine(Protocol):
    @property
    def version(self) -> str: ...
    def risk_for(self, tool_name: str) -> Risk: ...
    def validate_model_args(
        self, tool_name: str, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...
    def propose(
        self,
        run_id: str,
        tool_name: str,
        model_args: dict[str, JsonValue],
        *,
        key_factory: Callable[[], str],
    ) -> Action: ...
    def validate(self, action: Action) -> Action: ...


class Approver(Protocol):
    def ensure(
        self, action: Action, *, expires_at: datetime | None = None
    ) -> Approval: ...
    def read(self, approval_id: str) -> Approval: ...
    def decide(self, approval_id: str, *, approved: bool) -> Approval: ...
    def expire(self, approval_id: str) -> Approval: ...


class EffectStore(Protocol):
    def receipt_for(self, action: Action) -> ReceiptEnvelope | None: ...


class Verifier(Protocol):
    def obligation_for(
        self, action: Action, effect_sequence: int
    ) -> VerificationObligation | None: ...
    def verify(
        self,
        obligation: VerificationObligation,
        *,
        tool_name: str,
        arguments: dict[str, JsonValue],
        effect_sequence: int,
        result: dict[str, JsonValue],
    ) -> VerificationStatus: ...


class CheckpointStore(Protocol):
    async def setup(self) -> None: ...
    async def has_checkpoint(self, run_id: str) -> bool: ...


class TimerSpec(Record):
    timer_id: Identifier
    run_id: Identifier
    wake_at: Timestamp


class SourceRef(Record):
    system: Identifier
    object_id: Identifier


class SourceRevision(Record):
    source: SourceRef
    version: Identifier
    observed_at: Timestamp


class CapabilityDefinition(Record):
    capability_id: Identifier
    version: Identifier
    risk_class: Risk


class Reconciler(Protocol):
    """Planned — interface only, no implementation."""

    async def reconcile(self, action: Action) -> ReconciliationResult: ...


class TimerStore(Protocol):
    """Planned — interface only, no implementation."""

    async def put(self, timer: TimerSpec) -> None: ...
    async def due(self, at: datetime, limit: int) -> tuple[TimerSpec, ...]: ...


class SourceRevisionReader(Protocol):
    """Planned — interface only, no implementation."""

    async def read_revision(self, source: SourceRef) -> SourceRevision: ...


class CapabilityRegistry(Protocol):
    """Planned — interface only, no implementation."""

    def get(self, capability_id: str) -> CapabilityDefinition | None: ...
