# 06 — Observability Contract

## Mandatory foundation

Use OpenTelemetry APIs/SDK for traces. The project must not require a proprietary observability service.

Optional exporters may include Jaeger, an OTLP collector or Langfuse, but the runtime remains correct when none is configured.

## Required spans / operations

At minimum emit correlated spans for:

- `agent.run`
- `agent.model.call`
- `agent.retrieval.search`
- `agent.memory.read`
- `agent.memory.write`
- `agent.action.validate`
- `agent.policy.evaluate`
- `agent.approval.wait`
- `agent.approval.resume`
- `agent.tool.call`
- `agent.recovery.resume`
- `agent.finalize`

Use current OpenTelemetry GenAI semantic attributes when they directly apply. Project-specific attributes use a namespaced prefix such as `arr.*`.

## Minimum attributes

Low-cardinality attributes should make these questions answerable:

- Which run/scenario was this?
- Which provider/model executed?
- Which tool was requested?
- Was it read-only or side-effecting?
- Was approval required and what was its result?
- Was this tool result a replay of a prior effect receipt?
- How long did model, retrieval and tool stages take?
- How many model/tool steps occurred?
- Token usage when the provider reports it.
- Cost only when a configured price table establishes it; otherwise `cost_usd` remains absent/null, never guessed.
- Terminal outcome and failure class.

## Audit vs telemetry

OTel is operational telemetry. The project-owned `audit_events` stream is the durable domain audit trail used to build recruiter replays and deterministic eval assertions.

A trace export must correlate to audit events through run/trace/span IDs but neither layer substitutes for the other.

## Public replay exporter

`export-replays` converts accepted fictional runs into the replay schema, removes/redacts sensitive fields, records the source run and artifact digests, and refuses export if the run does not have an accepted eval receipt.
