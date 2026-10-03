# Agent Reliability Runtime

A local-first reliability reference implementation. **B00 foundation only:**
the runtime, approvals, MCP tools, retrieval, memory and accepted replay gallery
are not implemented yet. The locked design is in [docs/project](docs/project/README.md).

## Development

Prerequisites: Git, uv 0.12.23, Python 3.12 managed by uv, Node 24 with npm,
and Docker Desktop/Engine with Compose and Linux containers.

```text
python scripts/bootstrap.py
uv run python scripts/verify.py --scope static-unit
uv run alembic upgrade head
uv run uvicorn agent_reliability_runtime.api:app --host 127.0.0.1
npm --prefix web run dev
```

The bootstrap script installs both committed lockfiles and explicitly starts and
migrates the development database. `/healthz` reports process liveness only.
The web build is static and does not call the backend.

Compose binds PostgreSQL to **127.0.0.1** and uses a public fictional development
password by default. This configuration is exclusively for local development;
never deploy it. `.env.example` lists optional overrides. Compose reads `.env`;
Python reads environment variables, so export the same override values to both.
No real token or credential is needed. Set `ARR_DB_PORT` if 5432 is occupied.

For DB verification, set `ARR_TEST_DATABASE_URL` explicitly to your disposable
development database (default:
`postgresql+psycopg://arr:local-development-fixture@127.0.0.1:5432/arr`), then run:

```text
uv run python scripts/verify.py --scope db
uv run pytest
```

For a clean-state migration rehearsal, use a unique Compose project name via
`COMPOSE_PROJECT_NAME` and a free `ARR_DB_PORT`. Bootstrap creates a fresh named
volume. `docker compose down --volumes` **deletes that project's development DB**;
use only with a disposable project. Downgrading B00 preserves the pgvector
extension because it may have existed before this revision.

Target support is Windows 11, macOS and Linux. Local execution so far is on
Windows 10 Pro; that does not prove Windows 11. CI separately verifies its actual
Windows/macOS/Ubuntu runners; full DB integration runs on Ubuntu. No full agent,
Ollama or cross-platform model compatibility is claimed by B00.

TLS-intercepting environments may need `UV_SYSTEM_CERTS=true` and
`NODE_OPTIONS=--use-system-ca`. Certificate verification stays enabled.
On Windows ensure hardware virtualization, WSL2 and required Windows features
are enabled, restart if requested, and start Docker Desktop before bootstrap.

## Verification and scope

`scripts/verify.py` runs fail-fast checks shared with CI. Secret scanning covers
known token/private-key patterns and a forbidden-marker control in UTF-8 source;
it is deterministic but not an exhaustive credential detector. Its calibration
tests include positive, negative and valid alternate inputs. Command-runner tests
prove a failure stops later checks.

No license/publication choice is made in B00. No merge or release is implied.
