# ADR-0002: Separate core, adapters and demo

- Status: Accepted
- Date: 2026-10-25

## Context

Version 1.0.0 proved the reliability semantics, but policy/effect rules,
SQLAlchemy persistence, LangGraph orchestration and OpsDesk-specific behavior
shared module boundaries. Reusing the reliability semantics in another domain or
orchestrator would also pull in demo/framework concerns.

## Decision

- `core/` owns framework-neutral contracts plus policy, approval, effect and
  verification semantics; it may import only the standard library, Pydantic and
  other core modules.
- Orchestration remains in `adapters/langgraph/`; LangGraph checkpoint types do
  not enter core. ARR does not build its own generic control plane in 2.0.0.
- Extension ports use `typing.Protocol` structural typing.
- Long-running workflow needs are represented only by planned interface-only
  ports until a real implementation requires them.
- `PARTIAL` belongs to `VerificationStatus`, not `RunStatus`.
- Internal 1.x Python import paths break in 2.0.0; supported CLI, MCP server and
  Quickstart entry points remain.
- Behavior preservation is a release acceptance criterion.

## Alternatives considered

- Move files without splitting responsibilities — rejected because coupling would
  remain under new directories.
- Build an orchestrator-neutral control plane in core — deferred because it is a
  much larger abstraction without a second orchestrator implementation.
- Split package dependencies/extras in 2.0.0 — deferred because packaging is
  independent from the architectural boundary.

## Consequences

ARR exposes a reusable structural core without claiming that every reliability
invariant is captured by one port. `EffectStore` and `CheckpointStore` are
intentionally narrow; their current limits are documented in Extension points.
The historical v1.0 specification remains immutable and is verified against the
`v1.0.0` tree.
