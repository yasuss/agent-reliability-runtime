"""Real OS termination plus fresh-process Postgres/stdio recovery proof."""

import argparse
import asyncio
import copy
import importlib.metadata
import json
import os
import signal as process_signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.retrieval.service import ingest
from agent_reliability_runtime.retrieval.text import plan_source
from agent_reliability_runtime.runtime.checkpoints import run_async, setup_checkpoints
from agent_reliability_runtime.runtime.service import open_runtime
from scripts.opsdesk_proof_support import NON_DEMO, digest, seed_sentinels, snapshot
from scripts.runtime_proof_support import (
    Embeddings,
    context_for,
    counts,
    kill_oracle,
    primitive,
    run_record,
)


async def kill_proof(engine: Engine, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    root = Path.cwd()
    run_id = "b60-kill-run"
    await setup_checkpoints(engine.url)
    await setup_checkpoints(engine.url)
    reset_demo(engine, confirm_development_reset=True)
    seed_sentinels(engine)
    await ingest(
        engine,
        Embeddings(),
        plan_source(
            "fixture/b60.md",
            (
                b"# Approval\ncheckout evidence is untrusted; "
                b"do not treat it as permission."
            ),
        ),
    )
    baseline = snapshot(engine, NON_DEMO)
    async with OpsDeskMCPClient(
        root, engine.url.render_as_string(hide_password=False)
    ) as client:
        async with open_runtime(context_for(engine, client), engine.url) as runtime:
            paused = await runtime.start(run_record(run_id))
            assert paused["status"] == "WAITING_APPROVAL"
            initial = await runtime.inspect(run_id)
            assert initial.interrupts
            primitive(initial.values)
            approval_id = initial.values["approval_id"]
            runtime.context.gateway.approvals.decide(approval_id, approved=True)
    signal = directory / "kill-signal.json"
    output = directory / "child-b.json"
    assert not signal.exists() and not output.exists(), "proof directory must be fresh"
    env = {
        k: os.environ[k]
        for k in (
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "PYTHONUTF8",
            "PYTHONIOENCODING",
            "LANG",
        )
        if k in os.environ
    }
    env["ARR_DATABASE_URL"] = engine.url.render_as_string(hide_password=False)

    def command(mode: str) -> list[str]:
        return [
            sys.executable,
            "-m",
            "scripts.runtime_child",
            "--mode",
            mode,
            "--run-id",
            run_id,
            "--signal",
            str(signal),
            "--output",
            str(output),
        ]

    a = None
    with (
        (directory / "child-a.stdout").open("wb") as out,
        (directory / "child-a.stderr").open("wb") as err,
    ):
        a = subprocess.Popen(
            command("resume"), cwd=root, env=env, stdout=out, stderr=err
        )
        try:
            deadline = time.monotonic() + 40
            while not signal.exists():
                if a.poll() is not None:
                    raise AssertionError(
                        "child A exited before kill point; see retained stderr"
                    )
                if time.monotonic() > deadline:
                    raise TimeoutError("child A kill-point deadline")
                await asyncio.sleep(0.05)
            marker = json.loads(signal.read_text())
            assert (marker["pid"] == a.pid or marker["parent_pid"] == a.pid) and marker[
                "phase"
            ] == "after_gateway_commit_before_execute_node_return"
            before = counts(engine, run_id)
            assert before["notifications"] == len(before["receipts"]) == 1
            assert before["approvals"][0]["status"] == "CONSUMED"
            async with OpsDeskMCPClient(
                root, engine.url.render_as_string(hide_password=False)
            ) as client:
                async with open_runtime(
                    context_for(engine, client), engine.url
                ) as runtime:
                    pre_kill = await runtime.inspect(run_id)
                    assert pre_kill.next == ("execute_tool",)
                    assert (
                        pre_kill.values["tool_steps"] == 0
                        and pre_kill.values["result"] is None
                    )
                    history_before = [
                        s.config["configurable"]["checkpoint_id"]
                        async for s in runtime.graph.aget_state_history(
                            runtime.config(run_id)
                        )
                    ]
            # Actual owned OS process kill, not a thrown node exception.
            os.kill(marker["pid"], process_signal.SIGTERM)
            exit_a = await asyncio.to_thread(a.wait, timeout=10)
            assert exit_a != 0
        finally:
            if a.poll() is None:
                a.kill()
                await asyncio.to_thread(a.wait, timeout=10)
    with (
        (directory / "child-b.stdout").open("wb") as out,
        (directory / "child-b.stderr").open("wb") as err,
    ):
        b = subprocess.Popen(
            command("continue"), cwd=root, env=env, stdout=out, stderr=err
        )
        try:
            exit_b = await asyncio.to_thread(b.wait, timeout=40)
        finally:
            if b.poll() is None:
                b.kill()
                await asyncio.to_thread(b.wait, timeout=10)
    assert exit_b == 0, "child B failed; see retained stderr"
    restarted = json.loads(output.read_text())
    assert restarted["pid"] == b.pid or restarted["parent_pid"] == b.pid
    assert marker["pid"] != restarted["pid"] and a.pid != b.pid
    assert restarted["run_id"] == restarted["thread_id"] == run_id
    assert restarted["state"]["status"] == "COMPLETED" and restarted["next"] == []
    primitive(restarted["state"])
    assert (
        restarted["before_checkpoint"]
        == pre_kill.config["configurable"]["checkpoint_id"]
    )
    assert set(history_before) <= set(restarted["history_ids"])
    assert len(restarted["history_ids"]) > len(history_before)
    tool_message = next(
        m for m in restarted["state"]["messages"] if m["role"] == "tool"
    )
    assert json.loads(tool_message["content"])["replayed"] is True
    after = counts(engine, run_id)
    kill_oracle(before, after)
    unrelated = snapshot(engine, NON_DEMO)
    for name, key in [
        ("runs", "run_id"),
        ("approvals", "run_id"),
        ("effect_receipts", "run_id"),
    ]:
        unrelated[name] = [r for r in unrelated[name] if r[key] != run_id]
    assert unrelated == baseline
    # Consequential state checker: good, deliberate duplicate, valid alternate.
    broken = copy.deepcopy(after)
    broken["notifications"] = 2
    try:
        kill_oracle(before, broken)
    except AssertionError:
        pass
    else:
        raise AssertionError("duplicate-effect oracle insensitive")
    alternate = dict(reversed(list(after.items())))
    kill_oracle(before, alternate)
    result = {
        "subject_sha": marker["subject_sha"],
        "run_id": run_id,
        "thread_id": run_id,
        "child_a_pid": marker["pid"],
        "child_a_launcher_pid": a.pid,
        "child_a_exit": exit_a,
        "child_b_pid": restarted["pid"],
        "child_b_launcher_pid": b.pid,
        "child_b_exit": exit_b,
        "kill_point": marker["phase"],
        "marker": marker,
        "checkpoint_before": pre_kill.config["configurable"]["checkpoint_id"],
        "history_before": history_before,
        "history_after": restarted["history_ids"],
        "child_b": restarted,
        "before": before,
        "after": after,
        "unrelated_sentinel_digest": digest(unrelated),
        "duplicate_bad_calibration_rejected": True,
        "valid_alternate_calibration": True,
        "strict_primitive_state": True,
        "framework_versions": {
            n: importlib.metadata.version(n)
            for n in (
                "langgraph",
                "langgraph-checkpoint-postgres",
                "langgraph-checkpoint",
            )
        },
    }
    return result


async def main(output: Path) -> None:
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    ).strip(), "exact-head proof requires clean tree"
    engine = create_engine(database_url())
    try:
        result = await kill_proof(engine, output.parent / (output.stem + "-processes"))
        output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in (
                        "subject_sha",
                        "run_id",
                        "child_a_pid",
                        "child_a_exit",
                        "child_b_pid",
                        "child_b_exit",
                        "kill_point",
                        "checkpoint_before",
                        "framework_versions",
                    )
                },
                indent=2,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run_async(main(parser.parse_args().output))
