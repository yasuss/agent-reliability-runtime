# 02 — Target Architecture

## Architectural thesis

The model is replaceable. Reliability comes from the harness around it: explicit state, bounded orchestration, trusted policy, exact approvals, effect receipts, observability and evaluations.

## Component diagram

```text
                         ┌────────────────────────────┐
                         │ Local caller / API / CLI   │
                         └──────────────┬─────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │ FastAPI boundary   │
                              └─────────┬──────────┘
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │ LangGraph Agent Runtime                    │
                  │ bounded steps + checkpoints + interrupts   │
                  └───────┬──────────────┬──────────────┬─────┘
                          │              │              │
                 ┌────────▼──────┐ ┌────▼────────┐ ┌──▼────────────┐
                 │ RAG Context   │ │ Model       │ │ Memory        │
                 │ Postgres/FTS  │ │ Provider    │ │ governed      │
                 │ + pgvector    │ │ boundary    │ │ long-term     │
                 └────────┬──────┘ └────┬────────┘ └──┬────────────┘
                          │             │             │
                          └─────────────┼─────────────┘
                                        │
                               proposed tool action
                                        │
                              ┌─────────▼──────────┐
                              │ Trusted Policy     │
                              │ + exact approval   │
                              └─────────┬──────────┘
                                        │
                              ┌─────────▼──────────┐
                              │ MCP Client Adapter │
                              └─────────┬──────────┘
                                        │ stdio
                              ┌─────────▼──────────┐
                              │ OpsDesk MCP Server │
                              │ deterministic mock │
                              │ enterprise state   │
                              └────────────────────┘

     Cross-cutting: PostgreSQL persistence · OpenTelemetry · audit events · eval harness
```

## Required layering

Dependencies must point inward/downward through these conceptual layers:

```text
api / cli / replay-export
        ↓
application runtime / graph
        ↓
policy | retrieval | memory | providers | mcp adapter
        ↓
domain contracts / schemas
        ↓
infrastructure adapters (Postgres, Ollama/OpenAI-compatible, OTel)
```

The agent graph must not bypass policy to execute an MCP tool. The MCP server must not decide whether the caller is authorized to invoke a business side effect; it validates tool inputs and applies idempotency, while the trusted runtime policy decides whether execution is allowed.

## Agent graph

The graph must expose named nodes or equivalent observable stages:

1. `prepare_run`
2. `load_memory`
3. `retrieve_context`
4. `decide`
5. `validate_action`
6. `policy_gate`
7. `await_approval` when required
8. `execute_tool`
9. `observe_result`
10. `finalize`

A model may choose to answer without a tool, but cannot directly invoke a tool implementation.

## Bounded execution

- Default model-decision step budget: 8.
- Hard configurable ceiling: 12.
- The runtime must terminate with an explicit non-success state when the budget is exhausted.
- No retry loop may be unbounded.
- Transient tool retry default: maximum 2 retries after the initial attempt, with bounded backoff.
- A side-effecting tool is never blindly retried after an ambiguous outcome; the runtime first checks the effect receipt/idempotency state.

## Persistence

Use LangGraph PostgreSQL checkpointing for graph state. Application tables remain explicitly owned by this project. Checkpoint schema setup/migration is run as an explicit setup step, not silently on every app start.

## Transport choices

- MCP reference server transport: stdio for the canonical local demo.
- The reference server targets the current MCP protocol supported by the official Python SDK.
- HTTP auth, MCP Enterprise Managed Authorization and MCP Tasks are documented extension points, not v1 requirements.

## Frontend architecture

The static evidence viewer is a Vite React application that imports versioned JSON replay artifacts produced by the accepted backend runs. It has no secrets and no required runtime API.
