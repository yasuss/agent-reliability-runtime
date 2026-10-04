"""Fresh process worker for controlled B60 acceptance; never a production CLI."""

import argparse
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.runtime.checkpoints import run_async
from agent_reliability_runtime.runtime.graph import State
from agent_reliability_runtime.runtime.service import open_runtime
from scripts.runtime_proof_support import context_for, primitive


async def work(args: argparse.Namespace) -> None:
    engine = create_engine(database_url())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    async def stop(state: State, result: dict[str, Any]) -> None:
        temporary = args.signal.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "parent_pid": os.getppid(),
                    "subject_sha": head,
                    "phase": "after_gateway_commit_before_execute_node_return",
                    "run_id": state["run_id"],
                    "result": result,
                }
            ),
            encoding="utf-8",
        )
        temporary.replace(args.signal)
        await asyncio.Event().wait()

    try:
        async with OpsDeskMCPClient(
            Path.cwd(), database_url().render_as_string(hide_password=False)
        ) as client:
            context = context_for(
                engine, client, fault_hook=stop if args.mode == "resume" else None
            )
            async with open_runtime(context) as runtime:
                before = await runtime.inspect(args.run_id)
                state = (
                    await runtime.resume(args.run_id, {"caller": "resume only"})
                    if args.mode == "resume"
                    else await runtime.continue_run(args.run_id)
                )
                primitive(state)
                after = await runtime.inspect(args.run_id)
                history = [
                    s
                    async for s in runtime.graph.aget_state_history(
                        runtime.config(args.run_id)
                    )
                ]
                result = {
                    "pid": os.getpid(),
                    "parent_pid": os.getppid(),
                    "subject_sha": head,
                    "run_id": args.run_id,
                    "thread_id": after.config["configurable"]["thread_id"],
                    "state": state,
                    "next": list(after.next),
                    "before_checkpoint": before.config["configurable"]["checkpoint_id"],
                    "after_checkpoint": after.config["configurable"]["checkpoint_id"],
                    "history_ids": [
                        s.config["configurable"]["checkpoint_id"] for s in history
                    ],
                    "server": client.server_info,
                    "protocol": client.protocol_version,
                    "checkpointer": "AsyncPostgresSaver",
                    "durability": "sync",
                }
                args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["resume", "continue"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--signal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run_async(work(parser.parse_args()))
