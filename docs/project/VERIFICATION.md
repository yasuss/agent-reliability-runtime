# Verification

Verification source: `spec/v1.0/07_EVALS_AND_SCENARIOS.md` and `11_ACCEPTANCE_GATES.md`.

B10's bounded commands, after locked install and migration, are:

```text
uv run pytest tests/unit -k "contract or digest or transition"
uv run pytest tests/integration -k "schema or effect or audit or reset or migration"
uv run python scripts/verify.py --scope all
uv run pytest
```

Set `ARR_TEST_DATABASE_URL` to an explicitly disposable PostgreSQL 18 database.
Integration tests create/drop isolated random test schemas there, apply real
Alembic migrations, and retain pgvector 0.8.6. They prove empty DB table creation,
B00/B10 round-trip, metadata agreement, finite CHECK failures, effect/audit
uniqueness, exact knowledge-version FKs and immutable lifecycle operations.
Reset proof seeds all seven non-demo tables, dirties all four demo tables and
checks two identical resets with every non-demo row unchanged. Intentional DB
corruption must fail the same reset oracle. Unit tests calibrate contracts,
digest drift, fixture drift and workflow trigger/check preservation with good,
bad and valid alternate controls. Existing B00 checks remain enabled.

CI runs static/unit on Windows, macOS and Ubuntu, and live DB tests on Ubuntu,
for `codex/**` pushes and PRs targeting `main` or `codex/**`. Exact head evidence
requires both push and stacked-PR runs. This is B10 proof; full product gates
G3+ (retrieval, MCP, authorization, restart, evals, replay) are not claimed.

B20 deterministic tests: `uv run pytest tests/unit/test_providers.py`. Mock HTTP
fixtures prove the configurable OpenAI/vLLM request shape and auth header, normal
text, multiple tool calls, JSON-string/object argument alternatives, optional
usage, malformed wire shapes, finite embedding batches, explicit transport/HTTP
errors, no hidden retries/redirects and credential-free diagnostics/repr. Bad
NaN/Infinity/null fixtures use raw response bytes so the actual parser sees them.

Live acceptance is explicit and excluded from ordinary tests/CI:
`uv run python scripts/probe_providers.py`. It requires local Ollama at
`http://127.0.0.1:11434` (optional `--base-url` must remain loopback), records version,
model artifact digests and exact checkout SHA, and calls both project adapters.
It requires nonempty usable chat text from `qwen3:4b`, then two equal-size finite
vectors from `qwen3-embedding:0.6b`, reporting the observed dimension and vector
hash without writing vector DB columns. The fixed prompts contain fictional data.
Run after all behavior-affecting changes on the exact final candidate. No cloud
fallback or live vLLM claim is made; vLLM compatibility is a deterministic common
wire-contract proof. Repeat full bootstrap/verification in a fresh checkout and
new disposable DB volume before the implementation push.
