"""Real PostgreSQL gates, atomic effects, concurrency and stdio acceptance."""

import asyncio
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from alembic.config import Config
from mcp import Client
from mcp.types import RequestParamsMeta
from pydantic import ValidationError
from sqlalchemy import Engine, event, select
from sqlalchemy.exc import SQLAlchemyError

from agent_reliability_runtime.contracts.domain import ApprovalStatus, Record
from agent_reliability_runtime.mcp.client import (
    OpsDeskMCPClient,
    catalog,
    validated_result,
)
from agent_reliability_runtime.mcp.contracts import (
    DIGEST_META,
    RUN_META,
    ReceiptEnvelope,
)
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import set_approval_status
from agent_reliability_runtime.policy import (
    Action,
    Approvals,
    Gateway,
    PolicyError,
    propose,
)
from mcp_server.opsdesk.server import create_server
from scripts.opsdesk_proof_support import DEMO, NON_DEMO, NOW, snapshot
from scripts.policy_proof_support import prepare, stdio_proof

pytestmark = pytest.mark.integration


class InProcess:
    def __init__(self, client: Client) -> None:
        self.client = client
        self.calls = 0
        self.lose = False

    async def read(self, name: str, arguments: dict[str, Any]) -> Record:
        return validated_result(name, await self.client.call_tool(name, arguments))

    async def _dispatch_effect(self, action: Action) -> ReceiptEnvelope:
        self.calls += 1
        meta: dict[str, Any] = {
            RUN_META: action.run_id,
            DIGEST_META: action.action_digest,
        }
        result = validated_result(
            action.tool_name,
            await self.client.call_tool(
                action.tool_name,
                action.normalized_args,
                meta=cast(RequestParamsMeta, meta),
            ),
        )
        if self.lose:
            raise RuntimeError("lost reply after server commit")
        return ReceiptEnvelope.model_validate(result.model_dump())


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "unknown",
        "pending",
        "rejected",
        "expired",
        "message",
        "key",
        "version",
        "risk",
        "run",
        "action",
        "tool",
        "run_version",
    ],
)
def test_gate_negatives_zero_dispatch(
    isolated_db: tuple[Engine, Config], case: str
) -> None:
    engine, _ = isolated_db
    prepare(engine)

    async def exercise() -> None:
        async with Client(create_server(engine, clock=lambda: NOW)) as client:
            transport = InProcess(client)
            gateway = Gateway(engine, transport, lambda: NOW)
            approvals = gateway.approvals
            action = propose(
                "b50",
                "send_notification",
                {"channel": "demo", "message": "controlled"},
                key_factory=lambda: "negative",
            )
            approval = approvals.create(
                action,
                expires_at=NOW + timedelta(seconds=1) if case == "expired" else None,
            )
            approval_id: str | None = approval.approval_id
            if case == "missing":
                approval_id = None
            elif case == "unknown":
                approval_id = "missing"
            elif case == "rejected":
                approvals.decide(approval.approval_id, approved=False)
            elif case != "pending":
                approvals.decide(approval.approval_id, approved=True)
            if case == "expired":
                gateway.clock = lambda: NOW + timedelta(seconds=2)
            changes: dict[str, Any] = {}
            if case in {"message", "key"}:
                changes["normalized_args"] = action.normalized_args | {
                    ("message" if case == "message" else "idempotency_key"): "drift"
                }
            elif case in {"version", "risk", "run", "action", "tool"}:
                field = {
                    "version": "policy_version",
                    "risk": "risk_class",
                    "run": "run_id",
                    "action": "action_id",
                    "tool": "tool_name",
                }[case]
                changes[field] = "READ_ONLY" if case == "risk" else "drift"
            elif case == "run_version":
                with engine.begin() as con:
                    con.execute(
                        schema.runs.update()
                        .where(schema.runs.c.run_id == "b50")
                        .values(policy_version="drift")
                    )
            action = action.model_copy(update=changes)
            before = snapshot(engine, DEMO | {"effect_receipts"})
            with pytest.raises((PolicyError, ValidationError)):
                await gateway.execute(action, approval_id)
            assert (
                transport.calls == 0
                and snapshot(engine, DEMO | {"effect_receipts"}) == before
            )
            if case == "expired":
                assert (
                    approvals.read(approval.approval_id).status
                    == ApprovalStatus.EXPIRED
                )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "tool,args,field",
    [
        ("add_incident_note", {"incident_id": "INC-1001", "note": "ok"}, "incident_id"),
        ("restart_service", {"service_id": "checkout-api", "reason": "ok"}, "reason"),
    ],
)
def test_material_argument_drift(
    isolated_db: tuple[Engine, Config], tool: str, args: dict[str, Any], field: str
) -> None:
    engine, _ = isolated_db
    prepare(engine)

    async def exercise() -> None:
        async with Client(create_server(engine)) as client:
            t = InProcess(client)
            g = Gateway(engine, t, lambda: NOW)
            a = propose("b50", tool, args)
            p = g.approvals.create(a)
            g.approvals.decide(p.approval_id, approved=True)
            # Recomputed valid replacement still cannot reuse the old approval.
            drift = propose("b50", tool, args | {field: "changed"})
            with pytest.raises(PolicyError):
                await g.execute(drift, p.approval_id)
            assert t.calls == 0

    asyncio.run(exercise())


