"""Disposable B40 infrastructure oracles, shared by tests and exact-head proof."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, inspect, select

from agent_reliability_runtime.contracts.domain import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    EffectReceipt,
    KnowledgeChunk,
    KnowledgeDocument,
    Memory,
    Record,
    Run,
    RunStatus,
    action_digest,
    chunk_id,
    document_id,
)
from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.mcp.client import OpsDeskError
from agent_reliability_runtime.mcp.contracts import INPUTS
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import Snapshot, insert_snapshot

NOW = datetime(2026, 10, 4, tzinfo=UTC)
DEMO = {name for name in schema.metadata.tables if name.startswith("demo_")}
NON_DEMO = set(schema.metadata.tables) - DEMO


def snapshot(engine: Engine, names: set[str]) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as con:
        return {
            name: [
                dict(row)
                for row in con.execute(
                    select(schema.metadata.tables[name]).order_by(
                        *schema.metadata.tables[name].primary_key.columns
                    )
                ).mappings()
            ]
            for name in sorted(names)
        }


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def seed_sentinels(engine: Engine) -> None:
    doc = document_id("sentinel/knowledge.md")
    sha = "a" * 64
    values: tuple[Snapshot, ...] = (
        Run(
            run_id="sentinel",
            workspace_id="local",
            user_id="test",
            request_text="retain",
            provider_id="fake",
            model_id="fake",
            policy_version="sentinel",
            status=RunStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
        ),
        Approval(
            approval_id="sentinel",
            run_id="sentinel",
            action_id="sentinel",
            tool_name="sentinel",
            normalized_args={},
            action_digest=action_digest("sentinel", "sentinel", {}, "sentinel"),
            policy_version="sentinel",
            risk_class="SIDE_EFFECT",
            status=ApprovalStatus.PENDING,
            created_at=NOW,
        ),
        EffectReceipt(
            receipt_id="sentinel",
            run_id="sentinel",
            tool_name="sentinel",
            idempotency_key="sentinel",
            action_digest=sha,
            result_digest=sha,
            applied_at=NOW,
        ),
        AuditEvent(
            event_id="sentinel",
            run_id="sentinel",
            sequence_number=1,
            event_type="SAFE",
            payload={"fixture": True},
            timestamp=NOW,
        ),
        Memory.model_validate(
            dict(
                memory_id="sentinel",
                workspace_id="local",
                user_id="test",
                kind="OBSERVATION",
                provenance="MODEL_OBSERVATION",
                content="retain",
                created_at=NOW,
                updated_at=NOW,
                source_run_id="sentinel",
            )
        ),
        KnowledgeDocument(
            document_id=doc,
            source_path="sentinel/knowledge.md",
            content_digest=sha,
            title="Retain",
        ),
        KnowledgeChunk(
            chunk_id=chunk_id(doc, sha, 0),
            document_id=doc,
            document_digest=sha,
            ordinal=0,
            content="retain",
        ),
    )
    with engine.begin() as con:
        for value in values:
            insert_snapshot(con, value)


async def state_proof(
    engine: Engine, call: Callable[..., Awaitable[Record]]
) -> dict[str, Any]:
    raw = call

    async def bound_call(name: str, args: dict[str, Any]) -> Record:
        from agent_reliability_runtime.mcp.contracts import (
            DIGEST_META,
            RUN_META,
            RUNTIME_FIELDS,
        )

        meta = None
        if name in RUNTIME_FIELDS:
            meta = {
                RUN_META: "sentinel",
                DIGEST_META: action_digest("sentinel", name, args, "sentinel"),
            }
        return await raw(name, args, meta=meta)

    call = bound_call
    reset_demo(engine, confirm_development_reset=True)
    seed_sentinels(engine)
    before = snapshot(engine, NON_DEMO)
    tables_before = inspect(engine).get_table_names()
    assert len(before) == 7 and all(len(rows) == 1 for rows in before.values())
    incident = await call("get_incident", {"incident_id": "INC-1001"})
    service = await call("get_service_status", {"service_id": "checkout-api"})
    assert incident.model_dump() == {
        "incident_id": "INC-1001",
        "service_id": "checkout-api",
        "summary": "intermittent 5xx",
        "status": "open",
    }
    assert service.model_dump() == {"service_id": "checkout-api", "status": "degraded"}
    unchanged_demo = snapshot(engine, DEMO)
    bad_count = 0
    for name, arg_model in INPUTS.items():
        good: dict[str, Any] = {field: "fixture" for field in arg_model.model_fields}
        for bad in ({}, good | {"extra": "forged"}, good | {next(iter(good)): 7}):
            try:
                await call(name, bad)
            except OpsDeskError:
                bad_count += 1
            else:
                raise AssertionError("invalid raw arguments accepted")
    for name, args in (
        ("unknown", {}),
        ("get_incident", {"incident_id": "missing"}),
        ("get_service_status", {"service_id": "missing"}),
        (
            "add_incident_note",
            {"incident_id": "missing", "note": "fixture", "idempotency_key": "bad"},
        ),
        (
            "restart_service",
            {"service_id": "missing", "reason": "fixture", "idempotency_key": "bad"},
        ),
    ):
        try:
            await call(name, args)
        except OpsDeskError:
            bad_count += 1
        else:
            raise AssertionError("unknown tool/ID accepted")
    assert snapshot(engine, DEMO) == unchanged_demo
    note_args = {
        "incident_id": "INC-1001",
        "note": "controlled fictional note",
        "idempotency_key": "note-proof",
    }
    notification_args = {
        "channel": "demo",
        "message": "controlled fictional message",
        "idempotency_key": "notification-proof",
    }
    note = await call("add_incident_note", note_args)
    restarted = await call(
        "restart_service",
        {
            "service_id": "checkout-api",
            "reason": "controlled fictional restart",
            "idempotency_key": "restart-proof",
        },
    )
    notification = await call("send_notification", notification_args)
    duplicates = 0
    for name, args, original in (
        ("add_incident_note", note_args, note),
        ("send_notification", notification_args, notification),
    ):
        replay = await call(name, args)
        assert replay.model_dump()["replayed"] is True
        assert replay.model_dump(exclude={"replayed"}) == original.model_dump(
            exclude={"replayed"}
        )
        duplicates += 1
    after_demo = snapshot(engine, DEMO)
    assert after_demo["demo_incidents"] == unchanged_demo["demo_incidents"]
    expected_services = [
        dict(row, status="healthy") if row["service_id"] == "checkout-api" else row
        for row in unchanged_demo["demo_services"]
    ]
    assert after_demo["demo_services"] == expected_services
    note_rows = after_demo["demo_incident_notes"]
    notification_rows = after_demo["demo_notifications"]
    assert len(note_rows) == len(notification_rows) == 1
    assert note_rows[0]["note"] == note_args["note"]
    assert note_rows[0]["incident_id"] == note_args["incident_id"]
    assert notification_rows[0]["channel"] == notification_args["channel"]
    assert notification_rows[0]["message"] == notification_args["message"]
    after = snapshot(engine, NON_DEMO)
    intended_receipts = [
        r for r in after["effect_receipts"] if r["receipt_id"] != "sentinel"
    ]
    assert len(intended_receipts) == 3
    for receipt in (note, restarted, notification):
        assert receipt.model_dump()["replayed"] is False
        assert receipt.model_dump(exclude={"replayed"}) in intended_receipts
    after["effect_receipts"] = [
        r for r in after["effect_receipts"] if r["receipt_id"] == "sentinel"
    ]
    assert after == before
    assert inspect(engine).get_table_names() == tables_before
    return {
        "read_incident": incident.model_dump(mode="json"),
        "read_service": service.model_dump(mode="json"),
        "note": note.model_dump(mode="json"),
        "restart": restarted.model_dump(mode="json"),
        "notification": notification.model_dump(mode="json"),
        "invalid_unknown_rejected": bad_count,
        "duplicate_receipts_replayed": duplicates,
        "non_demo_counts": {name: len(rows) for name, rows in before.items()},
        "non_demo_before_digest": digest(before),
        "non_demo_after_digest": digest(after),
        "only_intended_demo_changes": True,
        "intended_effect_receipts": len(intended_receipts),
        "schema_unchanged": True,
    }
