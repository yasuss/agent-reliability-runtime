"""Insert validated snapshots; lifecycle updates preserve immutable identities.

Caller owns the transaction. Row locking prevents concurrent lifecycle updates
from ignoring the persisted status. No audit update/delete operation is exposed.
These primitives do not execute tools, assign audit order or authorize actions.
"""

from datetime import datetime

from sqlalchemy import Connection, select, update

from agent_reliability_runtime.contracts.domain import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    EffectReceipt,
    KnowledgeChunk,
    KnowledgeDocument,
    Memory,
    Run,
    RunStatus,
    transition_approval,
    transition_run,
)
from agent_reliability_runtime.persistence import schema

Snapshot = (
    Run
    | Approval
    | EffectReceipt
    | AuditEvent
    | Memory
    | KnowledgeDocument
    | KnowledgeChunk
)
TABLES = {
    Run: schema.runs,
    Approval: schema.approvals,
    EffectReceipt: schema.effect_receipts,
    AuditEvent: schema.audit_events,
    Memory: schema.memories,
    KnowledgeDocument: schema.knowledge_documents,
    KnowledgeChunk: schema.knowledge_chunks,
}


def insert_snapshot(connection: Connection, record: Snapshot) -> None:
    # Revalidate nested JSON too: frozen Pydantic fields do not freeze dicts.
    validated = type(record).model_validate(record.model_dump())
    table = TABLES[type(validated)]
    connection.execute(table.insert().values(**validated.model_dump()))


def set_run_status(
    connection: Connection,
    run_id: str,
    status: RunStatus,
    *,
    at: datetime,
    reason: str | None = None,
) -> Run:
    row = (
        connection.execute(
            select(schema.runs).where(schema.runs.c.run_id == run_id).with_for_update()
        )
        .mappings()
        .one()
    )
    result = transition_run(Run.model_validate(dict(row)), status, at=at, reason=reason)
    connection.execute(
        update(schema.runs)
        .where(schema.runs.c.run_id == run_id)
        .values(
            status=result.status,
            updated_at=result.updated_at,
            terminal_reason=result.terminal_reason,
        )
    )
    return result


def set_approval_status(
    connection: Connection,
    approval_id: str,
    status: ApprovalStatus,
    *,
    at: datetime,
) -> Approval:
    row = (
        connection.execute(
            select(schema.approvals)
            .where(schema.approvals.c.approval_id == approval_id)
            .with_for_update()
        )
        .mappings()
        .one()
    )
    result = transition_approval(Approval.model_validate(dict(row)), status, at=at)
    connection.execute(
        update(schema.approvals)
        .where(schema.approvals.c.approval_id == approval_id)
        .values(status=result.status, decided_at=result.decided_at)
    )
    return result
