# OpsDesk MCP Boundary

The repository module `python -m mcp_server.opsdesk` runs the official MCPServer
over local stdio. Use the current locked Python environment and repository root.
The child has exactly five tools; no resources/prompts are registered. Protocol
stdout belongs to the SDK; application logging goes to stderr. The server reads
the existing database configuration. trusted execution now atomically couples fictional
`demo_*` writes with `effect_receipts`; read tools remain unchanged.

| Tool | Wire required fields | Model required fields |
|---|---|---|
| get_incident | incident_id | incident_id |
| get_service_status | service_id | service_id |
| add_incident_note | incident_id, note, idempotency_key | incident_id, note |
| restart_service | service_id, reason, idempotency_key | service_id, reason |
| send_notification | channel, message, idempotency_key | channel, message |

All fields are strict nonempty strings, with extra fields forbidden. Project-owned
input models validate raw arguments before SDK coercion/filtering. The high-level
server's public list/call hooks publish the same schemas and reject invalid args.
Typed structured outputs are validated again by the project client. Errors are
bounded, with no SQL, connection string or traceback on the wire. A note or
notification row ID hashes compact JSON [tool_name, idempotency_key]. trusted execution supersedes
the original duplicate-error behavior: all three write tools now return a durable
receipt envelope, and exact run/key/digest repeats replay without another effect.
Restart still locks a known fictional service and sets its status to healthy.
A clock can be injected for fixed UTC tests.

**Raw mutation calls remain non-authorizing infrastructure.** Production execution
enters the trusted execution gateway. MCP annotations remain advisory and do not determine
field ownership or authorization. Model schemas omit runtime-owned idempotency_key;
trusted execution mints it before approval. See [trusted execution semantics](trusted execution_POLICY_EFFECTS.md).

OpsDeskMCPClient wraps official Client(StdioServerParameters), with current Python,
explicit module args/repository cwd and only ARR_DATABASE_URL as the explicit env
addition. The SDK adds its own documented environment allowlist. Parent environment
is never copied wholesale. Read calls exclude mutations; the explicitly named
raw_wire_call_for_testing is infrastructure/test-only. Tool catalog and semantic
schemas must match exactly; annotation-only titles/descriptions and property order
may vary. A sixth/missing/renamed tool or field/schema ownership drift fails.
is_error is checked before structured_content, then the project output model
validates every successful result.

Preflight uses plain mcp==2.3.0, not the CLI extra. The only lock version delta is
mcp and its exact required mcp-types 2.2.0 -> 2.3.0. Primary SDK sources:
[Client](https://py.sdk.modelcontextprotocol.io/client/),
[tools](https://py.sdk.modelcontextprotocol.io/servers/tools/),
[exact release metadata](https://pypi.org/project/mcp/2.3.0/).

On a fresh disposable migrated DB and clean exact-head checkout, run:

```text
uv run python scripts/probe_opsdesk.py --output ABSOLUTE_EXTERNAL_EVIDENCE_PATH.json
```

This resets fictional demo state, seeds one sentinel in each of the seven existing
non-demo evidence tables, calls all three raw mutations with binding metadata,
asserts exactly three intended receipts while preserving unrelated sentinels, checks exact receipt replays and
invalid/unknown calls leave state unchanged, and retains exact schemas, protocol,
server identity, output/state digests, annotation/schema calibration and official
context shutdown. Never run it against user or production state. Integration tests
exercise both in-process Client(server) and real stdio on PostgreSQL; the latter
runs in the existing Ubuntu database CI job. Windows/macOS/Ubuntu static jobs keep
all earlier checks. No model calls/downloads are added.
