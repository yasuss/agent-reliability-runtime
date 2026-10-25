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
| CapabilityRegistry | Planned, interface only | Future typed capability lookup |

`core/` imports only Python stdlib, Pydantic and core modules. Adapters may use
external frameworks and core but must not import demo. Demo owns composition and
OpsDesk-specific policy, schemas and verification. LangGraph remains an adapter;
no generic control plane is implemented. Embedding providers remain adapter-private.

`VerificationStatus` contains PASS, FAIL and PARTIAL, independently of `RunStatus`.
Only PASS resolves a verification obligation; the current OpsDesk rule emits PASS
or FAIL and requires a real matching later model-issued read. Planned ports have
no production wiring, behavior branches or acceptance claims.

The existing CLI (`python -m agent_reliability_runtime.cli`), MCP server launch
(`python -m mcp_server.opsdesk`) and Quickstart scripts remain supported. Other
internal imports moved in v2. The local API is `agent_reliability_runtime.demo.api:app`.

Dependency groups/extras are deliberately unchanged and deferred to a later
release: a core-only installation is not claimed by this release. Python runtime
dependencies remain unchanged; Vite development/build tooling is patched from
8.3.2 to 8.3.3 for reviewed upstream security advisories. See
[Architecture](project/ARCHITECTURE.md) and
[Verification](project/VERIFICATION.md) for boundaries and preserved evidence.
