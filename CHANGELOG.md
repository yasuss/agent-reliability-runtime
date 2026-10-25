# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-10-25

ARR 2.0.0 turns the runtime into a reusable reliability core with replaceable
adapters and a concrete OpsDesk demo. Runtime behavior proven in 1.0.0 is
preserved while the public architecture and internal import boundaries change.

### Why

In 1.0.0, trusted policy, exact approval, effect receipts and postcondition
verification shared modules with SQLAlchemy access, LangGraph orchestration and
OpsDesk-specific rules. Version 2.0.0 separates what must be true in `core/`
from storage/orchestration in `adapters/` and one concrete use case in `demo/`.

### Added

- A framework-neutral `core/` package depending only on the Python standard
  library, Pydantic and core modules; the boundary is enforced by a test.
- Seven implemented structural ports and four planned interface-only ports.
- `VerificationStatus` (`PASS` / `FAIL` / `PARTIAL`) independent of `RunStatus`.
- [Extension points](docs/extension-points.md) and [ADR-0002](docs/project/decisions/ADR-0002-core-adapters-demo.md).

### Changed

- Responsibility split across core policy/approval/effect semantics, the
  PostgreSQL execution gateway and OpsDesk-specific policy and postconditions.
- Generic rule-based verification is registered by the OpsDesk demo.
- LangGraph orchestration and checkpoints moved under `adapters/langgraph/`.
- The immutable v1.0 specification is verified against the exact `v1.0.0` tree.
- **Breaking:** internal 1.x Python import paths moved. CLI, MCP server launch,
  Quickstart scripts and the local API entry point remain supported.
- Vite development/build tooling is patched from 8.3.2 to 8.3.3.

### Removed

- The old internal 1.x import topology; see the [migration table](docs/extension-points.md#migrating-from-1x).

### Security

- Vite 8.3.2 -> 8.3.3 addresses the reviewed upstream advisories.
- Database schema and migrations, Python runtime dependencies, seed/knowledge
  fixtures, Compose, replay bytes and acceptance thresholds remain unchanged.

## [1.0.0] - 2026-10-06

Initial published release summary for the local-first Agent Reliability Runtime.

- durable LangGraph execution backed by PostgreSQL checkpoints;
- trusted policy, exact approvals and idempotent effect receipts;
- scoped governed memory, correlated OTel/audit evidence and deterministic evaluation;
- Static Evidence Demo with five integrity-checked recorded replay/receipt pairs;
- Apache-2.0 licensing and documented security/contribution guidance.

Version 1.0.0 was published as the immutable v1.0.0 Git tag and GitHub release.

[2.0.0]: https://github.com/yasuss/agent-reliability-runtime/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/yasuss/agent-reliability-runtime/releases/tag/v1.0.0
