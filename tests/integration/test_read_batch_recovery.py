"""Real stdio/Postgres queue durability at two actual process kill points."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.retrieval.service import ingest
from agent_reliability_runtime.retrieval.text import plan_source
from agent_reliability_runtime.runtime.checkpoints import run_async, setup_checkpoints
from agent_reliability_runtime.runtime.service import open_runtime
from scripts.runtime_proof_support import Embeddings, context_for, counts, primitive

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("phase", [1, 2])
def test_actual_multi_read_kill_and_fresh_restart(
    isolated_db: tuple[Engine, Config], tmp_path: Path, phase: int
) -> None:
    engine, _ = isolated_db

    async def exercise() -> None:
        await setup_checkpoints(engine.url)
        reset_demo(engine, confirm_development_reset=True)
        await ingest(
            engine,
            Embeddings(),
            plan_source("fixture/batch.md", b"# Synthetic\ncheckout approval evidence"),
        )
        marker = tmp_path / "signal.json"
        output = tmp_path / "continued.json"
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
            )
            if k in os.environ
        }
        env["ARR_DATABASE_URL"] = engine.url.render_as_string(hide_password=False)

        def command(mode: str) -> list[str]:
            return [
                sys.executable,
                "-m",
                "scripts.read_batch_child",
                "--mode",
                mode,
                "--phase",
                str(phase),
                "--signal",
                str(marker),
                "--output",
                str(output),
            ]

        with (
            (tmp_path / "first.stdout").open("wb") as out,
            (tmp_path / "first.stderr").open("wb") as err,
        ):
            first = subprocess.Popen(
                command("pause"), cwd=ROOT, env=env, stdout=out, stderr=err
            )
            try:
                deadline = time.monotonic() + 40
                while not marker.exists():
                    assert first.poll() is None, "child exited before queue kill point"
                    if time.monotonic() > deadline:
                        raise TimeoutError("queue kill point timeout")
                    await asyncio.sleep(0.05)
                signal_data = json.loads(marker.read_bytes())
                assert (
                    signal_data["pid"] == first.pid
                    or signal_data["parent_pid"] == first.pid
                )
                async with OpsDeskMCPClient(
                    ROOT, engine.url.render_as_string(hide_password=False)
                ) as client:
                    async with open_runtime(
                        context_for(engine, client), engine.url
                    ) as runtime:
                        before = await runtime.inspect("batch-restart-run")
                        primitive(before.values)
                assert (
                    before.values["model_steps"] == 1
                    and before.values["tool_steps"] == phase
                )
                assert (
                    len([m for m in before.values["messages"] if m["role"] == "tool"])
                    == phase
                )
                assert before.next == (("execute_tool",) if phase == 1 else ("decide",))
                if phase == 1:
                    assert before.values["proposed_call"]["call_id"] == "batch-service"
                os.kill(signal_data["pid"], signal.SIGTERM)
                exit_first = await asyncio.to_thread(first.wait, timeout=10)
                assert exit_first != 0
            finally:
                if first.poll() is None:
                    first.kill()
                    await asyncio.to_thread(first.wait, timeout=10)
        with (
            (tmp_path / "next.stdout").open("wb") as out,
            (tmp_path / "next.stderr").open("wb") as err,
        ):
            second = subprocess.Popen(
                command("continue"), cwd=ROOT, env=env, stdout=out, stderr=err
            )
            try:
                exit_second = await asyncio.to_thread(second.wait, timeout=40)
            finally:
                if second.poll() is None:
                    second.kill()
                    await asyncio.to_thread(second.wait, timeout=10)
        assert exit_second == 0, "fresh child failed; see retained stderr"
        proof = json.loads(output.read_bytes())
        state = proof["state"]
        assert first.pid != second.pid
        assert proof["pid"] == second.pid or proof["parent_pid"] == second.pid
        assert signal_data["pid"] != proof["pid"]
        assert (
            proof["before_checkpoint"] == before.config["configurable"]["checkpoint_id"]
        )
        assert (
            proof["after_checkpoint"] != proof["before_checkpoint"]
            and proof["next"] == []
        )
        assert (
            state["status"] == "COMPLETED"
            and state["model_steps"] == state["tool_steps"] == 2
        )
        assert state["pending_calls"] == []
        tool_messages = [m for m in state["messages"] if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tool_messages] == [
            "batch-incident",
            "batch-service",
        ]
        assistant = [m for m in state["messages"] if m["role"] == "assistant"]
        assert len(assistant) == 1 and len(assistant[0]["tool_calls"]) == 2
        assert "[evidence:" in state["final_text"] and "[E1]" not in state["final_text"]
        counters = counts(engine, "batch-restart-run")
        assert (
            not counters["approvals"]
            and not counters["receipts"]
            and counters["notifications"] == 0
        )
        (tmp_path / "proof.json").write_text(
            json.dumps(
                dict(
                    child_a_pid=first.pid,
                    child_b_pid=second.pid,
                    phase=phase,
                    checkpoint_before=before.config,
                    checkpoint_after=proof,
                    counts=counters,
                ),
                default=str,
                indent=2,
            ),
            encoding="utf-8",
        )

    run_async(exercise())
