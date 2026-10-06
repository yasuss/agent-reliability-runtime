"""Fresh-process multi-read checkpoint worker, used only by verification."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import create_engine

from agent_reliability_runtime.contracts.domain import Record
from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.policy import Action, Gateway
from agent_reliability_runtime.providers.contracts import (
    ChatRequest,
    ChatResult,
    ToolCall,
)
from agent_reliability_runtime.runtime.checkpoints import run_async
from agent_reliability_runtime.runtime.graph import Context
from agent_reliability_runtime.runtime.service import open_runtime
from scripts.runtime_proof_support import Embeddings, primitive, run_record


async def work(args: argparse.Namespace) -> None:
    async def pause(phase: str) -> None:
        temporary = args.signal.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(dict(pid=os.getpid(), parent_pid=os.getppid(), phase=phase)),
            encoding="utf-8",
        )
        temporary.replace(args.signal)
        await asyncio.Event().wait()

    class Provider:
        async def complete(self, request: ChatRequest) -> ChatResult:
            observations = [m for m in request.messages if m.role == "tool"]
            if not observations:
                return ChatResult(
                    provider_id="fixture",
                    model_id="fixture",
                    finish_reason="tool_calls",
                    text=None,
                    tool_calls=(
                        ToolCall(
                            call_id="batch-incident",
                            name="get_incident",
                            arguments={"incident_id": "INC-1001"},
                        ),
                        ToolCall(
                            call_id="batch-service",
                            name="get_service_status",
                            arguments={"service_id": "checkout-api"},
                        ),
                    ),
                )
            assert [m.tool_call_id for m in observations] == [
                "batch-incident",
                "batch-service",
            ]
            if args.mode == "pause" and args.phase == 2:
                await pause("after_second_read_before_model_decision")
            return ChatResult(
                provider_id="fixture",
                model_id="fixture",
                finish_reason="stop",
                text="Current incident and service inspected. [E1]",
            )

    class PausingGateway(Gateway):
        async def execute(
            self, action: Action, approval_id: str | None = None
        ) -> Record:
            if (
                args.mode == "pause"
                and args.phase == 1
                and action.tool_name == "get_service_status"
            ):
                await pause("after_first_read_before_second_read")
            return await super().execute(action, approval_id)

    engine = create_engine(database_url())
    try:
        async with OpsDeskMCPClient(
            Path.cwd(), engine.url.render_as_string(hide_password=False)
        ) as client:
            context = Context(
                engine=engine,
                provider=Provider(),
                embeddings=Embeddings(),
                tools=client.model_tools,
                gateway=PausingGateway(engine, client),
            )
            async with open_runtime(context, engine.url) as runtime:
                before = (
                    await runtime.inspect("batch-restart-run")
                    if args.mode == "continue"
                    else None
                )
                state = (
                    await runtime.continue_run("batch-restart-run")
                    if args.mode == "continue"
                    else await runtime.start(run_record("batch-restart-run"))
                )
                after = await runtime.inspect("batch-restart-run")
                primitive(state)
                args.output.write_text(
                    json.dumps(
                        dict(
                            pid=os.getpid(),
                            parent_pid=os.getppid(),
                            state=state,
                            next=list(after.next),
                            before_checkpoint=before.config["configurable"][
                                "checkpoint_id"
                            ]
                            if before
                            else None,
                            after_checkpoint=after.config["configurable"][
                                "checkpoint_id"
                            ],
                            server=client.server_info,
                            protocol=client.protocol_version,
                        )
                    ),
                    encoding="utf-8",
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pause", "continue"], required=True)
    parser.add_argument("--phase", type=int, choices=[1, 2], required=True)
    parser.add_argument("--signal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run_async(work(parser.parse_args()))
