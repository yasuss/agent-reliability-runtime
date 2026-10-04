"""S08 note effect: actual owned child termination before node checkpoint."""

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, select

from agent_reliability_runtime.contracts.domain import Run
from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.evals.execution import (
    FixtureEmbeddings,
    MeasuredTransport,
    ObservedGateway,
    ScriptedScenarioProvider,
    head,
)
from agent_reliability_runtime.evals.scenarios import ROOT, load_scenarios
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.policy import Action
from agent_reliability_runtime.runtime.checkpoints import run_async
from agent_reliability_runtime.runtime.graph import Context, State
from agent_reliability_runtime.runtime.service import open_runtime


def definition() -> Any:
    return next(s for s in load_scenarios()[0] if s.id.startswith("S08"))


async def kill_note(
    engine: Engine, run: Run, key: str, directory: Path
) -> tuple[State, list[Action], dict[str, int], dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=False)
    async with OpsDeskMCPClient(
        ROOT, engine.url.render_as_string(hide_password=False)
    ) as client:
        gateway = ObservedGateway(
            engine, MeasuredTransport(client, run.scenario_id or "")
        )
        context = Context(
            engine=engine,
            provider=ScriptedScenarioProvider(definition()),
            embeddings=FixtureEmbeddings(),
            tools=client.model_tools,
            gateway=gateway,
            key_factory=lambda: key,
        )
        async with open_runtime(context, engine.url) as runtime:
            paused = await runtime.start(run)
            assert paused["status"] == "WAITING_APPROVAL"
            action = Action.model_validate(paused["action"])
            gateway.approvals.decide(str(paused["approval_id"]), approved=True)
    marker, child_output = directory / "marker.json", directory / "child.json"
    counter = directory / "physical-calls.jsonl"
    env = os.environ.copy()
    env["ARR_DATABASE_URL"] = engine.url.render_as_string(hide_password=False)

    def command(mode: str) -> list[str]:
        return [
            sys.executable,
            "-m",
            "agent_reliability_runtime.evals.process_proof",
            "--mode",
            mode,
            "--run-id",
            run.run_id,
            "--directory",
            str(directory),
        ]

    with (
        (directory / "a.stdout").open("wb") as out,
        (directory / "a.stderr").open("wb") as err,
    ):
        a = subprocess.Popen(
            command("resume"), cwd=ROOT, env=env, stdout=out, stderr=err
        )
        try:
            deadline = time.monotonic() + 45
            while not marker.exists():
                if a.poll() is not None:
                    raise AssertionError(
                        "note child exited before kill point; retained a.stderr"
                    )
                if time.monotonic() > deadline:
                    raise TimeoutError("note kill point deadline")
                await asyncio.sleep(0.05)
            observed = json.loads(marker.read_text())
            assert observed["pid"] == a.pid or observed["parent_pid"] == a.pid
            assert observed["phase"] == "after_effect_commit_before_node_checkpoint"
            with engine.connect() as con:
                pre_receipts = (
                    con.execute(
                        select(schema.effect_receipts).where(
                            schema.effect_receipts.c.run_id == run.run_id
                        )
                    )
                    .mappings()
                    .all()
                )
                assert (
                    len(pre_receipts) == 1
                    and pre_receipts[0]["receipt_id"] == observed["receipt_id"]
                )
                assert (
                    con.scalar(
                        select(schema.approvals.c.status).where(
                            schema.approvals.c.approval_id == paused["approval_id"]
                        )
                    )
                    == "CONSUMED"
                )
                assert (
                    con.scalar(
                        select(schema.demo_incident_notes.c.incident_id).where(
                            schema.demo_incident_notes.c.note_id
                            == observed["receipt_id"]
                        )
                    )
                    == "INC-1006"
                )
            async with OpsDeskMCPClient(ROOT, env["ARR_DATABASE_URL"]) as client:
                async with open_runtime(
                    Context(
                        engine=engine,
                        provider=ScriptedScenarioProvider(definition()),
                        embeddings=FixtureEmbeddings(),
                        tools=client.model_tools,
                        gateway=ObservedGateway(
                            engine, MeasuredTransport(client, run.scenario_id or "")
                        ),
                    ),
                    engine.url,
                ) as runtime:
                    checkpoint = await runtime.inspect(run.run_id)
                    assert (
                        checkpoint.next == ("execute_tool",)
                        and checkpoint.values["tool_steps"] == 0
                    )
            assert len(counter.read_text().splitlines()) == 1
            os.kill(observed["pid"], signal.SIGTERM)
            exit_a = await asyncio.to_thread(a.wait, timeout=10)
            assert exit_a != 0
        finally:
            if a.poll() is None:
                a.kill()
                await asyncio.to_thread(a.wait, timeout=10)
    with (
        (directory / "b.stdout").open("wb") as out,
        (directory / "b.stderr").open("wb") as err,
    ):
        b = subprocess.Popen(
            command("continue"), cwd=ROOT, env=env, stdout=out, stderr=err
        )
        try:
            exit_b = await asyncio.to_thread(b.wait, timeout=45)
        finally:
            if b.poll() is None:
                b.kill()
                await asyncio.to_thread(b.wait, timeout=10)
    assert exit_b == 0, "note child B failed; retained b.stderr"
    restarted = json.loads(child_output.read_text())
    assert restarted["pid"] != observed["pid"]
    assert restarted["run_id"] == restarted["thread_id"] == run.run_id
    assert (
        restarted["before_checkpoint"]
        == checkpoint.config["configurable"]["checkpoint_id"]
    )
    state = restarted["state"]
    assert state["status"] == "COMPLETED" and state["tool_steps"] == 1
    assert any(
        json.loads(m["content"]).get("replayed")
        for m in state["messages"]
        if m["role"] == "tool"
    )
    calls: dict[str, int] = {}
    for line in counter.read_text().splitlines():
        row = json.loads(line)
        assert row["run_id"] == run.run_id
        calls[row["identity"]] = calls.get(row["identity"], 0) + 1
    assert sum(calls.values()) == 1
    proof = {
        "child_a_pid": observed["pid"],
        "child_a_launcher_pid": a.pid,
        "child_a_exit": exit_a,
        "child_b_pid": restarted["pid"],
        "child_b_launcher_pid": b.pid,
        "child_b_exit": exit_b,
        "checkpoint_before": restarted["before_checkpoint"],
        "checkpoint_after": restarted["after_checkpoint"],
        "physical_calls": calls,
        "server": restarted["server"],
        "protocol": restarted["protocol"],
        "kill_phase": observed["phase"],
        "pre_kill_receipt_count": len(pre_receipts),
        "pre_kill_note_incident_id": "INC-1006",
    }
    return state, [action], calls, proof


