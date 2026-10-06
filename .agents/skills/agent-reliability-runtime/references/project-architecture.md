# Project architecture / runtime invariants
Canonical stack and boundaries are locked by `docs/project/spec/v1.0/`:
- Python 3.12, FastAPI/Pydantic, LangGraph durable orchestration;
- PostgreSQL + pgvector, PostgreSQL-backed LangGraph checkpointer;
- official MCP Python SDK and exactly five fictional OpsDesk tools;
- Ollama `qwen3:4b` and `qwen3-embedding:0.6b` default local models;
- generic OpenAI-compatible provider boundary; vLLM live hardware run optional;
- OpenTelemetry mandatory;
- React + TypeScript + Vite static replay demo;
- GitHub Actions, `uv`, npm, Docker Compose; no Make/shell-only orchestration.

## LangGraph implementation consequence
Current LangGraph durable execution checkpoints at node boundaries and interruption/resume may re-run the interrupted node from its beginning. Therefore approval and effect design must never rely on "code before interrupt runs once". Persist/canonicalize the candidate action, interrupt before non-idempotent effects, and validate the resumed approval against the exact action digest before entering an effect node protected by the receipt boundary.

## MCP implementation consequence
The current stable official MCP Python SDK is v2. Use current v2 server/client APIs (`MCPServer` line); do not transplant stale v1 `FastMCP` examples. Tool annotations are metadata/hints, not authorization.
