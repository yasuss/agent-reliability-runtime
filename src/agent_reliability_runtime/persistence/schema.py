"""SQLAlchemy Core metadata. JSONB updates use explicit value replacement."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from agent_reliability_runtime.contracts.domain import (
    ApprovalStatus,
    MemoryKind,
    MemoryProvenance,
    MemoryTrust,
    RunStatus,
)

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    }
)


def finite(
    column: str,
    values: type[RunStatus]
    | type[ApprovalStatus]
    | type[MemoryKind]
    | type[MemoryProvenance]
    | type[MemoryTrust],
    name: str,
) -> CheckConstraint:
    members = ",".join(f"'{item.value}'" for item in values)
    return CheckConstraint(f"{column} IN ({members})", name=name)


runs = Table(
    "runs",
    metadata,
    Column("run_id", Text, primary_key=True),
    Column("workspace_id", Text, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("request_text", Text, nullable=False),
    Column("scenario_id", Text),
    Column("provider_id", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("policy_version", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("model_steps", Integer, nullable=False),
    Column("tool_steps", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("terminal_reason", Text),
    finite("status", RunStatus, "ck_runs_status"),
    CheckConstraint("model_steps >= 0", name="ck_runs_model_steps"),
    CheckConstraint("tool_steps >= 0", name="ck_runs_tool_steps"),
)

approvals = Table(
    "approvals",
    metadata,
    Column("approval_id", Text, primary_key=True),
    Column("run_id", Text, ForeignKey("runs.run_id"), nullable=False),
    Column("action_id", Text, nullable=False),
    Column("tool_name", Text, nullable=False),
    Column("normalized_args", JSONB, nullable=False),
    Column("action_digest", Text, nullable=False),
    Column("policy_version", Text, nullable=False),
    Column("risk_class", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
    Column("expires_at", DateTime(timezone=True)),
    finite("status", ApprovalStatus, "ck_approvals_status"),
    CheckConstraint("risk_class = 'SIDE_EFFECT'", name="ck_approvals_risk"),
    CheckConstraint("action_digest ~ '^[0-9a-f]{64}$'", name="ck_approvals_digest"),
)

effect_receipts = Table(
    "effect_receipts",
    metadata,
    Column("receipt_id", Text, primary_key=True),
    Column("run_id", Text, ForeignKey("runs.run_id"), nullable=False),
    Column("tool_name", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False),
    Column("action_digest", Text, nullable=False),
    Column("result_digest", Text, nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "tool_name", "idempotency_key", name="uq_effect_receipts_identity"
    ),
    CheckConstraint("action_digest ~ '^[0-9a-f]{64}$'", name="ck_effect_action_digest"),
    CheckConstraint("result_digest ~ '^[0-9a-f]{64}$'", name="ck_effect_result_digest"),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("event_id", Text, primary_key=True),
    Column("run_id", Text, ForeignKey("runs.run_id"), nullable=False),
    Column("sequence_number", Integer, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("trace_id", Text),
    Column("span_id", Text),
    UniqueConstraint("run_id", "sequence_number", name="uq_audit_events_sequence"),
    CheckConstraint("sequence_number > 0", name="ck_audit_events_sequence"),
)

memories = Table(
    "memories",
    metadata,
    Column("memory_id", Text, primary_key=True),
    Column("workspace_id", Text, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("provenance", Text, nullable=False),
    Column("trust", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("source_run_id", Text, ForeignKey("runs.run_id")),
    Column("source_tool_name", Text),
    finite("kind", MemoryKind, "ck_memories_kind"),
    finite("provenance", MemoryProvenance, "ck_memories_provenance"),
    finite("trust", MemoryTrust, "ck_memories_trust"),
    CheckConstraint("length(content) > 0", name="ck_memories_content"),
)

knowledge_documents = Table(
    "knowledge_documents",
    metadata,
    Column("document_id", Text, primary_key=True),
    Column("source_path", Text, nullable=False),
    Column("content_digest", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("metadata", JSONB, nullable=False),
    UniqueConstraint("source_path", name="uq_knowledge_documents_path"),
    UniqueConstraint(
        "document_id", "content_digest", name="uq_knowledge_documents_version"
    ),
    CheckConstraint("content_digest ~ '^[0-9a-f]{64}$'", name="ck_knowledge_digest"),
)

knowledge_chunks = Table(
    "knowledge_chunks",
    metadata,
    Column("chunk_id", Text, primary_key=True),
    Column("document_id", Text, nullable=False),
    Column("document_digest", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("content", Text, nullable=False),
    ForeignKeyConstraint(
        ["document_id", "document_digest"],
        ["knowledge_documents.document_id", "knowledge_documents.content_digest"],
        name="fk_knowledge_chunks_document_version",
    ),
    UniqueConstraint(
        "document_id", "document_digest", "ordinal", name="uq_knowledge_chunks_ordinal"
    ),
    CheckConstraint("ordinal >= 0", name="ck_knowledge_chunks_ordinal"),
)

demo_services = Table(
    "demo_services",
    metadata,
    Column("service_id", Text, primary_key=True),
    Column("status", Text, nullable=False),
)
demo_incidents = Table(
    "demo_incidents",
    metadata,
    Column("incident_id", Text, primary_key=True),
    Column("service_id", Text, ForeignKey("demo_services.service_id"), nullable=False),
    Column("summary", Text, nullable=False),
    Column("status", Text, nullable=False),
)
demo_notifications = Table(
    "demo_notifications",
    metadata,
    Column("notification_id", Text, primary_key=True),
    Column("channel", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
demo_incident_notes = Table(
    "demo_incident_notes",
    metadata,
    Column("note_id", Text, primary_key=True),
    Column(
        "incident_id", Text, ForeignKey("demo_incidents.incident_id"), nullable=False
    ),
    Column("note", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