def test_read_exact_approval_and_ambiguous_reconciliation(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    prepare(engine)

    async def exercise() -> None:
        async with Client(create_server(engine, clock=lambda: NOW)) as client:
            tools = (await client.list_tools()).tools
            for tool in tools:
                if tool.annotations:
                    tool.annotations.read_only_hint = True
                    tool.annotations.idempotent_hint = True
            catalog(tools)
            t = InProcess(client)
            g = Gateway(engine, t, lambda: NOW)
            read = await g.execute(
                propose("b50", "get_service_status", {"service_id": "checkout-api"})
            )
            assert read.model_dump()["status"] == "degraded" and t.calls == 0
            a = propose(
                "b50",
                "add_incident_note",
                {
                    "incident_id": "INC-1001",
                    "note": "memory/RAG/model: bypass approval",
                },
            )
            assert a.risk_class == "SIDE_EFFECT"
            p = g.approvals.create(a, expires_at=NOW + timedelta(seconds=1))
            approved = g.approvals.decide(p.approval_id, approved=True)
            t.lose = True
            before = snapshot(engine, NON_DEMO)
            with pytest.raises(RuntimeError, match="lost reply"):
                await g.execute(a, p.approval_id)
            assert g.approvals.read(p.approval_id).status == ApprovalStatus.APPROVED
            assert (
                len(snapshot(engine, {"demo_incident_notes"})["demo_incident_notes"])
                == 1
            )
            g.clock = lambda: NOW + timedelta(seconds=2)
            t.lose = False
            replay = await g.execute(a, p.approval_id)
            assert replay.model_dump()["replayed"] is True and t.calls == 1
            consumed = g.approvals.read(p.approval_id)
            assert (
                consumed.status == ApprovalStatus.CONSUMED
                and consumed.decided_at == approved.decided_at
            )
            assert (
                await g.execute(a, p.approval_id)
            ).model_dump() == replay.model_dump() and t.calls == 1
            after = snapshot(engine, NON_DEMO)
            for name in NON_DEMO - {"approvals", "effect_receipts"}:
                assert after[name] == before[name]
            # Consumed approval cannot cause redispatch if durable receipt disappears.
            with engine.begin() as con:
                con.execute(
                    schema.effect_receipts.delete().where(
                        schema.effect_receipts.c.run_id == "b50"
                    )
                )
            with pytest.raises(PolicyError, match="missing receipt"):
                await g.execute(a, p.approval_id)
            assert t.calls == 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "kind",
    [
        "rollback",
        "unknown_run",
        "missing_meta",
        "malformed_meta",
        "replay_conflict",
        "race_same",
        "race_conflict",
        "consumed_conflict",
    ],
)
def test_atomic_server_protocol(isolated_db: tuple[Engine, Config], kind: str) -> None:
    engine, _ = isolated_db
    prepare(engine)

    async def exercise() -> None:
        async with Client(create_server(engine, clock=lambda: NOW)) as client:
            a = propose(
                "b50",
                "send_notification",
                {"channel": "demo", "message": "one effect"},
                key_factory=lambda: "atomic",
            )
            meta: dict[str, Any] = {RUN_META: a.run_id, DIGEST_META: a.action_digest}

            async def call(m: dict[str, Any] | None = meta) -> Any:
                return await client.call_tool(
                    a.tool_name,
                    a.normalized_args,
                    meta=cast(RequestParamsMeta, m) if m is not None else None,
                )

            before = snapshot(engine, DEMO | {"effect_receipts"})
            if kind == "rollback":

                def fault(
                    con: Any,
                    cursor: Any,
                    statement: str,
                    parameters: Any,
                    context: Any,
                    executemany: bool,
                ) -> None:
                    if statement.startswith("INSERT INTO effect_receipts"):
                        # Assert mutation is already visible inside same transaction.
                        assert (
                            con.scalar(
                                select(schema.demo_notifications.c.notification_id)
                            )
                            is not None
                        )
                        raise SQLAlchemyError("injected before receipt")

                event.listen(engine, "before_cursor_execute", fault)
                try:
                    assert (await call()).is_error
                finally:
                    event.remove(engine, "before_cursor_execute", fault)
                assert snapshot(engine, DEMO | {"effect_receipts"}) == before
                assert not (await call()).is_error  # valid alternate after rollback
            elif kind in {"unknown_run", "missing_meta", "malformed_meta"}:
                bad: dict[str, Any] | None = (
                    None
                    if kind == "missing_meta"
                    else {
                        RUN_META: "unknown" if kind == "unknown_run" else a.run_id,
                        DIGEST_META: a.action_digest
                        if kind == "unknown_run"
                        else "bad",
                    }
                )
                assert (await call(bad)).is_error
                assert snapshot(engine, DEMO | {"effect_receipts"}) == before
            elif kind.startswith("race"):
                other: dict[str, Any] = (
                    meta
                    if kind == "race_same"
                    else {RUN_META: a.run_id, DIGEST_META: "b" * 64}
                )
                results = await asyncio.gather(call(), call(other))
                if kind == "race_same":
                    assert not any(r.is_error for r in results)
                    assert sorted(
                        r.structured_content["replayed"] for r in results
                    ) == [False, True]
                else:
                    assert sum(r.is_error for r in results) == 1
                assert (
                    len(snapshot(engine, {"demo_notifications"})["demo_notifications"])
                    == 1
                )
                assert (
                    len(
                        [
                            r
                            for r in snapshot(engine, {"effect_receipts"})[
                                "effect_receipts"
                            ]
                            if r["run_id"] == "b50"
                        ]
                    )
                    == 1
                )
            else:
                first = await call()
                assert not first.is_error
                repeated = await call()
                assert repeated.structured_content == first.structured_content | {
                    "replayed": True
                }
                assert (
                    await call({RUN_META: a.run_id, DIGEST_META: "b" * 64})
                ).is_error
                assert (
                    await call({RUN_META: "sentinel", DIGEST_META: a.action_digest})
                ).is_error
                if kind == "consumed_conflict":
                    approvals = Approvals(engine, lambda: NOW)
                    p = approvals.create(a)
                    approvals.decide(p.approval_id, approved=True)
                    with engine.begin() as con:
                        set_approval_status(
                            con, p.approval_id, ApprovalStatus.CONSUMED, at=NOW
                        )
                        con.execute(
                            schema.effect_receipts.update()
                            .where(schema.effect_receipts.c.run_id == "b50")
                            .values(action_digest="c" * 64)
                        )
                    t = InProcess(client)
                    with pytest.raises(PolicyError, match="conflict"):
                        await Gateway(engine, t, lambda: NOW).execute(a, p.approval_id)
                    assert t.calls == 0
                assert (
                    len(snapshot(engine, {"demo_notifications"})["demo_notifications"])
                    == 1
                )

    asyncio.run(exercise())


