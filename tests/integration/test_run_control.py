"""Remaining local control surfaces share exact durable approval authority."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic.config import Config
from sqlalchemy import Engine

from agent_reliability_runtime.api import create_app
from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.evals.execution import (
    FixtureEmbeddings,
    ScriptedScenarioProvider,
    prepare_knowledge,
)
from agent_reliability_runtime.evals.scenarios import ROOT, load_scenarios
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.policy import Gateway
from agent_reliability_runtime.providers.contracts import ChatRequest, ChatResult
from agent_reliability_runtime.runtime.checkpoints import run_async, setup_checkpoints
from agent_reliability_runtime.runtime.graph import Context
from agent_reliability_runtime.runtime.service import open_runtime

pytestmark = pytest.mark.integration


class APIProvider(ScriptedScenarioProvider):
    async def complete(self, request: ChatRequest) -> ChatResult:
        result = await super().complete(request)
        return ChatResult.model_validate(
            result.model_dump()
            | {"provider_id": "ollama-local", "model_id": "qwen3:4b"}
        )


def test_graph_foreign_citation_fails_closed(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db

    class ForeignProvider(APIProvider):
        async def complete(self, request: ChatRequest) -> ChatResult:
            return ChatResult(
                text="Foreign [evidence:" + "0" * 64 + "]",
                finish_reason="stop",
                provider_id="ollama-local",
                model_id="qwen3:4b",
            )

    async def exercise() -> None:
        from agent_reliability_runtime.runtime.local import RunRequest

        await setup_checkpoints(engine.url)
        await prepare_knowledge(engine, FixtureEmbeddings())
        definition = load_scenarios()[0][0]
        run = RunRequest(
            workspace_id="citation", user_id="operator", scenario_id=definition.id
        ).run()
        async with OpsDeskMCPClient(
            ROOT, engine.url.render_as_string(hide_password=False)
        ) as client:
            context = Context(
                engine=engine,
                provider=ForeignProvider(definition),
                embeddings=FixtureEmbeddings(),
                tools=client.model_tools,
                gateway=Gateway(engine, client),
            )
            async with open_runtime(context, engine.url) as runtime:
                state = await runtime.start(run)
            assert state["status"] == "FAILED"
            assert state["terminal_reason"] == "citation outside retrieved evidence"
            assert state["tool_steps"] == 0

    run_async(exercise())


def test_ambiguous_write_reconciles_without_retry(
    isolated_db: tuple[Engine, Config],
) -> None:
    from agent_reliability_runtime.evals.execution import MeasuredTransport
    from agent_reliability_runtime.mcp.client import OpsDeskError
    from agent_reliability_runtime.mcp.contracts import ReceiptEnvelope
    from agent_reliability_runtime.policy import Action
    from agent_reliability_runtime.runtime.local import RunRequest

    engine, _ = isolated_db

    class LostReply(MeasuredTransport):
        async def _dispatch_effect(self, action: Action) -> ReceiptEnvelope:
            await super()._dispatch_effect(action)
            raise OpsDeskError("evaluation lost response after commit")

    async def exercise() -> None:
        await setup_checkpoints(engine.url)
        reset_demo(engine, confirm_development_reset=True)
        await prepare_knowledge(engine, FixtureEmbeddings())
        definition = load_scenarios()[0][8]
        run = RunRequest(
            workspace_id="ambiguous", user_id="operator", scenario_id=definition.id
        ).run()
        async with OpsDeskMCPClient(
            ROOT, engine.url.render_as_string(hide_password=False)
        ) as client:
            transport = LostReply(client, definition.id)
            ctx = Context(
                engine=engine,
                provider=APIProvider(definition),
                embeddings=FixtureEmbeddings(),
                tools=client.model_tools,
                gateway=Gateway(engine, transport),
            )
            async with open_runtime(ctx, engine.url) as runtime:
                state = await runtime.start(run)
                ctx.gateway.approvals.decide(str(state["approval_id"]), approved=True)
                with pytest.raises(OpsDeskError):
                    await runtime.resume(run.run_id, "continue")
                assert sum(transport.physical_calls.values()) == 1
                checkpoint = await runtime.inspect(run.run_id)
                assert checkpoint.next == ("execute_tool",)
                recovered = await runtime.continue_run(run.run_id)
                assert recovered["status"] == "COMPLETED"
                assert sum(transport.physical_calls.values()) == 1
                assert recovered["tool_steps"] == 1
                assert any(
                    '"replayed": true' in str(m.get("content"))
                    for m in recovered["messages"]
                    if m["role"] == "tool"
                )

    run_async(exercise())


def test_post_run_approval_and_cli(
    isolated_db: tuple[Engine, Config],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine, _ = isolated_db
    definition = next(s for s in load_scenarios()[0] if s.id.startswith("S09"))

    @asynccontextmanager
    async def factory(selected: Engine) -> Any:
        async with OpsDeskMCPClient(
            ROOT, selected.url.render_as_string(hide_password=False)
        ) as client:
            ctx = Context(
                engine=selected,
                provider=APIProvider(definition),
                embeddings=FixtureEmbeddings(),
                tools=client.model_tools,
                gateway=Gateway(selected, client),
            )
            async with open_runtime(ctx, selected.url) as runtime:
                yield runtime

    async def exercise() -> None:
        await setup_checkpoints(engine.url)
        reset_demo(engine, confirm_development_reset=True)
        await prepare_knowledge(engine, FixtureEmbeddings())
        app = create_app(engine, runtime_factory=factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            for body in [
                {"workspace_id": "w", "user_id": "u"},
                {
                    "workspace_id": "w",
                    "user_id": "u",
                    "task": "x",
                    "scenario_id": definition.id,
                },
                {"workspace_id": "w", "user_id": "u", "task": "x", "approved": True},
            ]:
                assert (await client.post("/api/v1/runs", json=body)).status_code == 422
            created = await client.post(
                "/api/v1/runs",
                json={
                    "workspace_id": "w",
                    "user_id": "u",
                    "scenario_id": definition.id,
                },
            )
            assert created.status_code == 200, created.text
            run = created.json()
            assert (
                run["status"] == "WAITING_APPROVAL"
                and run["request_text"] == definition.input["task"]
            )
            events = (
                await client.get("/api/v1/runs/" + run["run_id"] + "/events")
            ).json()
            approval_id = next(
                e["payload"]["approval_id"]
                for e in events
                if e["event_type"] == "approval.waiting"
            )
            wrong = await client.post(
                "/api/v1/runs/wrong/approvals/" + approval_id,
                json={"decision": "APPROVE"},
            )
            assert wrong.status_code == 404
            forged = await client.post(
                "/api/v1/runs/" + run["run_id"] + "/approvals/" + approval_id,
                json={"decision": "APPROVE", "action_digest": "forged"},
            )
            assert forged.status_code == 422
            approved = await client.post(
                "/api/v1/runs/" + run["run_id"] + "/approvals/" + approval_id,
                json={"decision": "APPROVE"},
            )
            assert (
                approved.status_code == 200 and approved.json()["status"] == "COMPLETED"
            )
            repeated = await client.post(
                "/api/v1/runs/" + run["run_id"] + "/approvals/" + approval_id,
                json={"decision": "APPROVE"},
            )
            assert repeated.status_code == 409
            rejected_run = (
                await client.post(
                    "/api/v1/runs",
                    json={
                        "workspace_id": "w",
                        "user_id": "u",
                        "task": "Fictional notification",
                    },
                )
            ).json()
            async with factory(engine) as runtime:
                snap = await runtime.inspect(rejected_run["run_id"])
                rejected_id = snap.values["approval_id"]
            rejected = await client.post(
                "/api/v1/runs/" + rejected_run["run_id"] + "/approvals/" + rejected_id,
                json={"decision": "REJECT"},
            )
            assert rejected.json()["status"] == "REJECTED"
        (tmp_path / "api-proof.json").write_text(
            __import__("json").dumps(
                {
                    "created": run,
                    "approved": approved.json(),
                    "rejected": rejected.json(),
                    "wrong_run_status": wrong.status_code,
                    "forged_status": forged.status_code,
                }
            )
        )

    run_async(exercise())
    from agent_reliability_runtime import cli

    monkeypatch.setattr(cli, "create_engine", lambda *a: engine)
    monkeypatch.setattr(
        "agent_reliability_runtime.runtime.local.local_runtime", factory
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "arr",
            "run",
            "--scenario",
            definition.id,
            "--workspace-id",
            "cli",
            "--user-id",
            "operator",
        ],
    )
    cli.main()
    assert "WAITING_APPROVAL" in capsys.readouterr().out
