"""B10 project domain schema

Revision ID: 0002_domain
Revises: 0001_foundation
Create Date: 2026-10-03 21:40:13.802320

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_domain"
down_revision: str | Sequence[str] | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "demo_notifications",
        sa.Column("notification_id", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("notification_id", name=op.f("pk_demo_notifications")),
    )
    op.create_table(
        "demo_services",
        sa.Column("service_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("service_id", name=op.f("pk_demo_services")),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("content_digest", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$'", name="ck_knowledge_digest"
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint(
            "document_id", "content_digest", name="uq_knowledge_documents_version"
        ),
        sa.UniqueConstraint("source_path", name="uq_knowledge_documents_path"),
    )
    op.create_table(
        "runs",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=True),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("model_steps", sa.Integer(), nullable=False),
        sa.Column("tool_steps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('CREATED','RUNNING','WAITING_APPROVAL','COMPLETED',"
            "'REJECTED','FAILED','BUDGET_EXCEEDED','CANCELLED')",
            name="ck_runs_status",
        ),
        sa.CheckConstraint("model_steps >= 0", name="ck_runs_model_steps"),
        sa.CheckConstraint("tool_steps >= 0", name="ck_runs_tool_steps"),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_runs")),
    )
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("action_id", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column(
            "normalized_args", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("action_digest", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("risk_class", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action_digest ~ '^[0-9a-f]{64}$'", name="ck_approvals_digest"
        ),
        sa.CheckConstraint("risk_class = 'SIDE_EFFECT'", name="ck_approvals_risk"),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','EXPIRED','CONSUMED')",
            name="ck_approvals_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.run_id"], name=op.f("fk_approvals_run_id_runs")
        ),
        sa.PrimaryKeyConstraint("approval_id", name=op.f("pk_approvals")),
    )
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("span_id", sa.Text(), nullable=True),
        sa.CheckConstraint("sequence_number > 0", name="ck_audit_events_sequence"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.run_id"], name=op.f("fk_audit_events_run_id_runs")
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_audit_events")),
        sa.UniqueConstraint(
            "run_id", "sequence_number", name="uq_audit_events_sequence"
        ),
    )
    op.create_table(
        "demo_incidents",
        sa.Column("incident_id", sa.Text(), nullable=False),
        sa.Column("service_id", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["demo_services.service_id"],
            name=op.f("fk_demo_incidents_service_id_demo_services"),
        ),
        sa.PrimaryKeyConstraint("incident_id", name=op.f("pk_demo_incidents")),
    )
    op.create_table(
        "effect_receipts",
        sa.Column("receipt_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("action_digest", sa.Text(), nullable=False),
        sa.Column("result_digest", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_digest ~ '^[0-9a-f]{64}$'", name="ck_effect_action_digest"
        ),
        sa.CheckConstraint(
            "result_digest ~ '^[0-9a-f]{64}$'", name="ck_effect_result_digest"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.run_id"], name=op.f("fk_effect_receipts_run_id_runs")
        ),
        sa.PrimaryKeyConstraint("receipt_id", name=op.f("pk_effect_receipts")),
        sa.UniqueConstraint(
            "tool_name", "idempotency_key", name="uq_effect_receipts_identity"
        ),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("document_digest", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_knowledge_chunks_ordinal"),
        sa.ForeignKeyConstraint(
            ["document_id", "document_digest"],
            ["knowledge_documents.document_id", "knowledge_documents.content_digest"],
            name="fk_knowledge_chunks_document_version",
        ),
        sa.PrimaryKeyConstraint("chunk_id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "document_digest",
            "ordinal",
            name="uq_knowledge_chunks_ordinal",
        ),
    )
    op.create_table(
        "memories",
        sa.Column("memory_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("trust", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_run_id", sa.Text(), nullable=True),
        sa.Column("source_tool_name", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('PREFERENCE','VERIFIED_FACT','OBSERVATION')",
            name="ck_memories_kind",
        ),
        sa.CheckConstraint(
            "provenance IN ('USER_EXPLICIT','TOOL_VERIFIED','MODEL_OBSERVATION')",
            name="ck_memories_provenance",
        ),
        sa.CheckConstraint(
            "trust IN ('TRUSTED','UNTRUSTED')", name="ck_memories_trust"
        ),
        sa.CheckConstraint("length(content) > 0", name="ck_memories_content"),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["runs.run_id"],
            name=op.f("fk_memories_source_run_id_runs"),
        ),
        sa.PrimaryKeyConstraint("memory_id", name=op.f("pk_memories")),
    )
    op.create_table(
        "demo_incident_notes",
        sa.Column("note_id", sa.Text(), nullable=False),
        sa.Column("incident_id", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["demo_incidents.incident_id"],
            name=op.f("fk_demo_incident_notes_incident_id_demo_incidents"),
        ),
        sa.PrimaryKeyConstraint("note_id", name=op.f("pk_demo_incident_notes")),
    )


def downgrade() -> None:
    """Explicit destructive downgrade; disposable development/test DBs only."""
    op.drop_table("demo_incident_notes")
    op.drop_table("memories")
    op.drop_table("knowledge_chunks")
    op.drop_table("effect_receipts")
    op.drop_table("demo_incidents")
    op.drop_table("audit_events")
    op.drop_table("approvals")
    op.drop_table("runs")
    op.drop_table("knowledge_documents")
    op.drop_table("demo_services")
    op.drop_table("demo_notifications")
