"""Real audit concurrency/atomicity, exact emitted-span correlation and replay."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import Engine, create_engine, select, text

from agent_reliability_runtime.api import create_app
from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.memory import MemoryStore
from agent_reliability_runtime.observability import (
    REQUIRED_SPANS,
    AuditTrail,
    Telemetry,
    canonical,
)
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import insert_snapshot
from agent_reliability_runtime.providers.contracts import (
    ChatRequest,
    ChatResult,
    ToolCall,
    Usage,
)
from agent_reliability_runtime.replay import export_replay, locked_validate
from agent_reliability_runtime.retrieval.service import ingest
from agent_reliability_runtime.retrieval.text import plan_source
from agent_reliability_runtime.runtime.checkpoints import run_async, setup_checkpoints
from agent_reliability_runtime.runtime.service import open_runtime
from scripts.runtime_proof_support import (
    Embeddings,
    ScriptedProvider,
    context_for,
    run_record,
)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_concurrent_audit_and_rollback(
    isolated_db: tuple[Engine, Config], tmp_path: Path
) -> None:
    engine, _ = isolated_db
    with engine.begin() as con:
        insert_snapshot(con, run_record())
    audit = AuditTrail(engine)

    def worker(_: int) -> None:
        for i in range(20):
            audit.append(
                "b60-run",
                "memory.read",
                {"operation": "fixture", "count": i, "secret": "ignored"},
            )

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(worker, range(2)))
    with pytest.raises(RuntimeError):
        with engine.begin() as con:
            audit.append_in(con, "b60-run", "memory.read", {"count": 99})
            raise RuntimeError("rollback")
    events = audit.list("b60-run")
    assert [e.sequence_number for e in events] == list(range(1, 41))
    assert all(e.trace_id is None and "secret" not in e.payload for e in events)
    (tmp_path / "audit-concurrency-proof.json").write_text(
        json.dumps(
            {
                "events": [e.model_dump(mode="json") for e in events],
                "contiguous": True,
                "sessions": 2,
                "rollback_no_residue": True,
            },
            indent=2,
        )
    )


def test_memory_anchor_delete_rollback_and_api(
    isolated_db: tuple[Engine, Config], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine, _ = isolated_db
    store = MemoryStore(engine)
    memory = store.user_explicit("w", "u", "DO_NOT_AUDIT_DELETED_CONTENT")
    with engine.connect() as con:
        anchors = con.execute(select(schema.runs)).mappings().all()
    assert len(anchors) == 1 and anchors[0]["scenario_id"] is None
    anchor = anchors[0]["run_id"]
    assert anchors[0]["request_text"] == "memory control-plane audit anchor"
    original = AuditTrail.append_in

    def fail(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        raise RuntimeError("forced audit failure")

    with monkeypatch.context() as patch:
        patch.setattr(AuditTrail, "append_in", fail)
        with pytest.raises(RuntimeError):
            store.delete("w", "u", memory.memory_id)
    assert store.get("w", "u", memory.memory_id) == memory
    assert len(AuditTrail(engine).list(anchor)) == 1
    assert store.delete("w", "u", memory.memory_id)
    events = AuditTrail(engine).list(anchor)
    assert [e.event_type for e in events] == ["memory.created", "memory.deleted"]
    assert (
        "DO_NOT_AUDIT"
        not in canonical([e.model_dump(mode="json") for e in events]).decode()
    )
    await_setup = run_async(setup_checkpoints(engine.url))
    assert await_setup is None
    with engine.connect() as con:
        assert (
            con.scalar(
                text("SELECT count(*) FROM checkpoints WHERE thread_id=:id"),
                {"id": anchor},
            )
            == 0
        )
    with TestClient(create_app(engine)) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        assert client.get("/api/v1/runs/" + anchor).json()["scenario_id"] is None
        assert [
            e["sequence_number"]
            for e in client.get("/api/v1/runs/" + anchor + "/events").json()
        ] == [1, 2]
        assert client.get("/api/v1/runs/absent").status_code == 404
        assert client.get("/api/v1/runs/absent/events").status_code == 404
    empty = create_engine("sqlite://")
    try:
        with TestClient(create_app(empty)) as client:
            assert client.get("/readyz").status_code == 503
    finally:
        empty.dispose()
    unavailable = create_engine(
        "postgresql+psycopg://arr:fake@127.0.0.1:1/arr?connect_timeout=1"
    )
    try:
        with TestClient(create_app(unavailable)) as client:
            reply = client.get("/readyz")
            assert (
                reply.status_code == 503
                and "fake" not in reply.text
                and "postgresql" not in reply.text
            )
    finally:
        unavailable.dispose()
    (tmp_path / "memory-audit-proof.json").write_text(
        json.dumps(
            {
                "anchor": dict(anchors[0]),
                "events": [e.model_dump(mode="json") for e in events],
                "rollback_kept_memory": True,
                "successful_delete_absent": store.get("w", "u", memory.memory_id)
                is None,
                "anchor_checkpoint_count": 0,
                "api": {
                    "health": 200,
                    "ready": 200,
                    "unknown_run": 404,
                    "unknown_events": 404,
                    "unavailable": 503,
                    "missing_schema": 503,
                },
            },
            indent=2,
            default=str,
        )
    )


class ReportingProvider(ScriptedProvider):
    async def complete(self, request: ChatRequest) -> ChatResult:
        value = await super().complete(request)
        calls = []
        for call in value.tool_calls:
            args = dict(call.arguments)
            if call.name == "send_notification":
                args["message"] = "PRIVATE_SPAN_SENTINEL Bearer toolFixtureCredential"
            calls.append(
                ToolCall.model_validate(call.model_dump() | {"arguments": args})
            )
        return ChatResult.model_validate(
            value.model_dump()
            | {
                "usage": Usage(input_tokens=7, output_tokens=2).model_dump(),
                "tool_calls": [c.model_dump() for c in calls],
                "text": "PRIVATE_SPAN_SENTINEL Bearer modelFixtureCredential"
                if value.text
                else None,
            }
        )


def span_checker(spans: list[Any], events: list[Any]) -> None:
    assert set(REQUIRED_SPANS) <= {s.name for s in spans}
    index = {
        (f"{s.context.trace_id:032x}", f"{s.context.span_id:016x}"): s for s in spans
    }
    expected = {
        "run.started": "agent.run",
        "memory.created": "agent.memory.write",
        "memory.read": "agent.memory.read",
        "retrieval.completed": "agent.retrieval.search",
        "model.completed": "agent.model.call",
        "action.validated": "agent.action.validate",
        "policy.evaluated": "agent.policy.evaluate",
        "approval.waiting": "agent.approval.wait",
        "approval.resumed": "agent.approval.resume",
        "tool.completed": "agent.tool.call",
        "recovery.resumed": "agent.recovery.resume",
        "run.finalized": "agent.finalize",
    }
    for event in events:
        assert event.trace_id is not None and event.span_id is not None
        assert (event.trace_id, event.span_id) in index
        emitted = index[(event.trace_id, event.span_id)]
        assert emitted.name == expected[event.event_type]
        assert emitted.attributes["arr.run.id"] == event.run_id
    for span in spans:
        assert not any(
            "cost" in k
            or k
            in {
                "gen_ai.input.messages",
                "gen_ai.output.messages",
                "gen_ai.system_instructions",
                "gen_ai.tool.call.arguments",
                "gen_ai.tool.call.result",
                "gen_ai.retrieval.query.text",
            }
            for k in span.attributes
        )
        assert "PRIVATE_SPAN_SENTINEL" not in str(span.attributes)
    calls = [s for s in spans if s.name == "agent.model.call"]
    assert calls and all(
        s.attributes.get("gen_ai.usage.input_tokens") == 7
        and s.attributes.get("gen_ai.usage.output_tokens") == 2
        for s in calls
    )


def test_exact_spans_audit_correlation_and_replay(
    isolated_db: tuple[Engine, Config], tmp_path: Path
) -> None:
    engine, _ = isolated_db
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = Telemetry(provider.get_tracer("fixture"))

    async def exercise() -> None:
        await setup_checkpoints(engine.url)
        reset_demo(engine, confirm_development_reset=True)
        with engine.begin() as con:
            con.execute(
                schema.demo_services.update()
                .where(schema.demo_services.c.service_id == "checkout-api")
                .values(status="PRIVATE_SPAN_SENTINEL Bearer resultFixtureCredential")
            )
        await ingest(
            engine,
            Embeddings(),
            plan_source(
                "fixture/observability.md",
                b"# PRIVATE_SPAN_SENTINEL\nretrieval data sentinel",
            ),
        )
        MemoryStore(engine, telemetry=telemetry).user_explicit(
            "local", "test", "PRIVATE_SPAN_SENTINEL"
        )
        async with OpsDeskMCPClient(
            ROOT, engine.url.render_as_string(hide_password=False)
        ) as client:
            ctx = replace(
                context_for(engine, client, ReportingProvider("read_then_side")),
                telemetry=telemetry,
            )
            run = run_record().model_copy(
                update={
                    "scenario_id": "S02",
                    "request_text": "PRIVATE_SPAN_SENTINEL Bearer fakeCredential",
                }
            )
            async with open_runtime(ctx, engine.url) as runtime:
                state = await runtime.start(run)
                assert state["status"] == "WAITING_APPROVAL"
                ctx.gateway.approvals.decide(state["approval_id"], approved=True)
                final = await runtime.resume(run.run_id, "continue")
                assert final["status"] == "COMPLETED"
                await runtime.continue_run(run.run_id)

    run_async(exercise())
    with engine.connect() as con:
        anchors = (
            con.execute(
                select(schema.runs.c.run_id).where(
                    schema.runs.c.provider_id == "internal"
                )
            )
            .scalars()
            .all()
        )
    events = AuditTrail(engine).list("b60-run") + AuditTrail(engine).list(anchors[0])
    spans = list(exporter.get_finished_spans())
    span_checker(spans, events)
    with pytest.raises(AssertionError):
        span_checker([s for s in spans if s.name != "agent.finalize"], events)
    with pytest.raises(AssertionError):
        span_checker(spans, [events[0].model_copy(update={"span_id": "0" * 16})])
    span_checker(list(reversed(spans)), events)
    for bad in ("secret", "cost", "usage"):
        copied = [
            SimpleNamespace(
                name=s.name, context=s.context, attributes=dict(s.attributes or {})
            )
            for s in spans
        ]
        target = next(s for s in copied if s.name == "agent.model.call")
        if bad == "secret":
            target.attributes["gen_ai.input.messages"] = "PRIVATE_SPAN_SENTINEL"
        elif bad == "cost":
            target.attributes["arr.cost.usd"] = 1
        else:
            target.attributes.pop("gen_ai.usage.input_tokens")
        with pytest.raises(AssertionError):
            span_checker(copied, events)
    evidence = {
        "schema_version": "1.0",
        "git_sha": "a" * 40,
        "scenario_set_digest": "b" * 64,
        "lockfile_digests": {"uv": "c" * 64},
        "gates": {"fixture": "PASS"},
        "created_at": "fixture",
    }
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    export_replay(engine, "b60-run", evidence, "a" * 40, first)
    export_replay(engine, "b60-run", evidence, "a" * 40, second)
    assert first.read_bytes() == second.read_bytes()
    assert (
        first.with_suffix(".json.manifest.json").read_bytes()
        == second.with_suffix(".json.manifest.json").read_bytes()
    )
    locked_validate(__import__("json").loads(first.read_bytes()), "replay")
    assert b"fakeCredential" not in first.read_bytes()
    receipt_path = tmp_path / "fixture-receipt.json"
    receipt_path.write_text(json.dumps(evidence))
    cli_output = tmp_path / "cli.json"
    command = [
        sys.executable,
        "-m",
        "agent_reliability_runtime.cli",
        "export-replays",
        "--run-id",
        "b60-run",
        "--receipt",
        str(receipt_path),
        "--source-git-sha",
        "a" * 40,
        "--output",
        str(cli_output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True, cwd=ROOT)
    assert cli_output.read_bytes() == first.read_bytes()
    changed_receipt = tmp_path / "changed-receipt.json"
    export_replay(
        engine,
        "b60-run",
        evidence | {"created_at": "alternate"},
        "a" * 40,
        changed_receipt,
    )
    assert (
        json.loads(changed_receipt.read_bytes())["eval_receipt_digest"]
        != json.loads(first.read_bytes())["eval_receipt_digest"]
    )
    AuditTrail(engine).append(
        "b60-run", "memory.read", {"operation": "changed-audit", "count": 0}
    )
    changed_audit = tmp_path / "changed-audit.json"
    export_replay(engine, "b60-run", evidence, "a" * 40, changed_audit)
    assert changed_audit.read_bytes() != first.read_bytes()
    assert (
        json.loads(changed_audit.read_bytes())["eval_receipt_digest"]
        == json.loads(first.read_bytes())["eval_receipt_digest"]
    )
    for ident in ("absent",):
        with pytest.raises(ValueError):
            export_replay(
                engine, ident, evidence, "a" * 40, tmp_path / (ident + ".json")
            )
    with engine.begin() as con:
        insert_snapshot(
            con, run_record("nonterminal").model_copy(update={"scenario_id": "S01"})
        )
    with pytest.raises(ValueError):
        export_replay(
            engine, "nonterminal", evidence, "a" * 40, tmp_path / "nonterminal.json"
        )
    (tmp_path / "observability-proof.json").write_text(
        json.dumps(
            {
                "span_names": sorted({s.name for s in spans}),
                "spans": [
                    {
                        "name": s.name,
                        "trace_id": f"{s.context.trace_id:032x}",
                        "span_id": f"{s.context.span_id:016x}",
                        "attributes": dict(s.attributes or {}),
                    }
                    for s in spans
                ],
                "audit": [e.model_dump(mode="json") for e in events],
                "checker_negatives": [
                    "missing_span",
                    "wrong_correlation",
                    "content",
                    "cost",
                    "dropped_usage",
                ],
                "replay": json.loads(first.read_bytes()),
                "manifest": json.loads(
                    first.with_suffix(".json.manifest.json").read_bytes()
                ),
                "cli_equal": True,
            },
            indent=2,
        )
    )
    with pytest.raises(ValueError):
        export_replay(engine, anchors[0], evidence, "a" * 40, tmp_path / "anchor.json")
    with engine.begin() as con:
        con.execute(
            schema.audit_events.delete().where(
                schema.audit_events.c.run_id == "b60-run",
                schema.audit_events.c.sequence_number == 2,
            )
        )
    with pytest.raises(ValueError):
        export_replay(engine, "b60-run", evidence, "a" * 40, tmp_path / "gap.json")
    assert not (tmp_path / "gap.json").exists()
    provider.shutdown()
