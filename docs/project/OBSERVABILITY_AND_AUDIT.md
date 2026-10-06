# Observability, Audit, and Replay

Replay export requires the exact eval-trial-v1 receipt profile, including source
SHA, scenario-set and lockfile digests. See the
[Evaluation Harness](EVALUATION_HARNESS.md) for receipt construction and calibration.

Manual OTel API/SDK 1.45.0 instrumentation accepts a standard injected tracer.
No import sets a global provider or requires an exporter/collector/vendor sink.
Default runtime telemetry works with the standard no-op tracer. Tests use an
independent SDK provider, SimpleSpanProcessor and InMemorySpanExporter.

All twelve locked spans are covered: agent.run, agent.model.call,
agent.retrieval.search, agent.memory.read, agent.memory.write,
agent.action.validate, agent.policy.evaluate, agent.approval.wait,
agent.approval.resume, agent.tool.call, agent.recovery.resume and agent.finalize.
The wait span ends before interrupt. Start/resume/recovery are separate run
segments; process death never fabricates a surviving parent span. The fresh worker
proof reconstructs its own tracer and persists exact recovery correlation.

GenAI attributes cover operation/model/finish reasons and only reported usage;
there is no price table or cost. Project correlation/state uses arr.*. No default
prompt/system/tool args/results/memory/query content is attached. Automatic OTel
exception text/stack capture is disabled; failure class/status are bounded metadata.
Audit payloads use per-event allowlists plus shared recursive redaction before
persistence, preserving safe digests and reported numeric token counts.

## Audit and memory control plane

AuditTrail exposes append/list and transaction-local append, with no update/delete
application operation. Each append validates the run, locks a deterministic
PostgreSQL transaction advisory key, allocates max(sequence)+1, and inserts a
strict AuditEvent. Event identity is SHA-256 of canonical run/sequence/type.
Sequence, not timestamp, orders events. Rollback consumes no sequence. Genuine
repeated attempts are appended; no semantic ensure hides retries.

Stage events persist the active span's actual lowercase 32/16 trace/span IDs;
without a valid current span IDs are null. Tests match IDs and expected stage
names against actual SDK exports and calibrate wrong correlation/missing spans.

Memory create/delete uses one deterministic memory-audit anchor per workspace/user
scope, transactionally locked and validated. It has no scenario, internal provider,
memory-control model, fixed safe request, COMPLETED status and zero counters. It
never executes LangGraph. Memory mutation and allowlisted created/deleted audit
event commit together; forced audit failure rolls deletion back. Deleted content
is absent from anchor, audit and default telemetry. Missing/foreign DELETE stays
indistinguishable. Anchors cannot be exported as scenario replays.

## Local API

Health and scoped memory endpoints remain. GET /api/v1/runs/{run_id} returns strict
Run or bounded 404. GET /api/v1/runs/{run_id}/events returns strict snapshots sorted
by sequence, or 404 for unknown run. readyz checks DB, all project tables and four
framework checkpoint tables, returning ready/200 or bounded 503. It makes no model
or network-provider call. POST `/api/v1/runs` starts a bounded local run and
POST `/api/v1/runs/{run_id}/approvals/{approval_id}` records an exact persisted
decision before graph resume. These local control routes are not a public
demo backend or an enterprise authentication surface.

## Fail-closed replay export

CLI: `python -m agent_reliability_runtime.cli export-replays --run-id ID --receipt
PATH --source-git-sha SHA --output PATH`.

The narrow validator reads both exact locked schema files at execution and supports
only their actual keyword subset; it is not a general JSON Schema engine. Receipt
must be schema-valid and match source SHA, locked scenario-set and both lockfile
digests. Its seven named gates cover L0–L4, HARD_INVARIANTS and TASK_SUCCESS.
L0/L2/L3/hard/task must PASS; only legitimately inapplicable L1/L4 may be
NOT_APPLICABLE. Weak arbitrary-PASS receipts, FAIL, NOT_RUN and NOT_REVIEWED reject.
Canonical receipt digest is SHA-256 of sorted-key compact UTF-8 JSON.

Run must exist, be terminal and have a scenario. Audit must be nonempty and
contiguous from 1. Export synthesizes sanitized request, ordered safe audit events,
and eval.acceptance. Candidate schema and final-byte credential/sensitive-field
checks precede any write. Temporary replay/manifest files are replaced only after
both validations pass. Manifest binds source run/SHA, receipt digest and replay
SHA-256. Same inputs produce identical bytes; changing receipt/audit changes the
appropriate digest. Unsafe final sentinel fixture creates neither artifact.

Exporter tests use temporary profile-valid fixtures and calibrated unsafe
counterexamples. The [Static Evidence Demo](STATIC_EVIDENCE_DEMO.md) separately
ships five accepted replay/receipt pairs bound to their immutable runtime source.
Real OS kill/restart and memory poisoning/delete-after-checkpoint regressions
remain mandatory under instrumentation.

Primary sources: [manual instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
and [GenAI attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/).
