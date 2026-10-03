# 01 — Scope and Non-goals

## Locked v1 scope

The implementation must contain exactly one production agent topology: **one stateful tool-using agent graph**. No multi-agent swarm is required.

The project must include:

- Python 3.12 backend with FastAPI and Pydantic.
- LangGraph for explicit durable orchestration.
- PostgreSQL + pgvector for application state and retrieval data.
- Official MCP Python SDK and one self-contained fictional MCP server.
- Ollama local chat + local embeddings.
- OpenAI-compatible chat-provider boundary supporting vLLM and optional cloud endpoints.
- OpenTelemetry as the mandatory observability API.
- Optional observability backend integration, not required for correctness.
- React + TypeScript + Vite static recruiter demo.
- Deterministic evaluation and security suites.
- GitHub Actions CI.

## Deliberate non-goals

The following are outside v1 and must not be added unless a locked requirement becomes unrealizable without them:

- Multi-agent teams, supervisors, swarms or A2A.
- Kubernetes, Terraform or cloud infrastructure orchestration.
- Production multi-tenancy, billing, SSO or enterprise auth.
- A general-purpose agent framework intended to compete with LangGraph.
- Multiple vector databases.
- Multiple agent frameworks such as CrewAI, AutoGen and PydanticAI in the same repo.
- Live cloud inference in the Vercel demo.
- A public free-form chat product.
- Voice, image or multimodal input.
- A knowledge graph.
- A reranker unless retrieval acceptance cannot be met with the locked hybrid design.
- Real Slack/Jira/GitHub/service-desk credentials or actions.
- MCP Tasks extension in v1; LangGraph owns workflow durability.
- ACV integration in v1. `ai-change-verification` may only be linked as a related project.
- Langfuse as a hard dependency. If added, it is an optional visualization/export sink.
- Automatic model fallback across vendors unless later explicitly designed and evaluated.

## Why there is no public arbitrary chat box

The portfolio objective is to prove system engineering, not general conversational breadth. A free-form public chat box would add backend hosting, abuse handling, cost, live-model variability and UX work while weakening the evidence-focused demo. The public UI therefore exposes curated accepted run replays.

The local runtime still accepts a single free-text task through its API/CLI so the agent is a real system rather than a fixture player. It is not a persistent chat product.

## Scope-change rule

A proposal is not enough to expand v1. A scope change requires one of:

1. a demonstrated contradiction in the locked contract;
2. a mandatory acceptance failure that cannot be repaired inside the current architecture;
3. a material current platform incompatibility verified from primary evidence;
4. explicit user decision to revise the contract.

Any scope change increments the contract version and revalidates affected gates.
