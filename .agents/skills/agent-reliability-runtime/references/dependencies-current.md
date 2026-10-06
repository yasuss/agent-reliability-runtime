# Current ecosystem constraints revalidated 2026-10-03
These are implementation constraints, not permission to reopen locked product choices.

- LangGraph: 1.2.12 current observed release; `langgraph-checkpoint-postgres` 3.1.2 current observed release; both support Python >=3.10.
- MCP Python SDK: v2 is current stable; v2.2.0 observed latest release; v1 is maintenance-only. Project dependency must stay on the v2 line unless Architect revalidates a contradiction.
- FastAPI: 0.142.2 observed current release; Python >=3.10.
- Pydantic: 2.13.4 observed current release.
- OpenTelemetry Python SDK: 1.45.0 observed current release; traces/metrics stable, logs still development. GenAI content fields can contain sensitive data; content capture must not be enabled by default just for observability.
- Python: project remains 3.12 by locked contract. CPython 3.12 is security-only and 3.12.15 is source-only; use `uv` managed Python (`.python-version` `3.12`, project `>=3.12,<3.13`) for cross-platform bootstrap instead of assuming python.org binary installers.
- Vite current docs require Node 20.19+ or 22.12+; locked Node 24 LTS is compatible. Use Node 24 and npm lockfile.
- pgvector: official 0.8.6 images support PostgreSQL 18/17/...; B00 should first probe `pgvector/pgvector:0.8.6-pg18`. If the image/runtime itself fails for a real supported-platform reason, stop or use only the explicitly task-authorized bounded fallback.
- Ollama currently exposes `qwen3:4b` with tools and `qwen3-embedding:0.6b`; preserve these locked defaults.
- vLLM exposes OpenAI-compatible chat completions and embeddings; hardware live run remains optional per v1 contract.

Do not silently add/replace a dependency class. Exact lockfile resolution is Codex implementation work and must be preceded by current metadata check + install/import/bootstrap probe in its live environment.
