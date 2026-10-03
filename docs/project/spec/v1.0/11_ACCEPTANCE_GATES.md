# 11 — Acceptance Gates

A later gate cannot waive an earlier hard failure. Any behavior-affecting repair stales affected evidence.

## G0 — Contract integrity

PASS when implementation can be traced to the v1 product contract and no prohibited scope expansion has been introduced.

## G1 — Clean bootstrap

From a fresh clone on the tested environment:

- documented dependencies install;
- Postgres/pgvector starts;
- migrations apply;
- seed/reset succeeds;
- backend starts;
- web build succeeds.

## G2 — Static and unit quality

Required:

- Ruff format/lint PASS;
- mypy PASS for project-owned Python code;
- Python unit tests PASS;
- frontend typecheck/lint/unit tests PASS;
- no committed secret detected by the project's chosen deterministic scan.

## G3 — Persistence and retrieval

Required:

- migrations from empty DB PASS;
- RAG thresholds PASS;
- changed-source staleness test PASS;
- memory scope test PASS;
- effect uniqueness test PASS.

## G4 — MCP and policy boundary

Required:

- exact five tools callable through MCP;
- invalid tool/arguments rejected;
- all side-effect tools blocked without exact approval;
- annotations cannot elevate authority.

## G5 — Durable execution

Required:

- LangGraph uses PostgreSQL checkpointer;
- approval can pause and resume;
- a real process termination + fresh process resumes S08;
- loop ends on hard step budget;
- no in-memory-only durability claim.

## G6 — Side-effect safety

Zero-tolerance:

- unauthorized side effects = 0;
- duplicate physical/mock side effects in S09 = 0;
- stale approval acceptance = 0;
- same idempotency key with different action digest must fail.

Any failure blocks release.

## G7 — Security adversarial suite

S05, S06, S10 and direct bypass variants must pass. Retrieved/tool/memory text may influence model reasoning but cannot alter trusted policy behavior.

Replay export secret-redaction negative fixture must fail closed.

## G8 — Behavioral evaluation

Default Ollama model run:

- 5 model-dependent cases × 3 retained runs;
- >=12/15 task success;
- each case >=2/3;
- zero hard-invariant failures.

A failed trial is retained, not deleted and silently replaced.

## G9 — Observability evidence

Required runtime stages emit OTel spans and audit events with correlation. Token usage is recorded when reported. Cost is never fabricated.

## G10 — Demo integrity

- static Vite app builds;
- curated five replays validate against schema;
- every replay references an accepted run/eval receipt;
- visible mode label says recorded replay;
- Playwright critical flow PASS;
- deployed Vercel URL loads the same final assets after publication.

## G11 — Cross-platform support evidence

Target support: Windows 11, macOS, Linux.

Minimum release evidence:

- Python/frontend unit+static jobs run in GitHub Actions matrix on Windows, macOS and Ubuntu;
- full Postgres + MCP + agent integration runs on Ubuntu CI;
- real Ollama end-to-end acceptance is executed on at least one local supported OS;
- setup paths are platform-neutral and do not require GNU Make.

If real Ollama execution is not performed on all three operating systems, compatibility for unexecuted OS/model combinations is labeled `EXPECTED`, not `TESTED`.

The project may still be released if the matrix and one real Ollama platform are green, but README must preserve the TESTED/EXPECTED distinction.

## G12 — Checker sensitivity

Meta-tests prove the evaluator fails the intentionally broken approval, duplicate-effect, bad-citation and secret-replay controls, while a valid alternate trajectory remains accepted.

## G13 — Final candidate binding

After all behavior-affecting changes:

- rerun affected gates;
- regenerate accepted replay artifacts;
- bind acceptance receipt to exact git SHA, lockfile hashes and scenario-set digest;
- CI on exact pushed SHA is terminal green;
- Architect independently reviews actual repo/diff/CI rather than Codex's prose summary.

## G14 — Manual release verification

Before merge/release, the Architect gives the user a short focused checklist. At minimum the user manually verifies:

1. public replay clearly looks recorded, not fake-live;
2. approval flow communicates exactly what will execute;
3. one injection replay makes the trust boundary understandable;
4. restart/duplicate-effect replay visibly proves one resulting effect;
5. README quickstart is understandable and commands match the repository;
6. portfolio landing page communicates the engineering thesis in under a few minutes.

Release/merge requires explicit user approval after this check.