async def child(args: argparse.Namespace) -> None:
    engine = create_engine(database_url())

    async def stop(state: State, result: dict[str, Any]) -> None:
        marker = {
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "subject_sha": head(),
            "phase": "after_effect_commit_before_node_checkpoint",
            "run_id": state["run_id"],
            "receipt_id": result["receipt_id"],
        }
        temporary = args.directory / "marker.tmp"
        temporary.write_text(json.dumps(marker))
        temporary.replace(args.directory / "marker.json")
        await asyncio.Event().wait()

    try:
        async with OpsDeskMCPClient(
            ROOT, engine.url.render_as_string(hide_password=False)
        ) as client:
            transport = MeasuredTransport(
                client,
                "S08_PROCESS_KILL_RESUME",
                counter_path=args.directory / "physical-calls.jsonl",
            )
            ctx = Context(
                engine=engine,
                provider=ScriptedScenarioProvider(definition()),
                embeddings=FixtureEmbeddings(),
                tools=client.model_tools,
                gateway=ObservedGateway(engine, transport),
                fault_hook=stop if args.mode == "resume" else None,
            )
            async with open_runtime(ctx, engine.url) as runtime:
                before = await runtime.inspect(args.run_id)
                state = (
                    await runtime.resume(args.run_id, "continue")
                    if args.mode == "resume"
                    else await runtime.continue_run(args.run_id)
                )
                after = await runtime.inspect(args.run_id)
                result = {
                    "pid": os.getpid(),
                    "parent_pid": os.getppid(),
                    "run_id": args.run_id,
                    "thread_id": after.config["configurable"]["thread_id"],
                    "state": state,
                    "before_checkpoint": before.config["configurable"]["checkpoint_id"],
                    "after_checkpoint": after.config["configurable"]["checkpoint_id"],
                    "server": client.server_info,
                    "protocol": client.protocol_version,
                }
                (args.directory / "child.json").write_text(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["resume", "continue"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    run_async(child(parser.parse_args()))
