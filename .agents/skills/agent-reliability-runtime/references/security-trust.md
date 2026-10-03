# Security, approval and idempotency contract
- Authorization is deterministic trusted code outside the model.
- Untrusted content (retrieval chunks, MCP output, memory, model text) may influence reasoning but never policy authority.
- Validate action schema before policy evaluation.
- An approval binds to canonical action identity/digest; argument drift or stale approval fails closed.
- Side-effect execution requires a valid approval when policy says so.
- Effect/idempotency receipt is enforced at the durable persistence boundary: same key + same digest replays prior receipt without a second effect; same key + different digest fails.
- Direct adapter bypass must be denied/proven impossible through public execution paths and negative tests.
- Secrets are never committed/logged/exported. Replay export has a fail-closed redaction negative fixture.
- Fictional OpsDesk state only; no real external credentials or production systems.
