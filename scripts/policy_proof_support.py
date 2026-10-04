"""Real B50 stdio acceptance and independently asserted fictional state."""

from typing import Any

from sqlalchemy import Engine, select

from agent_reliability_runtime.contracts.domain import ApprovalStatus, Run, RunStatus
from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.mcp.client import OpsDeskError, OpsDeskMCPClient
from agent_reliability_runtime.mcp.contracts import (
    DIGEST_META,
    RUN_META,
    ReceiptEnvelope,
)
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import insert_snapshot
from agent_reliability_runtime.policy import VERSION, Approvals, Gateway, propose
from scripts.opsdesk_proof_support import (
    NON_DEMO,
    NOW,
    digest,
    seed_sentinels,
    snapshot,
)


def prepare(engine: Engine) -> None:
    reset_demo(engine, confirm_development_reset=True)
    seed_sentinels(engine)
    with engine.begin() as con:
        insert_snapshot(
            con,
            Run(
                run_id="b50",
                workspace_id="local",
                user_id="test",
                request_text="fictional approval",
                provider_id="fake",
                model_id="fake",
                policy_version=VERSION,
                status=RunStatus.CREATED,
                created_at=NOW,
                updated_at=NOW,
            ),
        )


async def stdio_proof(engine: Engine, client: OpsDeskMCPClient) -> dict[str, Any]:
    prepare(engine)
    before = snapshot(engine, NON_DEMO)
    approvals = Approvals(engine, lambda: NOW)
    action = propose(
        "b50",
        "send_notification",
        {"channel": "demo", "message": "approved fictional notification"},
        key_factory=lambda: "stdio-b50",
    )
    model = next(t for t in client.model_tools if t.name == action.tool_name)
    properties = model.parameters["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"channel", "message"}
    approval = approvals.create(action)
    approved = approvals.decide(approval.approval_id, approved=True)
    gateway = Gateway(engine, client, lambda: NOW)
    result = ReceiptEnvelope.model_validate(
        (await gateway.execute(action, approval.approval_id)).model_dump()
    )
    assert not result.replayed
    replay = ReceiptEnvelope.model_validate(
        (await gateway.execute(action, approval.approval_id)).model_dump()
    )
    assert replay.replayed and replay.model_dump(
        exclude={"replayed"}
    ) == result.model_dump(exclude={"replayed"})
    # Actual server replay too, not merely runtime reconciliation.
    raw = await client.raw_wire_call_for_testing(
        action.tool_name,
        action.normalized_args,
        meta={RUN_META: action.run_id, DIGEST_META: action.action_digest},
    )
    assert raw.model_dump() == replay.model_dump()
    try:
        await client.raw_wire_call_for_testing(
            action.tool_name,
            action.normalized_args,
            meta={RUN_META: action.run_id, DIGEST_META: "f" * 64},
        )
    except OpsDeskError:
        pass
    else:
        raise AssertionError("conflict accepted")
    with engine.connect() as con:
        rows = con.execute(select(schema.demo_notifications)).mappings().all()
        assert (
            len(rows) == 1 and rows[0]["message"] == action.normalized_args["message"]
        )
        receipts = (
            con.execute(
                select(schema.effect_receipts).where(
                    schema.effect_receipts.c.run_id == "b50"
                )
            )
            .mappings()
            .all()
        )
        assert len(receipts) == 1 and dict(receipts[0]) == result.model_dump(
            exclude={"replayed"}
        )
    consumed = approvals.read(approval.approval_id)
    assert (
        consumed.status == ApprovalStatus.CONSUMED
        and consumed.decided_at == approved.decided_at
    )
    after = snapshot(engine, NON_DEMO)
    assert after["runs"] == before["runs"]
    assert [r for r in after["approvals"] if r["approval_id"] == "sentinel"] == before[
        "approvals"
    ]
    assert len(after["approvals"]) == 2
    assert [
        r for r in after["effect_receipts"] if r["receipt_id"] == "sentinel"
    ] == before["effect_receipts"]
    for table in NON_DEMO - {"approvals", "effect_receipts"}:
        assert after[table] == before[table]
    return {
        "policy_version": VERSION,
        "action": action.model_dump(mode="json"),
        "approval": consumed.model_dump(mode="json"),
        "receipt": result.model_dump(mode="json"),
        "replay": replay.model_dump(mode="json"),
        "raw_server_replay": True,
        "conflict_rejected": True,
        "physical_mutations": 1,
        "intended_receipts": 1,
        "unrelated_sentinels_preserved": True,
        "model_args": model.parameters,
        "state_digest": digest(after),
    }
