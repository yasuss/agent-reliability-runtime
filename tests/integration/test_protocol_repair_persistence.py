"""Real persistence/stdio proof: correction does not execute or authorize."""

import json
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import JsonValue
from sqlalchemy import Engine, select

from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.providers.contracts import (
    ChatRequest,
    ChatResult,
    ToolCall,
)
from agent_reliability_runtime.retrieval.service import ingest
from agent_reliability_runtime.retrieval.text import plan_source
from agent_reliability_runtime.runtime.checkpoints import run_async, setup_checkpoints
from agent_reliability_runtime.runtime.prompt_context import parse_retrieval_context
from agent_reliability_runtime.runtime.service import open_runtime
from scripts.runtime_proof_support import Embeddings, context_for, counts, run_record

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("side", [False, True])
def test_pseudo_call_checkpoint_and_real_approval(
    isolated_db: tuple[Engine, Config], side: bool
) -> None:
    engine, _ = isolated_db

    class Provider:
        calls = 0

        async def complete(self, request: ChatRequest) -> ChatResult:
            self.calls += 1
            name = "send_notification" if side else "get_service_status"
            args: dict[str, JsonValue] = (
                {"channel": "demo", "message": "fictional protocol proof"}
                if side
                else {"service_id": "checkout-api"}
            )
            text: str | None = None
            calls: tuple[ToolCall, ...] = ()
            if self.calls == 1:
                text = json.dumps({"name": name, "arguments": args})
            elif self.calls == 2:
                before = counts(engine, "repair-pg-run")
                assert not before["approvals"] and not before["receipts"]
                assert before["notifications"] == before["run"]["tool_steps"] == 0
                assert request.messages[-1].content is not None
                assert "was not executed" in request.messages[-1].content
                calls = (ToolCall(call_id="normal-call", name=name, arguments=args),)
            else:
                text = "Fictional task completed."
            return ChatResult(
                provider_id="fixture",
                model_id="fixture",
                text=text,
                tool_calls=calls,
                finish_reason="tool_calls" if calls else "stop",
            )

    async def exercise() -> None:
        await setup_checkpoints(engine.url)
        reset_demo(engine, confirm_development_reset=True)
        await ingest(
            engine,
            Embeddings(),
            plan_source(
                "fixture/protocol.md", b"# Synthetic\ncheckout approval evidence"
            ),
        )
        async with OpsDeskMCPClient(
            ROOT, engine.url.render_as_string(hide_password=False)
        ) as client:
            provider = Provider()
            # Runtime provider is structural; the fixture helper's annotation is narrow.
            from agent_reliability_runtime.runtime.graph import Context

            original = context_for(engine, client)
            context = Context(
                engine=engine,
                provider=provider,
                embeddings=original.embeddings,
                tools=client.model_tools,
                gateway=original.gateway,
            )
            async with open_runtime(context, engine.url) as runtime:
                state = await runtime.start(run_record("repair-pg-run"))
                snapshot = await runtime.inspect("repair-pg-run")
                assert snapshot.values["protocol_repairs"] == 1
                assert all("citation_token" not in e for e in state["evidence"])
                projected = parse_retrieval_context(state["messages"][2]["content"])
                assert projected is not None
                assert all(
                    e["citation_token"] == f"[E{i}]" for i, e in enumerate(projected, 1)
                )
                if side:
                    assert state["status"] == "WAITING_APPROVAL"
                    assert state["model_steps"] == 2 and state["tool_steps"] == 0
                    assert snapshot.interrupts
                    before = counts(engine, "repair-pg-run")
                    assert len(before["approvals"]) == 1 and not before["receipts"]
                    assert before["notifications"] == 0
                    context.gateway.approvals.decide(
                        state["approval_id"], approved=True
                    )
            if side:
                async with open_runtime(context, engine.url) as reopened:
                    state = await reopened.resume("repair-pg-run", {"untrusted": True})
                    assert state["protocol_repairs"] == 1
            assert state["status"] == "COMPLETED" and state["model_steps"] == 3
            assert state["tool_steps"] == 1
            final = counts(engine, "repair-pg-run")
            assert final["notifications"] == int(side)
            assert len(final["receipts"]) == int(side)
            with engine.connect() as con:
                rows = (
                    con.execute(
                        select(schema.audit_events).where(
                            schema.audit_events.c.run_id == "repair-pg-run",
                            schema.audit_events.c.event_type == "model.protocol_repair",
                        )
                    )
                    .mappings()
                    .all()
                )
            assert len(rows) == 1
            assert rows[0]["payload"] == {
                "reason": "textual_tool_request",
                "repair_number": 1,
                "model_step": 1,
            }

    run_async(exercise())
