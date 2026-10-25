# ARR v2 extension points

Import public structural protocols from `agent_reliability_runtime.core.ports`.
Adapters satisfy `typing.Protocol` through static typing; runtime inheritance or
registration is unnecessary. Values referenced by these ports are core-clean.

| Port | Status | Current implementation / purpose |
| --- | --- | --- |
| ModelProvider | Implemented | `adapters.providers.http.OpenAICompatibleChatProvider.complete` |
| Retriever | Implemented | `adapters.postgres.retrieval.PostgresHybridRetriever.retrieve` |
| PolicyEngine | Implemented | `demo.opsdesk.policy.OpsDeskPolicyEngine`; schema/ownership, risk, action identity |
| Approver | Implemented | `adapters.postgres.execution.Approvals`; exact persisted lifecycle |
| EffectStore | Implemented | `adapters.postgres.execution.PostgresEffectStore`; durable receipt lookup |
| Verifier | Implemented | `core.verification.RuleVerifier`; demo registers its restart/status rule |
| CheckpointStore | Implemented | `adapters.langgraph.checkpoints.LangGraphPostgresCheckpointStore`; setup/existence |
| Reconciler | Planned, interface only | Future ambiguous-effect resolution; no implementation |
| TimerStore | Planned, interface only | Future durable wait metadata; no scanner/queue |
| SourceRevisionReader | Planned, interface only | Future source-version revalidation |
| CapabilityRegistry | Planned, interface only | Future typed capability lookup; `CapabilityDefinition` carries optional `risk_tier`, `egress_class`, `reversible` (2.1) |
| ScopeAuthorizer | Planned, interface only (2.1) | Future execution-boundary check of a `TaskScope` (tenant, project, region, principals, grants, auth epoch) |
| BudgetBroker | Planned, interface only (2.1) | Future `BudgetLease` reservation before an expensive step and settlement afterwards |

## Port scope and current limits

Ports describe the boundary that is stable today, not every guarantee ARR provides.
Two ports are intentionally narrow:

- **EffectStore** exposes durable receipt lookup only (`receipt_for`). Duplicate
  and effect safety in the shipped OpsDesk path is a composed invariant across the
  trusted PostgreSQL execution gateway and the OpsDesk MCP server's atomic domain
  mutation plus durable-receipt transaction. A third-party effect backend does
  not inherit exactly-once or idempotency safety by implementing `receipt_for`; it
  must reproduce action identity, semantic idempotency, atomic effect/receipt and
  reconciliation guarantees. A future release may widen the port only when
  another backend proves that abstraction useful.
- **CheckpointStore** exposes setup and existence only. Checkpoint payload and
  resume semantics remain orchestrator-owned so LangGraph types never enter core.

## Why these planned ports

The four planned ports serve long-running, multi-system workflows: `Reconciler`
resolves an ambiguous write after a timeout, `TimerStore` parks a durable wait
without a live worker, `SourceRevisionReader` revalidates source versions before
an approved effect executes, and `CapabilityRegistry` provides typed capability
lookup. They are interface-only: no implementation, wiring, behavior branch or
`PROOF_INDEX` entry.

Version 2.1 adds the contracts that multi-tenant agent action layers need, for
example an MCP surface exposing a product's capabilities to external agents:
`ScopeAuthorizer` defines a future execution-boundary check of an immutable
`TaskScope` (tenant, project, region, separately recorded human / agent-client /
task principals, capability grants, authorization epoch); `BudgetBroker` defines
future `BudgetLease` reservation and settlement; `RiskTier` (read, internal
reversible, external or production, forbidden) and `EgressClass` extend
`CapabilityDefinition` as optional metadata. These contracts are interface-only:
ARR 2.1 does not implement authorization, multi-tenancy or budget enforcement and
changes no existing behavior.

Architectures these ports were derived from:
[reliable-ai-agents-for-enterprise-workflows](https://github.com/yasuss/reliable-ai-agents-for-enterprise-workflows)
(Reconciler, TimerStore, SourceRevisionReader, CapabilityRegistry) and
[agent-safe-mcp-for-product-analytics](https://github.com/yasuss/agent-safe-mcp-for-product-analytics)
(ScopeAuthorizer, BudgetBroker, RiskTier).

## Migrating from 1.x

| 1.x module | 2.0 location |
| --- | --- |
| `policy` | split: `core.policy`, `core.approval`, `core.effects`, `adapters.postgres.execution`, `demo.opsdesk.policy` |
| `runtime.graph`, `runtime.checkpoints`, `runtime.service` | `adapters.langgraph.*` |
| `runtime.postconditions` | `demo.opsdesk.postconditions` (generic part: `core.verification`) |
| `contracts.*` | `core.contracts.*` |
| `providers.contracts` / `providers.http` | `core.contracts.model` / `adapters.providers.http` |
| `retrieval.contracts`, `retrieval.citations`, `retrieval.text` | `core.contracts.retrieval`, `core.retrieval`, `core.source_text` |
| `retrieval.service` | `adapters.postgres.retrieval` |
| `database`, `memory`, `persistence.*` | `adapters.postgres.*` |
| `observability` | `adapters.postgres.audit` + `adapters.otel.telemetry` |
| `mcp.client`, `mcp.contracts` | `demo.opsdesk.mcp`, `demo.opsdesk.contracts` |
| `api`, `replay`, `evals.*`, `demo_state.*` | `demo.*` |

Dependency extras are not currently part of the public extension contract; a
core-only install is not claimed.

`core/` imports only Python stdlib, Pydantic and core modules. Adapters may use
external frameworks and core but must not import demo. Demo owns composition and
OpsDesk-specific policy, schemas and verification. LangGraph remains an adapter;
no generic control plane is implemented.

The existing CLI (`python -m agent_reliability_runtime.cli`), MCP server launch
(`python -m mcp_server.opsdesk`) and Quickstart scripts remain supported. The local
API is `agent_reliability_runtime.demo.api:app`.
