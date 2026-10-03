"""B10 domain values and minimal lifecycle invariants.

Records are immutable snapshots. Construct new validated snapshots for changes;
never use model_copy(update=...) as a validation boundary. JSON values must be
revalidated on persistence and explicitly replaced rather than mutated in place.
"""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

Identifier = Annotated[str, Field(min_length=1, strict=True)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]
Counter = Annotated[int, Field(ge=0, strict=True)]


def utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


Timestamp = Annotated[datetime, AfterValidator(utc_timestamp)]


class Record(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_default=True, allow_inf_nan=False
    )


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.REJECTED,
        RunStatus.FAILED,
        RunStatus.BUDGET_EXCEEDED,
        RunStatus.CANCELLED,
    }
)


class Run(Record):
    run_id: Identifier
    workspace_id: Identifier
    user_id: Identifier
    request_text: Identifier
    scenario_id: Identifier | None = None
    provider_id: Identifier
    model_id: Identifier
    policy_version: Identifier
    status: RunStatus
    model_steps: Counter = 0
    tool_steps: Counter = 0
    created_at: Timestamp
    updated_at: Timestamp
    terminal_reason: Identifier | None = None

    @model_validator(mode="after")
    def terminal_explanation(self) -> Self:
        if (
            self.status in TERMINAL_STATUSES
            and self.status != RunStatus.COMPLETED
            and self.terminal_reason is None
        ):
            raise ValueError("non-complete terminal run requires terminal_reason")
        return self


def transition_run(
    run: Run, status: RunStatus, *, at: datetime, reason: str | None = None
) -> Run:
    if run.status in TERMINAL_STATUSES and status not in TERMINAL_STATUSES:
        raise ValueError("terminal run cannot return to a non-terminal status")
    return Run.model_validate(
        {
            **run.model_dump(),
            "status": status,
            "updated_at": at,
            "terminal_reason": reason,
        }
    )


def action_digest(
    run_id: str,
    tool_name: str,
    normalized_args: dict[str, JsonValue],
    policy_version: str,
) -> str:
    """Canonical UTF-8 JSON: sorted keys, compact separators, no NaN/Infinity.

    Input arguments are already normalized by the caller's schema. This helper
    hashes their exact JSON values; it does not interpret model text or grant
    authority. Unicode is retained without ASCII escaping.
    """
    payload = {
        "run_id": run_id,
        "tool_name": tool_name,
        "normalized_args": normalized_args,
        "policy_version": policy_version,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class Approval(Record):
    approval_id: Identifier
    run_id: Identifier
    action_id: Identifier
    tool_name: Identifier
    normalized_args: dict[str, JsonValue]
    action_digest: Digest
    policy_version: Identifier
    risk_class: Literal["SIDE_EFFECT"]
    status: ApprovalStatus
    created_at: Timestamp
    decided_at: Timestamp | None = None
    expires_at: Timestamp | None = None

    @model_validator(mode="after")
    def exact_digest(self) -> Self:
        expected = action_digest(
            self.run_id, self.tool_name, self.normalized_args, self.policy_version
        )
        if self.action_digest != expected:
            raise ValueError("action_digest does not match canonical action")
        return self


def transition_approval(
    approval: Approval, status: ApprovalStatus, *, at: datetime
) -> Approval:
    if approval.status in {ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
        if status != approval.status:
            raise ValueError("rejected/expired approval cannot be resurrected")
    return Approval.model_validate(
        {**approval.model_dump(), "status": status, "decided_at": at}
    )


class EffectReceipt(Record):
    receipt_id: Identifier
    run_id: Identifier
    tool_name: Identifier
    idempotency_key: Identifier
    action_digest: Digest
    result_digest: Digest
    applied_at: Timestamp


class AuditEvent(Record):
    """Append-only safe/redacted payload, prepared by trusted caller.

    This data shape does not claim automatic secret redaction; B80 owns that
    pipeline. Never put raw prompts, credentials or unsafe tool results here.
    """

    event_id: Identifier
    run_id: Identifier
    sequence_number: Annotated[int, Field(gt=0, strict=True)]
    event_type: Identifier
    payload: dict[str, JsonValue]
    timestamp: Timestamp
    trace_id: Identifier | None = None
    span_id: Identifier | None = None


class MemoryKind(StrEnum):
    PREFERENCE = "PREFERENCE"
    VERIFIED_FACT = "VERIFIED_FACT"
    OBSERVATION = "OBSERVATION"


class MemoryProvenance(StrEnum):
    USER_EXPLICIT = "USER_EXPLICIT"
    TOOL_VERIFIED = "TOOL_VERIFIED"
    MODEL_OBSERVATION = "MODEL_OBSERVATION"


class MemoryTrust(StrEnum):
    TRUSTED = "TRUSTED"
    UNTRUSTED = "UNTRUSTED"


class Memory(Record):
    memory_id: Identifier
    workspace_id: Identifier
    user_id: Identifier
    kind: MemoryKind
    provenance: MemoryProvenance
    trust: MemoryTrust = MemoryTrust.UNTRUSTED
    content: Identifier
    created_at: Timestamp
    updated_at: Timestamp
    source_run_id: Identifier | None = None
    source_tool_name: Identifier | None = None


def repository_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or value == "."
    ):
        raise ValueError("source_path must be normalized and repository-relative")
    return value


SourcePath = Annotated[str, AfterValidator(repository_path)]


def document_id(source_path: str) -> str:
    return hashlib.sha256(repository_path(source_path).encode("utf-8")).hexdigest()


def chunk_id(document_id: str, content_digest: str, ordinal: int) -> str:
    if ordinal < 0:
        raise ValueError("chunk ordinal must be non-negative")
    return hashlib.sha256(
        json.dumps(
            [document_id, content_digest, ordinal], separators=(",", ":")
        ).encode()
    ).hexdigest()


class KnowledgeDocument(Record):
    document_id: Identifier
    source_path: SourcePath
    content_digest: Digest
    title: Identifier
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def stable_identity(self) -> Self:
        if self.document_id != document_id(self.source_path):
            raise ValueError("document_id must derive from source_path")
        return self


class KnowledgeChunk(Record):
    chunk_id: Identifier
    document_id: Identifier
    document_digest: Digest
    ordinal: Counter
    content: Identifier

    @model_validator(mode="after")
    def stable_identity(self) -> Self:
        if self.chunk_id != chunk_id(
            self.document_id, self.document_digest, self.ordinal
        ):
            raise ValueError("chunk_id must derive from document/digest/ordinal")
        return self


class DemoService(Record):
    service_id: Identifier
    status: Identifier


class DemoIncident(Record):
    incident_id: Identifier
    service_id: Identifier
    summary: Identifier
    status: Identifier


class DemoNotification(Record):
    notification_id: Identifier
    channel: Identifier
    message: Identifier
    created_at: Timestamp


class DemoIncidentNote(Record):
    note_id: Identifier
    incident_id: Identifier
    note: Identifier
    created_at: Timestamp


class DemoSeed(Record):
    incidents: list[DemoIncident]
    services: list[DemoService]
