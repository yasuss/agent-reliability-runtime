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

B20 adds separate `ChatProvider.complete(ChatRequest)` and
`EmbeddingProvider.embed(EmbeddingRequest)` protocols in `providers/contracts.py`.
`OpenAICompatibleChatProvider` posts the common non-streaming chat subset to a
configurable base URL ending in `/v1`; `OllamaEmbeddingProvider` posts batches to
the native `/api/embed` endpoint with `truncate=false`. `httpx==0.28.1` moved from
dev-only to runtime; no vendor SDK or retry framework was added.

Configure `HTTPProviderConfig` with explicit provider/model identity, base URL,
finite positive timeout and optional Pydantic `SecretStr` API key. Keys are
excluded from configuration repr. Embedded credentials, query strings and
fragments in URLs are rejected. Clients close after each call, verify TLS,
ignore environment proxy/credential configuration, do not follow redirects and
never retry automatically. Timeout applies to connect/read/write/pool operations;
it is not a wall-clock deadline for the entire inference.

Requests include messages, JSON-object tool schemas, bounded model settings and
local caller trace context. B80 owns trace forwarding/emission. Parsed tool calls
are untrusted data and are never executed. JSON-string and object arguments are
accepted, including multiple calls and absent call IDs; history sent back to the
server requires IDs for assistant tool calls. Optional usage is preserved without
inventing missing token counts. Result identity preserves the server's reported
model, allowing compatible server aliases. Raw provider metadata/reasoning is
discarded; neutral metadata stays empty. Embedding count, uniform nonzero dimension
and finite numeric values are checked; no dimension is hard-coded or stored in DB.

Errors are explicit: `ProviderConfigurationError` before I/O,
`ProviderTransportError` for HTTPX transport/timeouts, `ProviderHTTPError` for
non-2xx status (bounded status-only diagnostic), and `ProviderProtocolError` for
invalid JSON/shape. Errors never retain bodies, headers or raw vendor exceptions
as visible traceback causes. There is no authorization or automatic redaction
of normal model text; callers must not send secrets or treat responses as authority.