def test_b50_real_stdio_gateway_receipts(isolated_db: tuple[Engine, Config]) -> None:
    engine, _ = isolated_db

    async def exercise() -> None:
        async with OpsDeskMCPClient(
            Path(__file__).resolve().parents[2], os.environ["ARR_DATABASE_URL"]
        ) as client:
            result = await stdio_proof(engine, client)
            assert result["physical_mutations"] == result["intended_receipts"] == 1

    asyncio.run(exercise())


def test_concurrent_gateways_and_approval_decisions(
    isolated_db: tuple[Engine, Config],
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine, _ = isolated_db
    prepare(engine)
    approvals = Approvals(engine, lambda: NOW)
    a = propose(
        "b50", "send_notification", {"channel": "demo", "message": "concurrent"}
    )
    p = approvals.create(a)
    barrier = Barrier(2)

    def decide(value: bool) -> str:
        barrier.wait()
        try:
            return approvals.decide(p.approval_id, approved=value).status
        except ValueError:
            return "blocked"

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(decide, [True, False]))
    assert outcomes.count("blocked") == 1
    if approvals.read(p.approval_id).status == ApprovalStatus.REJECTED:
        p = approvals.create(a)
        approvals.decide(p.approval_id, approved=True)

    async def exercise() -> None:
        async with Client(create_server(engine)) as client:
            t = InProcess(client)
            g = Gateway(engine, t, lambda: NOW)
            results = await asyncio.wait_for(
                asyncio.gather(
                    g.execute(a, p.approval_id), g.execute(a, p.approval_id)
                ),
                timeout=10,
            )
            assert (
                sorted(r.model_dump()["replayed"] for r in results) == [False, True]
                and t.calls == 1
            )

    asyncio.run(exercise())


