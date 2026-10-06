# Active compiled module rules

# Module: Greenfield

Activate when repository/product is genuinely new.

Rules:
- establish repo/toolchain/verification before large feature implementation;
- build vertical slices, not a giant scaffold with speculative layers;
- keep first architecture reversible;
- define durable sources of truth early;
- avoid adding libraries/services until an accepted use case needs them;
- keep every phase runnable/clean where practical;
- do not confuse "possible future scale" with current requirement.

Evidence:
- initial project contract;
- support/deployment target;
- first vertical user journey;
- baseline verification.

# Module: Frontend Web

Activate for browser UI.

Focus:
- user-visible behavior and accessibility;
- server/client rendering boundaries;
- state ownership and URL/navigation semantics;
- resilient loading/error/empty states;
- responsive layout and input modalities;
- browser support contract;
- performance budgets tied to user journeys;
- test real browser behavior only where browser is part of contract.

Do not:
- couple domain state to incidental component lifecycle;
- use arbitrary sleeps;
- test implementation details in E2E when public behavior suffices.

# Module: Backend / API

Activate for services/APIs.

Focus:
- boundary validation;
- authentication/authorization;
- idempotency;
- transaction boundaries;
- error model;
- rate limits/backpressure;
- observability;
- versioning/compatibility;
- failure/retry semantics;
- contract tests.

Do not trust client input or inferred third-party response shapes.

Prefer explicit schemas/contracts at boundaries.

# Module: Database / Persistence

Activate when durable data/storage changes.

Focus:
- ownership/source of truth;
- schema constraints;
- transactions/atomicity;
- indexes/query plans when material;
- concurrency;
- migrations/backfills;
- backup/restore;
- retention/deletion;
- data validation.

Migration requires old/new/partial/interrupted/retry cases.

Destructive production changes require explicit approval.

# Module: CLI

Activate for command-line tools.

Focus:
- exit codes;
- stdout vs stderr;
- deterministic/non-interactive behavior;
- config precedence;
- filesystem safety;
- idempotency;
- signals/interrupts;
- cross-platform paths;
- machine-readable output where promised.

Never hide failure behind exit 0.

Support dry-run for destructive/bulk operations when useful.

# Module: Authentication / Security

Activate when auth, authorization, sensitive actions or trust boundaries are involved.

Focus:
- actors/assets/trust boundaries;
- authentication vs authorization;
- session/token lifecycle;
- least privilege;
- CSRF/XSS/injection/SSRF/file abuse as relevant;
- rate/abuse limits;
- secret handling;
- auditability.

Security findings require concrete attack path and impact.

Add negative/denial tests, not only happy path.

# Module: AI / LLM / Agents

Activate for model calls, tools, RAG or autonomous agents.

Focus:
- measurable product job;
- eval set before/with implementation;
- model/tool latency and cost;
- prompt/tool injection;
- untrusted retrieval/tool outputs;
- data privacy;
- tool permissions;
- fallback/degradation;
- deterministic boundaries around nondeterministic model behavior;
- model/provider abstraction only when justified.

Do not claim quality from anecdotal examples.

For tool-using agents, separate reasoning/judgment from high-risk action approval.

# Module: Infrastructure / DevOps

Activate for cloud, CI/CD, containers, IaC, networking.

Focus:
- immutable/reviewable configuration;
- least privilege;
- secret management;
- environment parity;
- rollback;
- health/observability;
- cost;
- state/locking for IaC;
- blast radius;
- provider limits.

Production apply/delete is high-risk and requires task/user authorization.

Prefer plan/dry-run evidence before apply.

# Module: Offline / Local-first

Activate when local operation/sync matters.

Focus:
- local source of truth;
- synchronization;
- identity/versioning;
- conflicts;
- offline queue;
- retries;
- data durability;
- corruption/recovery;
- clock assumptions;
- multi-device/multi-tab semantics.

Choose explicit conflict policy.

Do not hide distributed-state complexity behind UI retries.

# Module: Dependency / Supply Chain

Activate for meaningful new dependencies, build tools, plugins, skills or CI actions.

Focus:
- provenance;
- license;
- lockfile integrity;
- version pinning policy;
- transitive footprint;
- maintainer/maintenance;
- advisories;
- install/build scripts;
- CI/action pinning;
- network/secret access.

Do not execute untrusted project setup scripts merely to inspect them.

# Module: Realtime / Concurrency

Activate for multiple actors/tabs/workers/processes or realtime collaboration.

Focus:
- authority/ownership;
- ordering;
- idempotency;
- locking/CAS/version vectors as appropriate;
- stale work cancellation;
- retries;
- partial failure;
- deterministic state transitions.

Test exhaustive deterministic decisions below E2E; retain higher-level proof only for real runtime coordination semantics.

Avoid timing sleeps as correctness mechanism.
