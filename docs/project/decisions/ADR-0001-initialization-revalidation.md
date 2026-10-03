# ADR-0001 — Initialization revalidation (2026-10-03)

Status: accepted implementation guidance; does not reopen locked v1 product choices.

- Target repository is a genuinely empty private GitHub repo with default branch metadata `main`.
- One empty `main` seed commit is allowed solely to create a branchable baseline; B00 implementation then occurs on `codex/b00-repository-foundation` through PR review.
- Python remains 3.12; cross-platform bootstrap uses `uv` managed Python because 3.12 is now security-only/source-only on python.org.
- Current LangGraph 1.2.x + PostgreSQL checkpointer remain compatible with the durability design.
- Current official MCP Python SDK is v2; implementation must use current v2 APIs and must not treat annotations as authority.
- Node 24 LTS remains compatible with current Vite requirements.
- pgvector 0.8.6 provides PostgreSQL 18 images. B00 must execute a live Compose/extension/migration probe before adopting its exact image in the repository lock/config.
- OTel remains mandatory. Sensitive GenAI content capture is not enabled by default; project-owned low-cardinality correlation/security attributes remain the reliable invariant surface.
- Repository license and any future public-repository visibility are user-owned release decisions and are intentionally not fabricated by B00.
