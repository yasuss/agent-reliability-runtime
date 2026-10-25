# ARR 2.0.0

## Summary

2.0.0 separates ARR's reliability semantics into a framework-neutral `core/`,
replaceable `adapters/` and the OpsDesk `demo/`. Behavior proven in 1.0.0 is
preserved; the change is in architecture and public boundaries.

## Highlights

- Strict core: standard library and Pydantic only, enforced by a test.
- Seven implemented structural ports and four planned interface-only ports.
- Generic rule-based postcondition verification with `PASS` / `FAIL` / `PARTIAL`.
- LangGraph is an adapter: the core does not import orchestrator types.
- [Migration table](https://github.com/yasuss/agent-reliability-runtime/blob/v2.0.0/docs/extension-points.md#migrating-from-1x).

## Breaking changes

Internal import paths moved — see the migration table above. CLI, MCP server launch
and Quickstart scripts are unchanged.

## Verification

- `scripts/verify.py --scope all`: Ruff, strict mypy, **359 unit** and
  **96 integration** tests, documentation truth gate, historical v1 spec,
  release/provenance, web checks, Compose/migrations/checkpoints and secret scan.
- CI: static/unit on Ubuntu, Windows and macOS; PostgreSQL integration; web e2e;
  release audit.
- Four exact-SHA probes passed on the final head.
- The v1.0 specification remains byte-identical and is verified against `v1.0.0`.

## Not included

Dependency extras (core-only installation) and implementations of planned ports.

## Deployment

Static Evidence Demo content and output are unchanged. Vite 8.3.2 -> 8.3.3 affects
development/build tooling only, so no production Vercel redeploy is required for
v2.
