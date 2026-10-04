# B50 trusted policy, approvals and atomic effects

`policy.Gateway.execute` is the production tool execution surface for later graph
connection. B50 adds no graph or API approval UI. Its project-owned immutable
registry is exactly `opsdesk-v1`: get_incident/get_service_status READ_ONLY;
add_incident_note/restart_service/send_notification SIDE_EFFECT. MCP annotations,
descriptions, model text, retrieval and memory never supply risk authority.

`propose` validates the model-owned shape, mints a fresh opaque UUID key in trusted
runtime for side effects, validates full wire arguments, and uses the existing
canonical action_digest. A key factory is injectable for deterministic tests.
Model callers cannot supply the key. Approval persists the exact run/action/tool,
full wire args, digest and policy version. Decisions lock/reload persisted state.
PENDING can become APPROVED/REJECTED/EXPIRED; APPROVED can become CONSUMED/EXPIRED;
all three terminal statuses prohibit further transitions. Consumption preserves
the original decided_at. No dependency, lock or migration is added.

The gateway revalidates action, run policy version, persisted approval identity,
status and expiry before dispatch. It queries the durable receipt first. Exact
APPROVED + receipt reconciles to CONSUMED; CONSUMED + receipt replays. Conflict or
CONSUMED without receipt fails closed. Exact prior receipts can reconcile after
expiry; expiry without a receipt persists EXPIRED and blocks dispatch. Ambiguous
transport failures propagate without retry. Next execution queries receipts
before another dispatch. The approval row lock spans bounded MCP dispatch; its
lock acquisition runs in a worker so concurrent async callers do not block the
connection owner's event loop. Server receipt transactions are independent.

The non-authorizing MCP server receives binding data through request `_meta`:
`agent-reliability-runtime/run-id` and
`agent-reliability-runtime/action-digest`. These never assert permission. Only
these project keys are read; reserved `io.modelcontextprotocol/*` keys stay SDK
owned. Input signatures remain exactly five and unchanged, including runtime key
ownership. A controlled raw testing surface can supply metadata explicitly.

For the three writes, one PostgreSQL transaction acquires a deterministic signed
64-bit advisory lock from SHA-256(compact JSON [tool,key]), checks existing receipt,
mutates fictional state, hashes the typed internal business result as canonical
UTF-8 JSON, inserts the receipt and commits. Existing unique(tool_name,key) remains
the final backstop. Same run/key/digest returns the original persisted receipt;
different run/digest fails. Unknown run/FK failure rolls back the mutation. No raw
business result payload is retained. Write structured outputs are exactly
receipt_id/run_id/tool_name/idempotency_key/action_digest/result_digest/applied_at/
replayed. Read outputs are unchanged. This explicitly supersedes B40 duplicate
rejection and write business outputs, preserving its input/schema/annotation gates.

Tests use real PostgreSQL and both official in-process and real stdio transports.
They cover zero-dispatch gates, every lifecycle transition, action drift, expiry,
forged hints, malicious text, atomic rollback and FK failure, concurrent same and
conflicting keys, concurrent gateway/decision calls, corrupted reply and lost
reply reconciliation, consumed missing/conflicting receipts, independent typed
result hashing and unrelated sentinels. Existing Ubuntu database CI runs these
through its unchanged integration suite; static jobs retain all earlier gates.

For exact-head evidence on a fresh disposable migrated database:

```text
uv run python -m scripts.probe_policy_effects --output ABSOLUTE_EXTERNAL_EVIDENCE.json
```

The proof creates intended run/approval/effect rows, approves through the service,
uses the actual project stdio adapter, proves runtime reconciliation and direct
server replay, rejects a conflicting digest, and asserts one notification and one
intended receipt with unrelated sentinel preservation. Do not point it at user
state. No Ollama/model call is needed for B50. Primary semantics were checked
against installed MCP 2.3.0 and the official
[SDK client](https://py.sdk.modelcontextprotocol.io/client/) and
[PostgreSQL transaction lock documentation](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS).
