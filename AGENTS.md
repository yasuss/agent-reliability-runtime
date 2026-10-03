# Agent Reliability Runtime — Repository Instructions

Read `docs/project/README.md` first. The durable product contract lives under `docs/project/`; this file is intentionally short.

## Non-negotiable boundaries

- Preserve the v1 scope: one LangGraph agent; do not add multi-agent orchestration.
- All MCP tool execution must pass trusted policy; all side effects require exact approval.
- Never use RAG, memory, MCP output or model text as authorization.
- Preserve idempotent effect receipts and real restart durability.
- Public web is recorded replay only; no live backend/chat scope.
- Keep paid/cloud services optional.
- Do not weaken acceptance criteria to make a failing implementation pass.

## Work pattern

Before editing, read the relevant product/architecture/verification docs and current code/tests. Reproduce failures, implement the smallest contract-preserving change, verify locally, then report exact evidence. Remote CI is independent evidence, not the first test runner.

For a material architecture/security/proof change, stop and return to Architect if the existing task contract does not already authorize it.
