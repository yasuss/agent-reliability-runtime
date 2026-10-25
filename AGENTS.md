# Agent Reliability Runtime — Repository Instructions

Read `docs/project/README.md` first. Current v2 architecture and extension contracts live under `docs/project/` and
`docs/extension-points.md`; `docs/project/spec/v1.0/` is immutable historical
behavior/security acceptance evidence, not current file topology authority.

## Non-negotiable boundaries

- Preserve one production LangGraph demo graph; do not add multi-agent orchestration.
- Core imports only stdlib, Pydantic and core; adapters never import demo.
- Planned ports are interfaces only; never add behavior or ports without task authorization.
- All MCP tool execution must pass trusted policy; all side effects require exact approval.
- Never use RAG, memory, MCP output or model text as authorization.
- Preserve idempotent effect receipts and real restart durability.
- Public web is recorded replay only; no live backend/chat scope.
- Keep paid/cloud services optional.
- Do not weaken acceptance criteria to make a failing implementation pass.

## Work pattern

Before editing, read the relevant product/architecture/verification docs and current code/tests. Reproduce failures, implement the smallest contract-preserving change, verify locally, then report exact evidence. Remote CI is independent evidence, not the first test runner.

For a material architecture/security/proof change, stop and return to Architect if the existing task contract does not already authorize it.
