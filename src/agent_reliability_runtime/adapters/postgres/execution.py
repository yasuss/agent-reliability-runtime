"""Trusted policy, exact approvals and durable execution gateway.

Only this gateway is a production execution surface. Raw MCP infrastructure is
non-authorizing and must never be connected directly to a graph.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import Connection, Engine, select, text

from agent_reliability_runtime.adapters.postgres.persistence import schema
from agent_reliability_runtime.adapters.postgres.persistence.records import (
    insert_snapshot,
    set_approval_status,
)
from agent_reliability_runtime.core.approval import (
    Approval,
    ApprovalStatus,
    approval_identity,
)
from agent_reliability_runtime.core.contracts.domain import (
    Record,
    Run,
)
from agent_reliability_runtime.core.effects import ReceiptEnvelope
from agent_reliability_runtime.core.policy import Action, PolicyError
from agent_reliability_runtime.core.ports import PolicyEngine


def load_run(con: Connection, run_id: str, policy: PolicyEngine) -> Run:
    row = (
        con.execute(select(schema.runs).where(schema.runs.c.run_id == run_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PolicyError("unknown run")
    run = Run.model_validate(dict(row))
    if run.policy_version != policy.version:
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
        self,
        engine: Engine,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        *,
        policy: PolicyEngine,
    ) -> None:
        self.engine, self.clock, self.policy = engine, clock, policy

    def create(self, action: Action, *, expires_at: datetime | None = None) -> Approval:
        action = self.policy.validate(action)
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
            load_run(con, action.run_id, self.policy)
            insert_snapshot(con, approval)
        return approval

    def read(self, approval_id: str) -> Approval:
        with self.engine.begin() as con:
            return load_approval(con, approval_id)

    def ensure(self, action: Action, *, expires_at: datetime | None = None) -> Approval:
        """Replay-safe graph primitive; preserve existing lifecycle and timestamps."""
        action = self.policy.validate(action)
        if action.risk_class != "SIDE_EFFECT":
            raise PolicyError("read action needs no approval")
        identity = approval_identity(action.action_id)
        proposed = Approval(
            approval_id=identity,
            **action.model_dump(exclude={"risk_class"}),
            risk_class="SIDE_EFFECT",
            status=ApprovalStatus.PENDING,
            created_at=self.clock(),
            expires_at=expires_at,
        )
        with self.engine.begin() as con:
            load_run(con, action.run_id, self.policy)
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
        *,
        policy: PolicyEngine,
    ) -> None:
        self.engine, self.transport, self.clock = engine, transport, clock
        self.policy = policy
        self.approvals = Approvals(engine, clock, policy=policy)
        self.effects = PostgresEffectStore(engine)

    async def execute(self, action: Action, approval_id: str | None = None) -> Record:
        action = self.policy.validate(action)
        if action.risk_class == "READ_ONLY":
            with self.engine.connect() as con:
                load_run(con, action.run_id, self.policy)
            return await self.transport.read(action.tool_name, action.normalized_args)
        if approval_id is None:
            raise PolicyError("exact approval required")
        expired = False
        # Serialize this approval through the bounded MCP dispatch. Server owns a
        # separate transaction: lost replies leave APPROVED + durable receipt.
        with self.engine.begin() as con:
            load_run(con, action.run_id, self.policy)
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
            prior = self.effects.receipt_for_connection(con, action)
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
                persisted = self.effects.receipt_for_connection(con, action)
                if persisted is None or persisted.model_dump(
                    exclude={"replayed"}
                ) != result.model_dump(exclude={"replayed"}):
                    raise PolicyError("missing or mismatched durable receipt")
                self.approvals.consume(con, approval_id)
                return result
        if expired:
            raise PolicyError("approval expired")
        raise PolicyError("effect not executed")


class PostgresEffectStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def receipt_for(self, action: Action) -> ReceiptEnvelope | None:
        with self.engine.connect() as con:
            return self.receipt_for_connection(con, action)

    @staticmethod
    def receipt_for_connection(
        con: Connection, action: Action
    ) -> ReceiptEnvelope | None:
        return receipt_for(con, action)
