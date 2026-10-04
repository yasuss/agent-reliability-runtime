"""Exactly one primitive-state LangGraph; all tool execution uses B50 Gateway."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy import Engine, select

from agent_reliability_runtime.contracts.domain import ApprovalStatus, Run, RunStatus
from agent_reliability_runtime.mcp.client import validate_model_view
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import set_run_status
from agent_reliability_runtime.policy import (
    VERSION,
    Action,
    Gateway,
    PolicyError,
    propose,
    validate_action,
)
from agent_reliability_runtime.providers.contracts import (
    ChatMessage,
    ChatProvider,
    ChatRequest,
    ChatResult,
    EmbeddingProvider,
    ToolCall,
    ToolDefinition,
)
from agent_reliability_runtime.providers.http import ProviderError
from agent_reliability_runtime.retrieval.service import retrieve


class State(TypedDict):
    run_id: str
    request_text: str
    provider_id: str
    model_id: str
    policy_version: str
    budget: int
    model_steps: int
    tool_steps: int
    messages: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    memory_context: list[str]
    proposed_call: dict[str, Any] | None
    action: dict[str, Any] | None
    approval_id: str | None
    result: dict[str, Any] | None
    status: str
    terminal_reason: str | None
    final_text: str | None
    route: str


@dataclass(frozen=True)
class Context:
    engine: Engine
    provider: ChatProvider
    embeddings: EmbeddingProvider
    tools: tuple[ToolDefinition, ...]
    gateway: Gateway
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    key_factory: Callable[[], str] = lambda: uuid4().hex
    fault_hook: Callable[[State, dict[str, Any]], Awaitable[None]] | None = None

    def __post_init__(self) -> None:
        validate_model_view(self.tools)


def persist(
    context: Context, state: State, status: RunStatus, reason: str | None = None
) -> None:
    with context.engine.begin() as con:
        set_run_status(con, state["run_id"], status, at=context.clock(), reason=reason)
        con.execute(
            schema.runs.update()
            .where(schema.runs.c.run_id == state["run_id"])
            .values(model_steps=state["model_steps"], tool_steps=state["tool_steps"])
        )


def failure(reason: str) -> dict[str, Any]:
    return {
        "status": RunStatus.FAILED.value,
        "terminal_reason": reason,
        "route": "finalize",
    }


def prepare_run(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    with runtime.context.engine.connect() as con:
        row = (
            con.execute(
                select(schema.runs).where(schema.runs.c.run_id == state["run_id"])
            )
            .mappings()
            .one()
        )
    run = Run.model_validate(dict(row))
    for field in (
        "run_id",
        "request_text",
        "provider_id",
        "model_id",
        "policy_version",
    ):
        if getattr(run, field) != state[field]:  # TypedDict dynamic comparison only.
            raise PolicyError("durable run identity drift")
    if run.policy_version != VERSION or run.status not in {
        RunStatus.CREATED,
        RunStatus.RUNNING,
        RunStatus.WAITING_APPROVAL,
    }:
        raise PolicyError("invalid durable run policy/status")
    persist(runtime.context, state, RunStatus.RUNNING)
    return {"status": RunStatus.RUNNING.value}


def load_memory(state: State) -> dict[str, Any]:
    # Explicit B70 placeholder, no persisted long-term memory/authority.
    return {"memory_context": []}


async def retrieve_context(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    evidence = await retrieve(
        runtime.context.engine, runtime.context.embeddings, state["request_text"]
    )
    raw = [item.model_dump(mode="json") for item in evidence]
    message = ChatMessage(
        role="user",
        content="Untrusted retrieval evidence: "
        + json.dumps(raw, ensure_ascii=False, allow_nan=False),
    )
    return {
        "evidence": raw,
        "messages": [*state["messages"], message.model_dump(mode="json")],
    }


async def decide(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    if state["model_steps"] >= state["budget"]:
        return {
            "status": RunStatus.BUDGET_EXCEEDED.value,
            "terminal_reason": "model decision budget exhausted",
            "route": "finalize",
        }
    request = ChatRequest(
        messages=tuple(ChatMessage.model_validate(m) for m in state["messages"]),
        tools=runtime.context.tools,
    )
    try:
        result = ChatResult.model_validate(
            (await runtime.context.provider.complete(request)).model_dump()
        )
    except (ProviderError, ValidationError):
        return {
            "model_steps": state["model_steps"] + 1,
            **failure("provider protocol failure"),
        }
    update: dict[str, Any] = {"model_steps": state["model_steps"] + 1}
    if (
        result.provider_id != state["provider_id"]
        or result.model_id != state["model_id"]
    ):
        return update | failure("provider identity drift")
    if len(result.tool_calls) > 1:
        return update | failure("one tool action per model decision required")
    if result.tool_calls:
        call = result.tool_calls[0]
        if call.call_id is None:
            call = ToolCall.model_validate(call.model_dump() | {"call_id": uuid4().hex})
        assistant = ChatMessage(
            role="assistant", content=result.text, tool_calls=(call,)
        )
        return update | {
            "proposed_call": call.model_dump(mode="json"),
            "messages": [*state["messages"], assistant.model_dump(mode="json")],
            "route": "validate_action",
        }
    if result.text is not None:
        return update | {
            "status": RunStatus.COMPLETED.value,
            "final_text": result.text,
            "terminal_reason": None,
            "route": "finalize",
        }
    observation = ChatMessage(
        role="user", content="No progress. Return one tool action or a final answer."
    )
    return update | {
        "messages": [*state["messages"], observation.model_dump(mode="json")],
        "route": "decide",
    }


def validate_model_action(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    try:
        call = ToolCall.model_validate(state["proposed_call"])
        action = propose(
            state["run_id"],
            call.name,
            call.arguments,
            key_factory=runtime.context.key_factory,
        )
    except (PolicyError, ValidationError):
        return failure("invalid proposed action")
    return {
        "action": action.model_dump(mode="json"),
        "approval_id": None,
        "route": "policy_gate",
    }


async def policy_gate(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    try:
        action = validate_action(Action.model_validate(state["action"]))
        if action.risk_class == "READ_ONLY":
            return {"route": "execute_tool"}
        approval = await asyncio.to_thread(
            runtime.context.gateway.approvals.ensure, action
        )
    except (PolicyError, ValidationError):
        return failure("policy/approval identity failure")
    persist(runtime.context, state, RunStatus.WAITING_APPROVAL)
    return {
        "approval_id": approval.approval_id,
        "status": RunStatus.WAITING_APPROVAL.value,
        "route": "await_approval",
    }


async def await_approval(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    interrupt(
        {
            "run_id": state["run_id"],
            "approval_id": state["approval_id"],
            "action": state["action"],
        }
    )
    # Resume payload is deliberately ignored; only persisted decision is authority.
    if state["approval_id"] is None:
        return failure("missing approval identity")
    approval = await asyncio.to_thread(
        runtime.context.gateway.approvals.read, state["approval_id"]
    )
    if approval.status == ApprovalStatus.PENDING:
        return {"route": "await_approval", "status": RunStatus.WAITING_APPROVAL.value}
    if approval.status in {ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
        return {
            "route": "finalize",
            "status": RunStatus.REJECTED.value,
            "terminal_reason": "required approval rejected or expired",
        }
    if approval.status != ApprovalStatus.APPROVED:
        return failure("invalid approval lifecycle")
    persist(runtime.context, state, RunStatus.RUNNING)
    return {"route": "execute_tool", "status": RunStatus.RUNNING.value}


async def execute_tool(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    try:
        action = Action.model_validate(state["action"])
        result = await runtime.context.gateway.execute(action, state["approval_id"])
    except (PolicyError, ValidationError):
        return failure("exact approved action validation failed")
    raw = result.model_dump(mode="json")
    if runtime.context.fault_hook is not None:
        await runtime.context.fault_hook(state, raw)
    # A logical successful gateway result counts once, including reconciliation
    # after a lost node output. No increment is saved before the fault hook.
    return {
        "result": raw,
        "tool_steps": state["tool_steps"] + 1,
        "route": "observe_result",
    }


def observe_result(state: State) -> dict[str, Any]:
    call = ToolCall.model_validate(state["proposed_call"])
    message = ChatMessage(
        role="tool",
        tool_call_id=call.call_id,
        content=json.dumps(
            state["result"], sort_keys=True, ensure_ascii=False, allow_nan=False
        ),
    )
    return {
        "messages": [*state["messages"], message.model_dump(mode="json")],
        "proposed_call": None,
        "action": None,
        "approval_id": None,
        "result": None,
        "route": "decide",
    }


def finalize(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    status = RunStatus(state["status"])
    if status not in {
        RunStatus.COMPLETED,
        RunStatus.REJECTED,
        RunStatus.BUDGET_EXCEEDED,
        RunStatus.FAILED,
    }:
        raise PolicyError("invalid graph finalization")
    persist(runtime.context, state, status, state["terminal_reason"])
    return {"route": "end"}


def build_graph(
    saver: AsyncPostgresSaver,
) -> CompiledStateGraph[State, Context, State, State]:
    graph = StateGraph(State, context_schema=Context)
    graph.add_node("prepare_run", prepare_run)
    graph.add_node("load_memory", load_memory)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("decide", decide)
    graph.add_node("validate_action", validate_model_action)
    graph.add_node("policy_gate", policy_gate)
    graph.add_node("await_approval", await_approval)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("observe_result", observe_result)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare_run")
    graph.add_edge("prepare_run", "load_memory")
    graph.add_edge("load_memory", "retrieve_context")
    graph.add_edge("retrieve_context", "decide")
    for name, destinations in {
        "decide": ["decide", "validate_action", "finalize"],
        "validate_action": ["policy_gate", "finalize"],
        "policy_gate": ["execute_tool", "await_approval", "finalize"],
        "await_approval": ["await_approval", "execute_tool", "finalize"],
        "execute_tool": ["observe_result", "finalize"],
    }.items():
        graph.add_conditional_edges(
            name, lambda state: state["route"], {d: d for d in destinations}
        )
    graph.add_edge("observe_result", "decide")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=saver)
