# 00 — Product Contract

## Product identity

**Repository working name:** `agent-reliability-runtime`  
**Display name:** **Agent Reliability Runtime**  
**Reference application:** **OpsDesk**, a fictional enterprise incident-operations agent.

## One-sentence product contract

Build a local-first, provider-agnostic reference implementation showing how a tool-using AI agent can retrieve evidence, call MCP tools, pause for exact human approval before side effects, survive process failure, prevent duplicate effects, use governed long-term memory, emit inspectable OpenTelemetry traces, and prove its behavior through repeatable evaluations.

## Primary audience

Technical hiring managers and senior engineers evaluating Staff / Senior Staff / Principal / Founding AI engineering capability.

## What the finished repository must demonstrate

The repository must provide observable evidence of these competencies, rather than merely listing technologies:

1. LLM provider abstraction with a real local open-weight model.
2. Explicit agent orchestration and bounded execution.
3. RAG with local embeddings, hybrid retrieval and citations.
4. MCP tool integration through the official Python SDK.
5. Deterministic policy enforcement outside the model.
6. Human-in-the-loop approval bound to the exact proposed action.
7. Durable checkpoint/resume across a real process restart.
8. Idempotent side-effect execution and duplicate-effect prevention.
9. Long-term memory separated from thread state and from authorization.
10. OpenTelemetry instrumentation for model, retrieval, policy, approval, tool and recovery operations.
11. A first-class evaluation harness covering outputs, trajectories and environment state.
12. Security/adversarial scenarios including prompt injection, malicious tool output and memory poisoning.
13. A static recruiter-facing Vercel demo that replays evidence from real accepted local runs without pretending to execute a live LLM.
14. Reproducible documentation and repository-level engineering discipline appropriate to Staff-level work.

## Canonical reference flow

```text
Single task request
→ load scoped memory hints
→ retrieve runbooks/policies with hybrid RAG
→ model selects answer or MCP action
→ validate tool/action schema
→ deterministic policy gate
→ read-only action executes directly
OR
→ side-effecting action creates an exact approval request and pauses
→ user approves/rejects
→ exact action digest is revalidated
→ effect executes with idempotency key
→ observation returns to graph
→ agent completes or takes another bounded step
→ audit + OTel trace + evaluation artifacts are produced
```

## Canonical local model path

- Default chat model: `qwen3:4b` through Ollama.
- Default embedding model: `qwen3-embedding:0.6b` through Ollama.
- The chat provider contract must also support an OpenAI-compatible vLLM endpoint without changing the graph or tool/policy layers.
- A generic OpenAI-compatible cloud endpoint may be configured, but no paid/cloud provider may be required for installation, tests, acceptance or the public demo.

## Completion semantics

`PROJECT_COMPLETE` is allowed only when every mandatory gate in `11_ACCEPTANCE_GATES.md` is PASS on the final candidate and the manual release checklist has been executed by the user.

A hardware-dependent vLLM live run is not mandatory. Its provider contract is mandatory; live vLLM execution is `OPTIONAL_HARDWARE_VALIDATION` unless a suitable GPU environment exists.

The public Vercel deployment is a static replay UI. It must never claim that its displayed runs are live inference.
