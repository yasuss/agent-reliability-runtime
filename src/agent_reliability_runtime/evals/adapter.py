"""Project record/audit/retrieval adapter; validates before digest-only projection."""

import hashlib
from typing import Any

from sqlalchemy import Engine, select

from agent_reliability_runtime.contracts.domain import (
    Approval,
)
from agent_reliability_runtime.contracts.domain import (
    EffectReceipt as DurableReceipt,
)
from agent_reliability_runtime.evals.contracts import (
    ActionBinding,
    ApprovalBinding,
    EffectReceipt,
    RetrievedEvidence,
    Step,
    TrialEvidence,
)
from agent_reliability_runtime.observability import (
    AuditTrail,
    canonical,
    read_run,
    sanitize,
)
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.policy import Action, validate_action
from agent_reliability_runtime.retrieval.contracts import Evidence
from mcp_server.opsdesk.effects import row_id


def bind_action(action: Action) -> ActionBinding:
    action = validate_action(Action.model_validate(action.model_dump()))
    return ActionBinding(
        run_id=action.run_id,
        action_id=action.action_id,
        tool_name=action.tool_name,
        policy_version=action.policy_version,
        action_digest=action.action_digest,
        args_digest=hashlib.sha256(canonical(action.normalized_args)).hexdigest(),
        wire_fields=sorted(action.normalized_args),
        schema_valid=True,
    )


def environment_snapshot(engine: Engine) -> dict[str, str]:
    """All fictional tables, row IDs and raw-row digests; never raw content."""
    result = {}
    with engine.connect() as con:
        for table in (
            schema.demo_services,
            schema.demo_incidents,
            schema.demo_notifications,
            schema.demo_incident_notes,
        ):
            key = list(table.primary_key.columns)[0].name
            for row in con.execute(select(table)).mappings():
                obj = {
                    k: v.isoformat() if hasattr(v, "isoformat") else v
                    for k, v in row.items()
                }
                result[table.name + "/" + str(row[key])] = hashlib.sha256(
                    canonical(obj)
                ).hexdigest()
    return result


def capture(
    engine: Engine,
    *,
    run_id: str,
    scenario_id: str,
    subject_sha: str,
    trial_id: str,
    actions: list[Action],
    before: dict[str, str],
    retrieved: list[Evidence] | None = None,
    cited_ids: list[str] | None = None,
    final_answer: str = "",
    replay_json: str | None = None,
    physical_calls: dict[str, int] | None = None,
) -> TrialEvidence:
    with engine.connect() as con:
        run = read_run(con, run_id)
        if run is None:
            raise ValueError("unknown evidence run")
        if run.scenario_id != scenario_id:
            raise ValueError("persisted run/scenario binding mismatch")
        approvals = [
            Approval.model_validate(dict(r))
            for r in con.execute(
                select(schema.approvals).where(schema.approvals.c.run_id == run_id)
            ).mappings()
        ]
        receipts = [
            DurableReceipt.model_validate(dict(r))
            for r in con.execute(
                select(schema.effect_receipts).where(
                    schema.effect_receipts.c.run_id == run_id
                )
            ).mappings()
        ]
        current = dict(
            con.execute(
                select(
                    schema.knowledge_documents.c.document_id,
                    schema.knowledge_documents.c.content_digest,
                )
            )
            .tuples()
            .all()
        )
    projected_actions = [bind_action(a) for a in actions]
    projected_approvals = []
    for a in approvals:
        action = Action.model_validate(
            a.model_dump(
                exclude={
                    "approval_id",
                    "status",
                    "created_at",
                    "decided_at",
                    "expires_at",
                }
            )
        )
        projected_approvals.append(
            ApprovalBinding(
                approval_id=a.approval_id,
                action=bind_action(action),
                status=a.status.value,
            )
        )
    trajectory = []
    latest: ActionBinding | None = None
    for event in AuditTrail(engine).list(run_id):
        p: dict[str, Any] = event.payload
        if event.event_type == "action.validated":
            latest = next(
                (a for a in projected_actions if a.action_id == p.get("action_id")),
                None,
            )
        trajectory.append(
            Step(
                sequence=event.sequence_number,
                event_type=event.event_type,
                tool_name=p.get("tool_name"),
                action_id=latest.action_id
                if event.event_type == "tool.completed" and latest
                else p.get("action_id"),
                action_digest=latest.action_digest
                if event.event_type == "tool.completed" and latest
                else p.get("action_digest"),
                approval_id=p.get("approval_id"),
                approval_status=p.get("status")
                if event.event_type.startswith("approval.")
                else None,
                receipt_id=p.get("receipt_id"),
                replayed=p.get("replayed", False),
            )
        )
    after = environment_snapshot(engine)
    effects = {}
    projected_receipts = []
    for r in receipts:
        identity = row_id(r.tool_name, r.idempotency_key)
        if r.receipt_id != identity:
            raise ValueError("durable receipt identity mismatch")
        table = {
            "send_notification": "demo_notifications",
            "add_incident_note": "demo_incident_notes",
        }.get(r.tool_name)
        if table is None and physical_calls is None:
            raise ValueError(
                "adapter needs explicit physical-call evidence for non-append mutation"
            )
        if physical_calls is None:
            key = str(table) + "/" + identity
            effects[identity] = int(key not in before and key in after)
        projected_receipts.append(
            EffectReceipt(
                receipt_id=r.receipt_id,
                run_id=r.run_id,
                tool_name=r.tool_name,
                logical_identity=identity,
                action_digest=r.action_digest,
                result_digest=r.result_digest,
            )
        )
    snapshots = [Evidence.model_validate(r.model_dump()) for r in (retrieved or [])]
    return TrialEvidence(
        subject_sha=subject_sha,
        scenario_id=scenario_id,
        trial_id=trial_id,
        run_id=run_id,
        retrieved=[
            RetrievedEvidence(
                **r.model_dump(
                    include={
                        "evidence_id",
                        "document_id",
                        "document_digest",
                        "source_path",
                    }
                )
            )
            for r in snapshots
        ],
        current_document_digests=current,
        cited_ids=cited_ids or [],
        actions=projected_actions,
        approvals=projected_approvals,
        trajectory=trajectory,
        model_steps=run.model_steps,
        tool_steps=run.tool_steps,
        terminal_status=run.status.value,
        before=before,
        after=after,
        physical_effect_counts=effects if physical_calls is None else physical_calls,
        retries=sum(s.event_type == "tool.retry" for s in trajectory),
        receipts=projected_receipts,
        final_answer=sanitize(final_answer),
        replay_json=replay_json,
    )
