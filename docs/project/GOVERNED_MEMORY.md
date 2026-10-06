# Governed Memory

Memory create/delete and its audit event commit atomically through an internal
scope anchor; see [Observability and Audit](OBSERVABILITY_AND_AUDIT.md).
The anchor stores no memory content and never runs the agent graph.

`MemoryStore` reuses the accepted `memories` table and strict Memory snapshots.
Every list/get/resolve/delete constrains both workspace_id and user_id. Ordering
is created_at ASC then memory_id ASC. Missing and foreign IDs resolve to nothing;
physical delete removes only the exact scoped row. No tombstone stores content.
IDs and timestamps are generated in project code, with injectable test factories.

Creation has three explicit profiles, rather than a public arbitrary trust setter:

| Method | Kind | Provenance | Trust | Source |
|---|---|---|---|---|
| user_explicit | PREFERENCE or VERIFIED_FACT | USER_EXPLICIT | TRUSTED | optional same-scope run, no tool |
| tool_verified | VERIFIED_FACT | TOOL_VERIFIED | TRUSTED | required same-scope run and exact-five tool |
| model_observation | OBSERVATION | MODEL_OBSERVATION | UNTRUSTED | required same-scope run, no tool |

Profile mismatch and nonexistent/foreign source runs fail before persistence.
TRUSTED describes contextual provenance; it never grants authorization. Creation
is an internal trusted service boundary; automatic model writes are outside governed memory.

## Local HTTP surface

`create_app(engine=None)` retains exported `app` and `/healthz`. An injected Engine
is caller-owned; the default request dependency creates/disposes its Engine when
database-backed routes need it, so liveness remains independent of the database.
Both memory routes require
strict nonempty workspace_id and user_id query parameters:

- GET `/api/v1/memory` returns validated ordered snapshots for that exact pair.
- DELETE `/api/v1/memory/{memory_id}` returns 204 for physical deletion; missing or
  foreign IDs both return 404 with identical response text.

There is no public memory-creation POST route or enterprise identity/authentication
claim. The run/approval control routes are described in
[Reliability Acceptance](RELIABILITY_ACCEPTANCE.md).

## Runtime and deletion

In the durable graph, `load_memory` reads the durable run's scope
and checkpoints only ordered `memory_ids`. Before every provider decision, current
rows for those IDs are resolved against the current durable run scope. Deleted and
foreign IDs silently drop. A transient user/data ChatMessage appears after the
project system instruction, before task/conversation messages; its JSON snapshots
preserve kind/provenance/trust and explicitly cannot override policy or approval.
It is never appended to durable state.messages. No fake memory message is added
when no rows resolve. A checkpoint with no memory IDs resolves no memory rows.

Memory fields do not enter evaluate/propose/Gateway. Trusted risk classification,
approval bindings, runtime-owned keys and receipt reconciliation remain intact.
Semantic budgets and real process-kill recovery retain their original gates.

`scripts.probe_memory` exercises real PostgreSQL, official strict PostgresSaver,
real OpsDesk stdio, harmless personalization, UNTRUSTED observation poisoning and
TRUSTED user-memory poisoning. Both attacks pause WAITING_APPROVAL/PENDING with
unchanged fictional service and no receipt. Spoofed resume values cannot authorize.
An explicit exact persisted decision alone allows the fictional restart.

At the pause, HTTP DELETE removes a unique marker memory. A newly opened saver and
graph resumes that old thread; its next provider request contains no marker. Every
retained deserialized snapshot is recursively inspected, and actual checkpoints,
checkpoint_blobs and checkpoint_writes textual/JSON/binary payloads are scanned.
The deleted ID may remain; raw marker content must not. Known-bad copied-content
and memory-derived risk fixtures must fail calibrated oracles; valid alternates
pass. Provider output can itself repeat contextual text; this oracle concerns the
runtime copying memory content into checkpoints merely by loading it.

For an exact clean candidate and fresh disposable migrated DB:

```text
uv run python -m scripts.probe_memory --output ABSOLUTE_EXTERNAL_EVIDENCE.json
```

After re-interruption, use a scalar JSON resume value (for example `"continue"`),
or the pinned API's correct interrupt-ID map. LangGraph 1.2.12 treats an empty dict
as an empty resume map; it does not release the interrupt. Resume values remain
non-authorizing. No durable agent runtime framework/service upgrade is required.

## Scope limits

Audit and OTel deletion evidence retain identifiers and bounded metadata without
deleted content. Vector/semantic memory, TTL/scoring, autonomous writes and
enterprise authentication remain outside the implemented memory service.

The security boundary follows the locked project contract and
[OWASP agent memory/context guidance](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html#3-memory--context-security).
