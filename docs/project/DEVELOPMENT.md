# Development

Development structure/backlog: `spec/v1.0/09_TARGET_REPOSITORY_STRUCTURE.md`, `10_ENGINEERING_BACKLOG.md`, and current Architect task package.

B10 implements `contracts/domain.py`, SQLAlchemy Core metadata in
`persistence/schema.py`, validated snapshot inserts and locked lifecycle updates
in `persistence/records.py`, and Alembic revision `0002_domain` over B00's
`0001_foundation`. The migration has a frozen explicit schema; it does not import
live metadata. No framework checkpoint tables are created.

Use `uv run alembic upgrade head`, then explicitly seed a development/test DB:
`uv run python scripts/reset_demo.py --confirm-development-reset`. The CLI and
library require destructive reset confirmation. Reset owns only demo notes,
notifications, incidents and services; it never deletes evidence tables.
`data/seed/demo_state.json` matches the locked fixture and is checked for drift.

Contract snapshots forbid extra fields and are frozen. Timestamps normalize to
UTC and naive timestamps fail. Use validated reconstruction, never
`model_copy(update=...)`, as the validation boundary. JSON dictionaries themselves
are mutable: snapshot inserts revalidate them, and SQLAlchemy Core operations
replace whole JSONB values explicitly. No implicit ORM mutation tracking is used.

Approval identity/digest cannot be changed by the lifecycle persistence API.
Terminal runs cannot return to non-terminal status; rejected/expired approvals
cannot be resurrected. Audit snapshots expose only insertion. These are application
contracts, not protection against arbitrary administrative SQL; B50/B80 own
execution authorization, decision auditing, sequence allocation and redaction.
Audit payloads here must already be safe/redacted by their trusted caller.

Knowledge IDs derive from normalized repository-relative paths; chunk IDs derive
from document ID, exact digest and ordinal. A composite FK binds chunks to the
document's current digest. Re-ingestion/replacement and vector/search columns
remain B30 work. Effect uniqueness is enforced on `(tool_name, idempotency_key)`;
same-key replay and digest reconciliation remain B50 work. Foreign keys do not
cascade-delete retained evidence.
