"""Trusted OpsDesk policy, exact approvals and durable execution gateway.

Only this gateway is a production execution surface. Raw MCP infrastructure is
non-authorizing and must never be connected directly to a graph.
"""

import asyncio
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import Connection, Engine, select, text

from agent_reliability_runtime.contracts.domain import (
    Approval,
    ApprovalStatus,
    Digest,
    Identifier,
    Record,
    Run,
    action_digest,
)
from agent_reliability_runtime.mcp.contracts import (
    INPUTS,
    RUNTIME_FIELDS,
    ReceiptEnvelope,
)
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import (
    insert_snapshot,
    set_approval_status,
)

VERSION = "opsdesk-v1"
Risk = Literal["READ_ONLY", "SIDE_EFFECT"]
TOOL_RISK: MappingProxyType[str, Risk] = MappingProxyType(
    {
        "get_incident": "READ_ONLY",
        "get_service_status": "READ_ONLY",
        "add_incident_note": "SIDE_EFFECT",
        "restart_service": "SIDE_EFFECT",
        "send_notification": "SIDE_EFFECT",
    }
)


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


def load_run(con: Connection, run_id: str) -> Run:
    row = (
        con.execute(select(schema.runs).where(schema.runs.c.run_id == run_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PolicyError("unknown run")
    run = Run.model_validate(dict(row))
    if run.policy_version != VERSION:
        raise PolicyError("run policy drift")
    return run


def load_approval(con: Connection, approval_id: str) -> Approval:
    row = (
        con.execute(
            select(schema.approvals)
            .where(schema.approvals.c.approval_id == approval_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PolicyError("unknown approval")
    return Approval.model_validate(dict(row))


class Approvals:
    def __init__(
        self, engine: Engine, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.engine, self.clock = engine, clock

    def create(self, action: Action, *, expires_at: datetime | None = None) -> Approval:
        action = validate_action(action)
        if action.risk_class != "SIDE_EFFECT":
            raise PolicyError("read action needs no approval")
        approval = Approval(
            approval_id=uuid4().hex,
            **action.model_dump(exclude={"risk_class"}),
            risk_class="SIDE_EFFECT",
            status=ApprovalStatus.PENDING,
            created_at=self.clock(),
            expires_at=expires_at,
        )
        with self.engine.begin() as con:
            load_run(con, action.run_id)
            insert_snapshot(con, approval)
        return approval

    def read(self, approval_id: str) -> Approval:
        with self.engine.begin() as con:
            return load_approval(con, approval_id)

    def ensure(self, action: Action, *, expires_at: datetime | None = None) -> Approval:
        """Replay-safe graph primitive; preserve existing lifecycle and timestamps."""
        action = validate_action(action)
        if action.risk_class != "SIDE_EFFECT":
            raise PolicyError("read action needs no approval")
        identity = hashlib.sha256(
            json.dumps(["approval", action.action_id], separators=(",", ":")).encode()
        ).hexdigest()
        proposed = Approval(
            approval_id=identity,
            **action.model_dump(exclude={"risk_class"}),
            risk_class="SIDE_EFFECT",
            status=ApprovalStatus.PENDING,
            created_at=self.clock(),
            expires_at=expires_at,
        )
        with self.engine.begin() as con:
            load_run(con, action.run_id)
            con.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int.from_bytes(bytes.fromhex(identity)[:8], signed=True)},
            )
            row = (
                con.execute(
                    select(schema.approvals)
                    .where(schema.approvals.c.approval_id == identity)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                insert_snapshot(con, proposed)
                return proposed
            existing = Approval.model_validate(dict(row))
            lifecycle = {"status", "created_at", "decided_at"}
            if existing.model_dump(exclude=lifecycle) != proposed.model_dump(
                exclude=lifecycle
            ):
                raise PolicyError("approval identity conflict")
            return existing

    def decide(self, approval_id: str, *, approved: bool) -> Approval:
        with self.engine.begin() as con:
            prior = load_approval(con, approval_id)
            status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            if prior.expires_at is not None and prior.expires_at <= self.clock():
                status = ApprovalStatus.EXPIRED
            return set_approval_status(con, approval_id, status, at=self.clock())

    def expire(self, approval_id: str) -> Approval:
        with self.engine.begin() as con:
            return set_approval_status(
                con, approval_id, ApprovalStatus.EXPIRED, at=self.clock()
            )

    def consume(self, con: Connection, approval_id: str) -> Approval:
        # Only gateway callers with a verified durable receipt may consume.
        return set_approval_status(
            con, approval_id, ApprovalStatus.CONSUMED, at=self.clock()
        )


class Transport(Protocol):
    async def read(self, name: str, arguments: dict[str, Any]) -> Record: ...
    async def _dispatch_effect(self, action: Action) -> ReceiptEnvelope: ...


def receipt_for(con: Connection, action: Action) -> ReceiptEnvelope | None:
    row = (
        con.execute(
            select(schema.effect_receipts).where(
                schema.effect_receipts.c.tool_name == action.tool_name,
                schema.effect_receipts.c.idempotency_key
                == action.normalized_args["idempotency_key"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    receipt = ReceiptEnvelope.model_validate(dict(row) | {"replayed": True})
    if receipt.run_id != action.run_id or receipt.action_digest != action.action_digest:
        raise PolicyError("effect identity conflict")
    return receipt


class Gateway:
    def __init__(
        self,
        engine: Engine,
        transport: Transport,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine, self.transport, self.clock = engine, transport, clock
        self.approvals = Approvals(engine, clock)

    async def execute(self, action: Action, approval_id: str | None = None) -> Record:
        action = validate_action(action)
        if action.risk_class == "READ_ONLY":
            with self.engine.connect() as con:
                load_run(con, action.run_id)
            return await self.transport.read(action.tool_name, action.normalized_args)
        if approval_id is None:
            raise PolicyError("exact approval required")
        expired = False
        # Serialize this approval through the bounded MCP dispatch. Server owns a
        # separate transaction: lost replies leave APPROVED + durable receipt.
        with self.engine.begin() as con:
            load_run(con, action.run_id)
            # A competing gateway must not block the event loop while this
            # approval's owner awaits its MCP response. No concurrent connection
            # use occurs: the worker finishes before this task resumes.
            approval = await asyncio.to_thread(load_approval, con, approval_id)
            expected = action.model_dump()
            actual = approval.model_dump(include=set(expected))
            if actual != expected or approval.status not in {
                ApprovalStatus.APPROVED,
                ApprovalStatus.CONSUMED,
            }:
                raise PolicyError("approval mismatch or not approved")
            prior = receipt_for(con, action)
            if prior is not None:
                if approval.status == ApprovalStatus.APPROVED:
                    self.approvals.consume(con, approval_id)
                return prior
            if approval.status == ApprovalStatus.CONSUMED:
                raise PolicyError("consumed approval missing receipt")
            if approval.expires_at is not None and approval.expires_at <= self.clock():
                set_approval_status(
                    con, approval_id, ApprovalStatus.EXPIRED, at=self.clock()
                )
                expired = True
            else:
                result = await self.transport._dispatch_effect(action)
                persisted = receipt_for(con, action)
                if persisted is None or persisted.model_dump(
                    exclude={"replayed"}
                ) != result.model_dump(exclude={"replayed"}):
                    raise PolicyError("missing or mismatched durable receipt")
                self.approvals.consume(con, approval_id)
                return result
        if expired:
            raise PolicyError("approval expired")
        raise PolicyError("effect not executed")