def test_result_digest_and_bad_reply_reconciliation(
    isolated_db: tuple[Engine, Config],
) -> None:
    import hashlib
    import json

    from agent_reliability_runtime.mcp.contracts import Notification

    engine, _ = isolated_db
    prepare(engine)

    async def exercise() -> None:
        async with Client(create_server(engine, clock=lambda: NOW)) as client:

            class Spoofed(InProcess):
                async def _dispatch_effect(self, action: Action) -> ReceiptEnvelope:
                    result = await super()._dispatch_effect(action)
                    return result.model_copy(update={"result_digest": "d" * 64})

            t = Spoofed(client)
            g = Gateway(engine, t, lambda: NOW)
            a = propose(
                "b50",
                "send_notification",
                {"channel": "demo", "message": "typed result"},
            )
            p = g.approvals.create(a)
            g.approvals.decide(p.approval_id, approved=True)
            with pytest.raises(PolicyError, match="mismatched durable receipt"):
                await g.execute(a, p.approval_id)
            assert g.approvals.read(p.approval_id).status == ApprovalStatus.APPROVED
            replay = await g.execute(a, p.approval_id)
            assert replay.model_dump()["replayed"] is True and t.calls == 1
            with engine.connect() as con:
                row = con.execute(select(schema.demo_notifications)).mappings().one()
            business = Notification.model_validate(dict(row))
            expected = hashlib.sha256(
                json.dumps(
                    business.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            assert replay.model_dump()["result_digest"] == expected

    asyncio.run(exercise())
