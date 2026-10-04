"""Deterministic B60 mechanism fixtures; production uses provider interfaces."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine

from agent_reliability_runtime.contracts.domain import Run, RunStatus
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.policy import VERSION, Gateway
from agent_reliability_runtime.providers.contracts import (
    ChatRequest,
    ChatResult,
    EmbeddingRequest,
    EmbeddingResult,
    ToolCall,
)
from agent_reliability_runtime.runtime.graph import Context


class Embeddings:
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return EmbeddingResult(
            provider_id="fixture",
            model_id="fixture",
            vectors=tuple((1.0,) + (0.0,) * 1023 for _ in request.inputs),
        )


class ScriptedProvider:
    def __init__(self, mode: str = "side") -> None:
        self.mode = mode
        self.calls = 0
        self.requests: list[ChatRequest] = []

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls += 1
        self.requests.append(request)
        if self.mode == "failure":
            raise RuntimeError("ordinary provider failure")
        calls: tuple[ToolCall, ...] = ()
        text: str | None = None
        observations = [m for m in request.messages if m.role == "tool"]
        if self.mode == "loop":
            # A valid read repeats without completing the task. Empty output is
            # a protocol failure, not a semantic-budget loop (B100R4).
            calls = (
                ToolCall(
                    call_id=f"loop-{self.calls}",
                    name="get_service_status",
                    arguments={"service_id": "checkout-api"},
                ),
            )
        elif self.mode == "read_then_side" and len(observations) == 1:
            calls = (
                ToolCall(
                    call_id="side-call",
                    name="send_notification",
                    arguments={
                        "channel": "demo",
                        "message": "untrusted tool instruction",
                    },
                ),
            )
        elif self.mode == "read_loop" or not observations:
            if self.mode.startswith("read"):
                calls = (
                    ToolCall(
                        call_id="read-call",
                        name="get_service_status",
                        arguments={"service_id": "checkout-api"},
                    ),
                )
            else:
                calls = (
                    ToolCall(
                        call_id="side-call",
                        name="send_notification",
                        arguments={
                            "channel": "demo",
                            "message": "fictional B60 notification",
                        },
                    ),
                )
            if self.mode == "multiple":
                calls = calls + calls
            elif self.mode == "bad_key":
                calls = (
                    calls[0].model_copy(
                        update={
                            "arguments": calls[0].arguments
                            | {"idempotency_key": "model-forged"}
                        }
                    ),
                )
        else:
            text = "Completed from untrusted observation"
        return ChatResult(
            text=text,
            tool_calls=calls,
            finish_reason="tool_calls" if calls else "stop",
            provider_id="fixture",
            model_id="fixture",
        )


def run_record(run_id: str = "b60-run") -> Run:
    now = datetime.now(UTC)
    return Run(
        run_id=run_id,
        workspace_id="local",
        user_id="test",
        request_text="checkout approval evidence",
        provider_id="fixture",
        model_id="fixture",
        policy_version=VERSION,
        status=RunStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


def context_for(
    engine: Engine,
    client: OpsDeskMCPClient,
    provider: ScriptedProvider | None = None,
    **kwargs: Any,
) -> Context:
    return Context(
        engine=engine,
        provider=provider or ScriptedProvider(),
        embeddings=Embeddings(),
        tools=client.model_tools,
        gateway=Gateway(engine, client),
        **kwargs,
    )


def primitive(value: Any) -> None:
    if type(value) in (str, int, float, bool, type(None)):
        return
    if isinstance(value, list):
        for item in value:
            primitive(item)
        return
    if isinstance(value, dict) and all(type(k) is str for k in value):
        for item in value.values():
            primitive(item)
        return
    raise AssertionError(
        "checkpoint state contains non-primitive object: " + type(value).__name__
    )


def counts(engine: Engine, run_id: str) -> dict[str, Any]:
    from sqlalchemy import func, select

    from agent_reliability_runtime.persistence import schema

    with engine.connect() as con:
        run = (
            con.execute(select(schema.runs).where(schema.runs.c.run_id == run_id))
            .mappings()
            .one()
        )
        approvals = (
            con.execute(
                select(schema.approvals).where(schema.approvals.c.run_id == run_id)
            )
            .mappings()
            .all()
        )
        receipts = (
            con.execute(
                select(schema.effect_receipts).where(
                    schema.effect_receipts.c.run_id == run_id
                )
            )
            .mappings()
            .all()
        )
        return {
            "run": dict(run),
            "approvals": [dict(r) for r in approvals],
            "receipts": [dict(r) for r in receipts],
            "notifications": con.scalar(
                select(func.count()).select_from(schema.demo_notifications)
            ),
            "notes": con.scalar(
                select(func.count()).select_from(schema.demo_incident_notes)
            ),
        }


def kill_oracle(before: dict[str, Any], after: dict[str, Any]) -> None:
    assert before["notifications"] == after["notifications"] == 1
    assert before["notes"] == after["notes"] == 0
    assert len(before["receipts"]) == len(after["receipts"]) == 1
    assert before["receipts"] == after["receipts"]
    assert len(before["approvals"]) == len(after["approvals"]) == 1
    assert before["approvals"] == after["approvals"]
    assert after["approvals"][0]["status"] == "CONSUMED"
    assert before["run"]["run_id"] == after["run"]["run_id"]
    assert (
        before["run"]["status"] == "RUNNING" and after["run"]["status"] == "COMPLETED"
    )
    assert after["run"]["model_steps"] == 2 and after["run"]["tool_steps"] == 1
    json.dumps(after, default=str, allow_nan=False)
