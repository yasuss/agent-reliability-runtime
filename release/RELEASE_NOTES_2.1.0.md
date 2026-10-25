# ARR 2.1.0

## Summary

ARR 2.1.0 extends `core.ports` for multi-tenant and action-layer architectures
without changing the existing OpsDesk runtime. It is an additive,
interface-only public-contract release.

## Highlights

- Planned `ScopeAuthorizer` and `BudgetBroker` ports.
- Frozen `TaskScope` with tenant, project, region, separate principals,
  capability grants and authorization epoch.
- `PrincipalRef`, `AuthorizationDecision` and `BudgetLease` value contracts.
- `RiskTier` and `EgressClass` metadata plus optional
  `CapabilityDefinition` risk/egress/reversibility fields.
- Provenance links to [reliable-ai-agents-for-enterprise-workflows](https://github.com/yasuss/reliable-ai-agents-for-enterprise-workflows)
  and [agent-safe-mcp-for-product-analytics](https://github.com/yasuss/agent-safe-mcp-for-product-analytics).

## Compatibility

This is an additive public-interface release. Existing `CapabilityDefinition`
construction remains valid; defaulted metadata may appear in normal serialized
output. CLI, MCP and Quickstart entry points are unchanged. The new planned
ports have no implementation or runtime wiring.

## Verification

The final full verification run recorded **369 unit** and **96 integration**
tests, plus strict mypy, documentation, historical v1, release, provenance,
web and secret-scan gates. Release acceptance additionally runs four exact-SHA
behavior probes on the final pre-merge head.

## Not included

- `ScopeAuthorizer` implementation.
- `BudgetBroker` implementation.
- Multi-tenant OpsDesk runtime or a generic control plane.
- Dependency extras.
- A new `PROOF_INDEX` behavior claim for planned ports.

## Deployment

There is no `web/**` change and Static Evidence Demo content is unchanged. No
production Vercel redeploy is required.
