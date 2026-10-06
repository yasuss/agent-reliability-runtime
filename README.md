# Agent Reliability Runtime

## What it is

Agent Reliability Runtime is a local-first reference implementation for one
durable, tool-using LangGraph agent. It combines fictional OpsDesk state,
retrieval, governed memory, trusted policy, exact approval, idempotent effects,
postcondition verification, OTel/audit evidence and deterministic evaluation.

## Reliability properties

The runtime treats model, retrieval, memory and MCP content as untrusted data.
Side effects require schema validation, trusted policy and an exact approval.
PostgreSQL-backed checkpoints and effect receipts cover process restart and
duplicate delivery. The accepted capability map is tied to the machine-readable
[PROOF_INDEX](docs/project/PROOF_INDEX.json).

| Capability | Proof ID |
| --- | --- |
| Provider boundary | `provider-boundary` |
| Hybrid retrieval and citations | `hybrid-retrieval-citations` |
| Five-tool MCP boundary | `mcp-five-tools` |
| Deterministic policy | `deterministic-policy` |
| Exact approval | `exact-approval` |
| Idempotent side effects | `idempotent-side-effects` |
| Durable restart | `durable-restart` |
| Governed memory | `governed-memory` |
| OTel and audit | `otel-audit` |
| Evaluation harness | `eval-harness` |
| Adversarial scenarios | `adversarial-scenarios` |
| Static Evidence Demo | `static-evidence-demo` |

## Architecture at a glance

The current flow is memory scope -> retrieval -> model -> typed actions ->
trusted policy -> approval -> idempotent effect -> postcondition verification ->
result -> audit/OTel/evaluation. See the [architecture](docs/project/ARCHITECTURE.md)
for ownership and data-flow details.

## Quickstart

Prerequisites: Git, uv 0.12.23, Python 3.12, Node.js 24 with npm, and Docker
Desktop/Engine with Compose and Linux containers.

```text
python scripts/bootstrap.py
uv run python scripts/reset_demo.py --confirm-development-reset
uv run python scripts/verify.py --scope all
```

These commands use a disposable local PostgreSQL/pgvector database and do not
require Ollama. Bootstrap installs locked dependencies, starts Compose and runs
migrations/checkpoint setup. Reset restores only fictional `demo_*` state. The
third command runs the documentation, static, frontend and database gates.

## Optional live local model path

The deterministic quickstart is independent of model availability. Live local
inference uses Ollama with exactly `qwen3:4b` for chat and
`qwen3-embedding:0.6b` for embeddings:

```text
ollama pull qwen3:4b
ollama pull qwen3-embedding:0.6b
uv run python scripts/probe_providers.py
```

The probe never downloads models automatically and accepts only a loopback Ollama
server. Ingestion, runs, approvals and live evaluation are documented in
[Operations](docs/project/OPERATIONS.md).

## Verification

The fail-fast verifier runs Ruff, mypy, unit tests, web checks, the documentation
truth gate and the deterministic secret scan. Database verification uses an
explicit disposable `ARR_TEST_DATABASE_URL`; CI runs PostgreSQL integration on
Ubuntu and static/unit gates on Ubuntu, Windows and macOS. See
[Verification](docs/project/VERIFICATION.md) for exact scopes and evidence.

## Static Evidence Demo

The web app is a static recorded-replay viewer. It has no backend, live inference
or arbitrary prompt input. Five accepted replay/receipt pairs are checked by
`scripts/verify_static_evidence.py`; the critical Chromium path is covered by
`web/e2e/static-evidence.spec.ts`.

## Support and limitations

See the [support matrix](docs/project/SUPPORT_MATRIX.md) for TESTED versus
EXPECTED environments and [limitations](docs/project/LIMITATIONS.md) for claim
boundaries. Development Compose credentials are fictional and must not be
deployed.

## License and public API

This candidate is licensed under the [Apache License 2.0](LICENSE). SECURITY.md
describes responsible disclosure. The documented runtime, configuration, tool
and evidence contracts form the public v1 interface; arbitrary internal Python
symbols are not guaranteed API. Candidate preparation does not publish the
repository, create a release, or deploy the Static Evidence Demo.

## Documentation map

- [Architecture](docs/project/ARCHITECTURE.md)
- [Operations](docs/project/OPERATIONS.md)
- [Verification](docs/project/VERIFICATION.md)
- [Support Matrix](docs/project/SUPPORT_MATRIX.md)
- [Limitations](docs/project/LIMITATIONS.md)
- [Evidence & Proof](docs/project/EVIDENCE_AND_PROOF.md)
- [Project truth map](docs/project/README.md)
- [Release and deployment operations](docs/project/RELEASE_AND_DEPLOYMENT.md)
- [Public release checklist](docs/project/PUBLIC_RELEASE_CHECKLIST.md)
- [Security policy](SECURITY.md)
