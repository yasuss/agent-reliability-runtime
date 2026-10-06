# Architecture

This document is the current orientation for the accepted implementation. The
locked contracts remain the authority for exact schemas and invariants:
[architecture contracts](spec/v1.0/02_ARCHITECTURE.md),
[runtime contracts](spec/v1.0/03_RUNTIME_CONTRACTS.md),
[state model](spec/v1.0/04_DATA_AND_STATE_MODEL.md), and
[security model](spec/v1.0/05_SECURITY_AND_TRUST.md).

## Topology and ownership

The repository contains one production LangGraph graph. A local FastAPI control
surface creates runs and exposes health/readiness, while PostgreSQL stores domain
records, retrieval documents, audit events, effect receipts, approvals and
LangGraph checkpoints. The OpsDesk MCP server is a genuine stdio subprocess with
fictional state and five tools. The static web is a separate recorded-replay
viewer and never opens a backend connection.

The main boundaries are:

1. provider adapters normalize chat, tool calls and embeddings;
2. retrieval returns evidence with canonical IDs and current-source digests;
3. memory resolves only scoped IDs from a checkpoint and remains non-authorizing;
4. the graph validates typed actions and sends every tool action to the B50
   trusted gateway;
5. policy classifies risk, exact approval authorizes required side effects, and
   idempotency/effect receipts reconcile retries;
6. postcondition verification records the observed result before completion;
7. audit and OTel events correlate the run, trace and span without raw secrets;
8. deterministic evaluators inspect persisted state, effects, receipts and
   sanitized evidence.

## Trust and data flow

Current configuration and trusted policy outrank local approval, verified tool
state, user task text, memory, retrieval and model observations. None of the
lower-trust content can grant authorization or suppress approval. MCP annotations
are metadata only. Action arguments are validated before policy and again before
execution.

For a side effect, the graph proposes a typed action, the gateway computes the
canonical action digest and the approval record binds that digest. Resume checks
the same run, owner, approval status, action digest and idempotency key. A receipt
is the durable boundary for exactly-once effect reconciliation. An ambiguous
outcome is reconciled against that receipt before any retry.

## Durability and verification obligation

LangGraph uses the PostgreSQL checkpointer. An approval interrupt can resume in a
fresh process, including the accepted S08 kill point after effect commit and
before the graph checkpoint. The postcondition verification obligation is
durable: completion cannot be finalized until the model emits the required real
structured read and the observed state matches the obligation. The matching
post-restart status read is part of the final S02/R10 contract.

## Evidence boundaries

The [Evidence & Proof map](EVIDENCE_AND_PROOF.md) and
[PROOF_INDEX](PROOF_INDEX.json) point each capability to a real tracked test,
script or replay. The locked spec and accepted implementation/tests are stronger
than historical task prose. The architecture describes ownership; it does not
replace the executable gates.
