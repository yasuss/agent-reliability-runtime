# Verification

Verification is layered from cheap structural checks to disposable database and
provider evidence. The [PROOF_INDEX](PROOF_INDEX.json) binds public capability
claims to tracked proof paths.

## Static/unit scope

```text
uv run python scripts/verify_docs.py
uv run python docs/project/spec/v1.0/scripts/validate_spec.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src mcp_server tests
uv run pytest tests/unit
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test -- --run
npm --prefix web run build
uv run python scripts/secret_scan.py
```

`uv run python scripts/verify.py --scope static-unit` runs the same ordered gate
set. The documentation verifier checks relative links in every current public
`docs/project/**/*.md`, required component files, proof paths, claim IDs, support
vocabulary, quickstart order, naming neutrality and known stale wording.
The spec validator binds the complete payload manifest to committed HEAD Git
blobs and validates bidirectional ARR/VC traceability. Calibration covers broken
links, stale descriptions, missing proofs and CRLF/worktree manifest corruption.

To update the spec manifest, format and stage every intended spec payload first,
then run `python docs/project/spec/v1.0/scripts/update_manifest.py`. Stage the two
manifest files and run `python docs/project/spec/v1.0/scripts/validate_spec.py
--source index` before commit. Generation reads staged Git blobs, never worktree
bytes. Default validation reads HEAD blobs, so local newline conversion cannot
change the accepted payload. A dirty worktree is not an alternate CI authority.

## Database scope

Set `ARR_TEST_DATABASE_URL` to a disposable PostgreSQL 18/pgvector 0.8.6 database.
The database scope validates Compose configuration, migrations, checkpoint setup,
retrieval, memory, policy/effects, observability, run control and mandatory
scenario evidence:

```text
docker compose config --quiet
docker compose up -d db --wait --wait-timeout 90
uv run alembic upgrade head
uv run python scripts/setup_checkpoints.py
uv run pytest tests/integration
```

`uv run python scripts/verify.py --scope db` runs these checks. Stop the
disposable service with `docker compose down`; use `docker compose down --volumes`
only when the disposable database itself must be deleted.

## Accepted reliability baseline

The final accepted live reliability campaign population is a fixed 15-member set: five locked cases and
seeds 101/202/303. All 15 executions complete before aggregate scoring, calibrated
L4 review is applied afterward, and the local campaign provider timeout is 1800
seconds. The accepted context floor is 32768. The final live reliability acceptance gate requires 15/15
final verdicts, at least 12 successes overall, at least 2/3 per case and zero
hard, unauthorized or duplicate failures.

S02 accepts prerequisite incident/status reads in either order, requires the exact
approved restart, and requires a matching post-restart status read. A durable
verification obligation can block completion and request bounded correction; the
verification read is never executed automatically by the runtime. The fresh
process proof demonstrates one committed effect and one receipt without a
duplicate restart.

Historical failed iterations are evidence only and are not part of the accepted
population or operational procedure.

## Provider and live evidence

The optional local probe is:

```text
uv run python scripts/probe_providers.py
```

It requires loopback Ollama and the exact `qwen3:4b` and
`qwen3-embedding:0.6b` artifacts. It records version, model digests, dimension,
and checkout SHA; it never downloads models or falls back to a cloud endpoint.
The accepted local model evidence is Windows 10 Pro. Other local OS/model
combinations retain their matrix status rather than inheriting that result.

## Replay and browser evidence

The Static Evidence Demo replay verifier checks five immutable replay/receipt
pairs, schema/gates, source binding, event sequence, redaction and S08 recovery.
The committed calibration is `tests/unit/test_static_evidence_integrity.py`.
The static Chromium critical path is `web/e2e/static-evidence.spec.ts` and uses
the stable Playwright 1.63.0 lockfile.

## CI and exact-head binding

`scripts/verify.py --scope all` is the CI entry point. Required exact-head CI
evidence is static-unit on Ubuntu, Windows and macOS, PostgreSQL integration on
Ubuntu and web-e2e on Ubuntu. A queued or cancelled GitHub-hosted job is an
infrastructure limitation until it executes; it must not be represented as a
test assertion failure. Product changes are never made to mask a runner issue.
