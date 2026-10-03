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
