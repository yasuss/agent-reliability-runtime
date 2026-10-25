"""Exact approval snapshots and irreversible lifecycle semantics."""

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import JsonValue, model_validator

from agent_reliability_runtime.core.contracts.domain import (
    Digest,
    Identifier,
    Record,
    Timestamp,
    action_digest,
)


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
    allowed = {
        ApprovalStatus.PENDING: {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
        },
        ApprovalStatus.APPROVED: {ApprovalStatus.CONSUMED, ApprovalStatus.EXPIRED},
    }
    if status not in allowed.get(approval.status, set()):
        raise ValueError(
            "illegal approval transition; terminal approval cannot be resurrected"
        )
    return Approval.model_validate(
        {
            **approval.model_dump(),
            "status": status,
            "decided_at": approval.decided_at
            if status == ApprovalStatus.CONSUMED
            else at,
        }
    )


def approval_identity(action_id: str) -> str:
    return hashlib.sha256(
        json.dumps(["approval", action_id], separators=(",", ":")).encode()
    ).hexdigest()
