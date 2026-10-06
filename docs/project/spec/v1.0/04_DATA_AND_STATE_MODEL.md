# 04 — Data and State Model

## PostgreSQL responsibilities

One PostgreSQL instance is used to minimize operational complexity. pgvector is enabled in the same instance.

Project-owned logical tables:

- `runs`
- `approvals`
- `effect_receipts`
- `audit_events`
- `memories`
- `knowledge_documents`
- `knowledge_chunks`
- `demo_incidents`
- `demo_services`
- `demo_notifications`
- `demo_incident_notes`

LangGraph checkpoint tables are framework-owned and must not be manually repurposed.

## Important invariants

### Runs

- `run_id` is immutable.
- terminal run status cannot silently return to `RUNNING`.
- current `policy_version` is recorded on the run.

### Approvals

- action digest is immutable after creation.
- approval decision is append/audit visible.
- a rejected or expired approval cannot be resurrected.

### Effects

- an effect receipt records `tool_name`, `idempotency_key`, action digest, result digest and application timestamp.
- uniqueness prevents duplicate physical/mock side effects.
- repeated identical request returns the prior receipt explicitly as `replayed=true`.

### Audit events

Append-only at application level. Every event has:

- `event_id`
- `run_id`
- monotonic sequence number within the run
- event type
- event payload with sensitive-field redaction
- timestamp
- trace/span IDs when available

### Knowledge

A chunk binds to the exact content digest of its source document. Re-ingestion replaces/stales chunks from a changed digest rather than mixing versions.

### Memories

Memory is scoped by workspace + user. Deletion is observable in audit history but deleted content is not kept in normal runtime payloads.

## Migration policy

Use SQLAlchemy 2.x + Alembic for project-owned schema. Schema creation must be reproducible from an empty database. No implicit destructive migration is permitted.

## Demo reset

A deterministic reset command/fixture restores fictional OpsDesk state. Evals must not depend on residue from previous runs.
