# 12 — Research and Design Decisions

Research was used to decide architecture, not to maximize source count. English, German, native Chinese and native Japanese lanes were checked because they contain relevant current agent-engineering practice and target-market signals.

## D01 — Build a reliability runtime, not another framework

**Decision:** use LangGraph for orchestration and spend project complexity on reliability boundaries.

**Reason:** current high-value agent platform roles emphasize context, orchestration, policy, observability, evaluation and reliability. Native Chinese and Japanese material independently emphasizes trajectory evaluation, recovery, constraints and operational harnesses.

## D02 — Single agent, not multi-agent

**Decision:** one explicit graph.

**Reason:** no locked user outcome requires specialist-agent delegation. Multi-agent would add coordination and evaluation surface without increasing the main hiring signal.

## D03 — Python backend

**Decision:** Python 3.12 + FastAPI/Pydantic.

**Reason:** strengthens a material portfolio gap while matching current AI platform roles. It also aligns with LangGraph and MCP Python ecosystems.

## D04 — LangGraph durable execution + Postgres checkpointer

**Decision:** use its durable primitives rather than inventing a workflow engine.

**Evidence consequence:** real restart must be proven because durable semantics are a core claim.

## D05 — PostgreSQL + pgvector + FTS

**Decision:** one data platform for relational state and hybrid retrieval.

**Reason:** pgvector explicitly supports combination with PostgreSQL full-text search. Multiple vector stores would add no v1 signal.

## D06 — Current MCP official SDK, local stdio reference server

**Decision:** official SDK; canonical demo uses stdio.

**Reason:** current MCP 2026-07-28 evolves HTTP transport and authorization substantially, but the portfolio goal is tool contract/governance, not remote MCP hosting. Stdio is the smallest faithful integration. Tool annotations are treated only as hints.

## D07 — Deterministic policy outside the model

**Decision:** model cannot self-authorize effects.

**Reason:** current MCP and OWASP material distinguish descriptive tool metadata/model reasoning from trusted enforcement. Memory and retrieved content are attack surfaces.

## D08 — Exact approval + idempotency receipts

**Decision:** approval binds to action digest; effect execution uses idempotency record.

**Reason:** approval without argument binding becomes stale authority, while restart/retry without effect reconciliation can duplicate actions.

## D09 — OTel mandatory, Langfuse optional

**Decision:** OpenTelemetry is the neutral foundation.

**Reason:** current OTel GenAI conventions cover model/tool visibility; the project should not require SaaS. Optional UI sinks can consume the same telemetry.

## D10 — No public arbitrary chat

**Decision:** Vercel is a static evidence browser using real recorded accepted runs.

**Reason:** live public chat would add cost, hosting, abuse/security and nondeterminism while distracting from the portfolio thesis. Vite supports straightforward static deployment to Vercel.

## D11 — Qwen3:4b local default

**Decision:** default Ollama chat model `qwen3:4b`; embeddings `qwen3-embedding:0.6b`.

**Reason:** lightweight enough to be broadly practical, available through Ollama, and explicitly supports tool-oriented agent use. Acceptance measures the actual model rather than assuming capability.

## D12 — Generic OpenAI-compatible chat adapter

**Decision:** same application/provider boundary can point to Ollama, vLLM or an optional compatible cloud endpoint.

**Reason:** both Ollama and vLLM expose OpenAI-compatible APIs. This demonstrates model portability without vendor zoo.

## D13 — Hardware-dependent vLLM validation

**Decision:** vLLM live execution is optional hardware validation; contract compatibility is mandatory.

**Reason:** local vLLM normally implies a suitable acceleration environment. Pretending a non-executed GPU lane passed would weaken the project's evidence quality.

## D14 — Cross-platform by portable primitives

**Decision:** avoid Make/shell-only orchestration; use Python scripts, uv, npm and Docker Compose.

**Reason:** target support is Windows/macOS/Linux. Full feature evidence distinguishes TESTED from EXPECTED.
