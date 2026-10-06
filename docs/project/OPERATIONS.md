# Operations

These procedures target the local fictional OpsDesk environment. They use only
tracked scripts and commands. Keep command output and live campaign artifacts in
an external directory rather than tracked source.

## Local topology and process ownership

Compose owns the disposable PostgreSQL/pgvector `db` service. The API, CLI and
MCP stdio server are developer-owned processes. The web build is a static asset
viewer. Check process ownership before stopping anything; do not kill an
unrelated PostgreSQL or Ollama process.

The default database binds to `127.0.0.1:${ARR_DB_PORT:-5432}`. `ARR_DB_PORT`
changes the host port in Compose. Python database clients use
`ARR_DATABASE_URL` when set; integration tests require an explicit
`ARR_TEST_DATABASE_URL` pointing at the same disposable database.

## Bootstrap and migrate

Prerequisites are Git, uv 0.12.23, Python 3.12, Node 24/npm and Docker
Desktop/Engine with Linux containers. The complete deterministic path is:

```text
python scripts/bootstrap.py
uv run alembic upgrade head
uv run python scripts/setup_checkpoints.py
```

Bootstrap installs the locked Python and web dependencies, validates Compose,
starts PostgreSQL and applies migrations/checkpoint setup. Re-running migration
commands is safe for the same disposable database.

## Reset fictional OpsDesk state

Reset is an explicit destructive operation on the four `demo_*` tables:

```text
uv run python scripts/reset_demo.py --confirm-development-reset
```

It restores fictional services/incidents and clears demo notes/notifications
while preserving runtime, approval, effect, audit, memory and knowledge evidence.
Never aim this command at production data.

## Start/stop PostgreSQL safely

```text
docker compose config --quiet
docker compose up -d db --wait --wait-timeout 90
docker compose down
```

`docker compose down` stops the disposable service while retaining its named
volume. `docker compose down --volumes` deletes that project's database and is
reserved for a disposable proof project. Use a unique `COMPOSE_PROJECT_NAME` and
free `ARR_DB_PORT` for clean-checkout rehearsals.

## Static Evidence Demo

The viewer is static-only and shows recorded evidence. Build and verify it with:

```text
npm --prefix web ci
npm --prefix web run build
python scripts/verify_b110_replays.py
npm --prefix web exec -- playwright test --config web/playwright.config.ts
```

It has no backend, live inference or arbitrary prompt input and cannot approve or
run live actions.

## Provision and verify Ollama models

Ollama is optional for deterministic verification and required only for live local
inference. Provision exactly:

```text
ollama pull qwen3:4b
ollama pull qwen3-embedding:0.6b
uv run python scripts/probe_providers.py
```

The probe is loopback-only, records `/api/version`, model digests and the exact
checkout SHA, and does not download or cloud-fallback. Keep live output external.

## Ingest the six locked knowledge sources

After migrations and with Ollama running, ingest the six canonical files:

```text
uv run python -m agent_reliability_runtime.cli ingest data/knowledge/policy-approvals.md data/knowledge/policy-retries.md data/knowledge/runbook-checkout.md data/knowledge/runbook-search.md data/knowledge/service-catalog.md data/knowledge/untrusted-vendor-note.md
```

The source bytes must match the six locked fixtures under
`docs/project/spec/v1.0/fixtures/knowledge/`. Re-ingestion is digest-aware.

## Run a local task/scenario

```text
uv run python -m agent_reliability_runtime.cli run --scenario S01_READ_ONLY_GROUNDED --workspace-id local --user-id operator
uv run python -m agent_reliability_runtime.cli run --task "Inspect checkout-api" --workspace-id local --user-id operator
```

The API equivalents are `POST /api/v1/runs` and `GET /api/v1/runs/{run_id}`.
`/healthz` is process liveness; `/readyz` includes the readiness contract.

## Approve or reject a pending side effect

Inspect the run and its pending approval, then send exactly one decision through
the local control surface:

```text
POST /api/v1/runs/{run_id}/approvals/{approval_id}
{"decision":"APPROVE"}
```

Use `REJECT` for a denial. Ownership, interrupt identity, action digest and
approval status are checked before resume. The API is a local control surface;
it is not an enterprise authentication boundary.

## Deterministic mandatory evaluation

Run calibration first, then the complete locked S01-S12 suite. Keep output
outside the repository:

```text
uv run python -m agent_reliability_runtime.cli eval --calibrate
uv run python -m agent_reliability_runtime.cli eval --mandatory --output C:\temp\arr-evidence
```

Mandatory evaluation uses scripted providers and deterministic/environment-state
oracles. It does not require Ollama.

## Live local acceptance campaign

The accepted final campaign uses qwen3:4b, the accepted embedding artifact,
context 32768, timeout 1800 seconds, five locked cases and seeds 101/202/303.
Complete deterministic gates and freeze the candidate before any live run. Keep
campaign output external:

```text
uv run python -m agent_reliability_runtime.cli eval --live-local --phase freeze --output C:\temp\arr-r10
uv run python -m agent_reliability_runtime.cli eval --live-local --phase next --output C:\temp\arr-r10
uv run python -m agent_reliability_runtime.cli eval --live-local --phase finalize --trial-id ID --review C:\temp\review.json --output C:\temp\arr-r10
uv run python -m agent_reliability_runtime.cli eval --live-local --phase summary --output C:\temp\arr-r10
```

All 15 executions complete before aggregate; calibrated L4 review follows
execution. Never replace a started trial or tune code, prompts, settings or
checkers after campaign start.

## Replay export

Export only from a successful receipt and a clean exact candidate:

```text
uv run python -m agent_reliability_runtime.cli export-replays --run-id RUN_ID --receipt C:\temp\receipt.json --source-git-sha EXACT_SHA --output C:\temp\replay
```

The B110 verifier must pass before treating the static replay as accepted.

## Cleanup

Stop developer processes you started, then stop Compose:

```text
docker compose down
```

For a disposable proof project only, remove its data with
`docker compose down --volumes`. Keep Ollama installed models unless explicitly
removing them is part of a separate maintenance task.

## Troubleshooting

- Port 5432 occupied: choose a free `ARR_DB_PORT` and put the matching port in
  `ARR_TEST_DATABASE_URL`.
- Compose not ready: inspect `docker compose ps` and `docker compose logs db`.
- Database URL mismatch: export the same explicit disposable URL for Python and
  test commands.
- Ollama unavailable: deterministic quickstart and mandatory eval remain usable;
  live probe/eval must wait for the local server and exact models.
- Git `safe.directory` ownership failure: use a user-owned checkout. Do not weaken
  global Git safety as a workaround.
- CI job queued or cancelled without assertions: retain that as infrastructure
  evidence and use same-SHA job-level rerun when runner capacity is available.
