"""Safe manual OTel spans and serialized append-only PostgreSQL audit."""

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from sqlalchemy import Connection, Engine, func, select, text

from agent_reliability_runtime.adapters.postgres.persistence import schema
from agent_reliability_runtime.adapters.postgres.persistence.records import (
    insert_snapshot,
)
from agent_reliability_runtime.core.contracts.domain import AuditEvent, Run, RunStatus
from agent_reliability_runtime.core.evidence import canonical, sanitize

PAYLOADS = {
    "run.started": "scenario_id provider_id model_id policy_version",
    "retrieval.completed": "result_count evidence_ids source_paths",
    "memory.read": "operation count memory_ids",
    "model.completed": "model_step provider_id model_id finish_reason tool_names usage",
    "model.protocol_repair": "reason repair_number model_step",
    "action.validated": "action_id tool_name risk_class action_digest",
    "policy.evaluated": "tool_name risk_class approval_required",
    "approval.waiting": "approval_id action_digest status",
    "approval.resumed": "approval_id action_digest status",
    "tool.completed": "tool_name risk_class receipt_id result_digest replayed success",
    "tool.retry": "tool_name attempt action_id action_digest",
    "recovery.resumed": "kind checkpoint_id",
    "run.finalized": (
        "status terminal_reason model_steps tool_steps sanitized_final_text"
    ),
    "memory.created": "memory_id kind provenance trust",
    "memory.deleted": "memory_id kind provenance trust",
}


def lock(con: Connection, identity: str) -> None:
    key = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], signed=True)
    con.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def read_run(con: Connection, run_id: str) -> Run | None:
    row = (
        con.execute(select(schema.runs).where(schema.runs.c.run_id == run_id))
        .mappings()
        .one_or_none()
    )
    return Run.model_validate(dict(row)) if row else None


class AuditTrail:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def append(
        self, run_id: str, event_type: str, payload: Mapping[str, Any]
    ) -> AuditEvent:
        with self.engine.begin() as con:
            return self.append_in(con, run_id, event_type, payload)

    def append_in(
        self, con: Connection, run_id: str, event_type: str, payload: Mapping[str, Any]
    ) -> AuditEvent:
        if read_run(con, run_id) is None or event_type not in PAYLOADS:
            raise ValueError("unknown audit run/event")
        lock(con, "audit:" + run_id)
        sequence = (
            con.scalar(
                select(func.max(schema.audit_events.c.sequence_number)).where(
                    schema.audit_events.c.run_id == run_id
                )
            )
            or 0
        ) + 1
        fields = PAYLOADS[event_type].split()
        safe = sanitize({k: v for k, v in payload.items() if k in fields})
        ctx = trace.get_current_span().get_span_context()
        event = AuditEvent(
            event_id=hashlib.sha256(
                canonical([run_id, sequence, event_type])
            ).hexdigest(),
            run_id=run_id,
            sequence_number=sequence,
            event_type=event_type,
            payload=safe,
            timestamp=datetime.now(UTC),
            trace_id=f"{ctx.trace_id:032x}" if ctx.is_valid else None,
            span_id=f"{ctx.span_id:016x}" if ctx.is_valid else None,
        )
        insert_snapshot(con, event)
        return event

    def list(self, run_id: str) -> list[AuditEvent]:
        with self.engine.connect() as con:
            if read_run(con, run_id) is None:
                raise ValueError("unknown audit run")
            rows = con.execute(
                select(schema.audit_events)
                .where(schema.audit_events.c.run_id == run_id)
                .order_by(schema.audit_events.c.sequence_number)
            ).mappings()
            return [AuditEvent.model_validate(dict(row)) for row in rows]


def memory_anchor(
    con: Connection, workspace_id: str, user_id: str, *, policy_version: str
) -> str:
    ident = (
        "memory-audit-"
        + hashlib.sha256(
            canonical(["memory-audit-anchor", workspace_id, user_id])
        ).hexdigest()
    )
    lock(con, "anchor:" + ident)
    existing = read_run(con, ident)
    if existing is not None and (
        existing.workspace_id != workspace_id
        or existing.user_id != user_id
        or existing.scenario_id is not None
        or existing.provider_id != "internal"
        or existing.model_id != "memory-control"
        or existing.policy_version != policy_version
        or existing.request_text != "memory control-plane audit anchor"
        or existing.status != RunStatus.COMPLETED
        or existing.model_steps
        or existing.tool_steps
    ):
        raise ValueError("memory audit anchor identity drift")
    if existing is None:
        now = datetime.now(UTC)
        insert_snapshot(
            con,
            Run(
                run_id=ident,
                workspace_id=workspace_id,
                user_id=user_id,
                request_text="memory control-plane audit anchor",
                provider_id="internal",
                model_id="memory-control",
                policy_version=policy_version,
                status=RunStatus.COMPLETED,
                created_at=now,
                updated_at=now,
            ),
        )
    return ident
