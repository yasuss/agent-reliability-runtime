# 10 — Engineering Backlog

This is a **dependency/acceptance backlog**, not a calendar. Completion is determined by artifacts and gates, never by elapsed time.

## B00 — Repository foundation

**Result:** greenfield repo can bootstrap deterministically.

Deliver:
- toolchain files, lockfiles, Compose Postgres/pgvector, migration foundation, concise AGENTS, docs skeleton, CI skeleton.

Acceptance:
- clean checkout can install backend/frontend dependencies;
- DB starts and migrations apply from empty state;
- backend/frontend static checks can run locally before any remote CI.

## B10 — Domain contracts and persistence

**Result:** run, approval, effect, audit, memory, knowledge and demo-state contracts exist with migrations.

Acceptance:
- schema tests cover valid/invalid variants;
- effect receipt uniqueness is proven at the DB boundary;
- clean reset restores deterministic fictional state.

## B20 — Provider boundary

**Result:** graph can use a provider-independent chat interface and local embeddings.

Acceptance:
- Ollama qwen3:4b real call works;
- Ollama qwen3-embedding:0.6b real embedding works;
- generic OpenAI-compatible provider contract tests pass against stub and configuration compatible with vLLM;
- provider failure has explicit error semantics.

## B30 — Retrieval

**Result:** deterministic ingestion + hybrid retrieval + evidence IDs.

Acceptance:
- changed document digest stales/replaces prior chunks;
- retrieval metrics meet locked thresholds;
- citation validator rejects non-retrieved IDs.

## B40 — OpsDesk MCP server + client

**Result:** official MCP SDK connects the graph runtime to the exact five tools.

Acceptance:
- list/call schemas work;
- invalid arguments fail clearly;
- server operates only on fictional state;
- no business authorization is delegated to untrusted annotations.

## B50 — Trusted policy, approvals and effect receipts

**Result:** no side effect can occur without an exact approval, and replay cannot duplicate an effect.

Acceptance:
- direct bypass attempt fails;
- approval argument drift fails;
- rejection prevents mutation;
- same idempotency key + same digest replays receipt without second mutation;
- same key + different digest fails.

## B60 — Durable LangGraph runtime

**Result:** bounded agent graph runs end to end and persists state.

Acceptance:
- read-only happy path completes;
- approval interrupt/resume works;
- step budget terminates loops;
- real fresh-process restart continues same run from retained checkpoint.

## B70 — Governed memory

**Result:** scoped long-term memory exists independently from thread state.

Acceptance:
- create/read/delete behavior works;
- provenance/trust is preserved;
- model observation defaults untrusted;
- poisoning scenario cannot affect authorization.

## B80 — Observability and audit

**Result:** every material runtime boundary is inspectable.

Acceptance:
- required spans are emitted and correlated;
- audit event order is deterministic per run;
- default telemetry excludes prompt/tool secret content;
- replay exporter produces schema-valid sanitized artifacts.

## B90 — Eval harness and oracle calibration

**Result:** repository can prove hard invariants and measure behavior.

Acceptance:
- L0-L4 layers implemented as specified;
- consequential checkers have good/bad/valid-alternative calibration;
- meta-tests prove broken approval, duplicate effect, bad citation and secret replay are caught.

## B100 — Full mandatory scenario suite

**Result:** S01–S12 exist as executable scenarios with retained evidence.

Acceptance:
- deterministic scenarios pass;
- real restart and ambiguous-effect rehearsals pass;
- model-dependent reliability run meets thresholds;
- hard invariant failures remain zero.

## B110 — Static evidence demo

**Result:** Static Evidence Demo viewer renders accepted replay artifacts.

Acceptance:
- five mandatory curated replays are inspectable;
- Playwright critical-path test passes;
- replay mode is clearly labeled;
- no secret or backend dependency is present;
- production Vite build succeeds.

## B120 — Project Documentation & Operational Guidance

**Result:** repo explains tradeoffs and evidence without overclaiming.

Acceptance:
- README quickstart works from clean checkout;
- architecture, threat model, eval method, limitations and support matrix agree with implementation;
- no claimed feature lacks an observable proof path.

## B130 — Release-candidate acceptance

**Result:** exact final candidate is proven and ready for user manual verification.

Acceptance:
- all automated gates pass on exact SHA;
- accepted replays originate from exact final candidate or are regenerated after any behavior-affecting change;
- independent Architect review of actual diff/repo/CI returns PASS or only explicitly accepted low-risk residuals;
- user executes focused manual checklist and explicitly approves release/merge.
