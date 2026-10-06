"""Plural reads are harmless alternatives; bad batches execute nothing."""

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_reliability_runtime.mcp.contracts import Service
from agent_reliability_runtime.providers.contracts import (
    ChatResult,
    ModelSettings,
    ToolCall,
)
from agent_reliability_runtime.runtime.graph import (
    decide,
    execute_tool,
    observe_result,
    policy_gate,
    validate_model_action,
)
from agent_reliability_runtime.runtime.prompt_context import (
    UnknownCitationAlias,
    normalize_citation_aliases,
)
from agent_reliability_runtime.runtime.protocol import repair_reason


def read(identity: str = "r1", target: str = "synthetic") -> ToolCall:
    return ToolCall(
        call_id=identity, name="get_service_status", arguments={"service_id": target}
    )


def write(identity: str = "w1") -> ToolCall:
    return ToolCall(
        call_id=identity,
        name="restart_service",
        arguments={"service_id": "synthetic", "reason": "requested"},
    )


def state() -> dict[str, Any]:
    return dict(
        run_id="batch-fixture",
        provider_id="fixture",
        model_id="fixture",
        model_steps=0,
        tool_steps=0,
        budget=8,
        protocol_repairs=0,
        pending_calls=[],
        memory_ids=[],
        messages=[{"role": "user", "content": "Inspect"}],
        evidence=[{"evidence_id": "a" * 64}, {"evidence_id": "b" * 64}],
        proposed_call=None,
        action=None,
        approval_id=None,
        result=None,
    )


def context(calls: tuple[ToolCall, ...]) -> Any:
    return SimpleNamespace(
        provider=SimpleNamespace(
            complete=AsyncMock(
                side_effect=[
                    ChatResult(
                        provider_id="fixture",
                        model_id="fixture",
                        finish_reason="tool_calls",
                        text=None,
                        tool_calls=calls,
                    ),
                    ChatResult(
                        provider_id="fixture",
                        model_id="fixture",
                        finish_reason="stop",
                        text="Grounded [E2]",
                    ),
                ]
            )
        ),
        model_settings=ModelSettings(),
        tools=(),
        engine=Mock(),
        key_factory=lambda: "unused",
        fault_hook=None,
        telemetry=SimpleNamespace(span=lambda *a, **kw: nullcontext(Mock())),
        gateway=SimpleNamespace(
            execute=AsyncMock(
                return_value=Service(service_id="synthetic", status="healthy")
            )
        ),
    )


@pytest.fixture
def boundaries() -> Any:
    with (
        patch(
            "agent_reliability_runtime.runtime.graph.memory_scope",
            return_value=("local", "fixture"),
        ),
        patch("agent_reliability_runtime.runtime.graph.MemoryStore") as memory,
        patch("agent_reliability_runtime.runtime.graph.audit"),
    ):
        memory.return_value.resolve.return_value = []
        yield


@pytest.mark.parametrize(
    "calls", [(read(), read("r2", "alternate")), (read(), read("r2")), (read(),)]
)
def test_all_read_results_before_next_model_call(
    boundaries: Any, calls: tuple[ToolCall, ...]
) -> None:
    async def exercise() -> None:
        s = state()
        c = context(calls)
        rt = cast(Any, SimpleNamespace(context=c))
        s.update(await decide(cast(Any, s), rt))
        assert s["model_steps"] == 1 and len(s["pending_calls"]) == len(calls) - 1
        assert len(s["messages"][-1]["tool_calls"]) == len(calls)
        while s["route"] == "validate_action":
            s.update(await validate_model_action(cast(Any, s), rt))
            s.update(await policy_gate(cast(Any, s), rt))
            assert s["route"] == "execute_tool"
            s.update(await execute_tool(cast(Any, s), rt))
            s.update(observe_result(cast(Any, s)))
            assert c.provider.complete.await_count == 1
        assert s["tool_steps"] == len(calls) and s["pending_calls"] == []
        observations = [m for m in s["messages"] if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in observations] == [x.call_id for x in calls]
        s.update(await decide(cast(Any, s), rt))
        assert s["status"] == "COMPLETED" and s["model_steps"] == 2
        assert s["final_text"] == f"Grounded [evidence:{'b' * 64}]"
        assert c.gateway.execute.await_count == len(calls)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "calls,route",
    [
        ((read(), write()), "decide"),
        ((write(), write("w2")), "decide"),
        ((read(), read()), "finalize"),
        (
            (read(), ToolCall(call_id="r2", name="get_service_status", arguments={})),
            "finalize",
        ),
        ((read(), ToolCall(call_id="r2", name="unknown", arguments={})), "finalize"),
        (tuple(read(f"r{i}") for i in range(5)), "finalize"),
    ],
)
def test_bad_batch_has_zero_execution(
    boundaries: Any, calls: tuple[ToolCall, ...], route: str
) -> None:
    c = context(calls)
    result = asyncio.run(
        decide(cast(Any, state()), cast(Any, SimpleNamespace(context=c)))
    )
    assert result["route"] == route and "proposed_call" not in result
    c.gateway.execute.assert_not_awaited()
    assert result["model_steps"] == 1
    if route == "decide":
        assert result["protocol_repairs"] == 1 and result["pending_calls"] == []


def test_missing_ids_normalized_and_aliases_fail_closed(boundaries: Any) -> None:
    calls = tuple(read(f"r{i}").model_copy(update={"call_id": None}) for i in range(2))
    c = context(calls)
    update = asyncio.run(
        decide(cast(Any, state()), cast(Any, SimpleNamespace(context=c)))
    )
    ids = [update["proposed_call"]["call_id"], update["pending_calls"][0]["call_id"]]
    assert len(set(ids)) == 2 and all(ids)
    assert (
        normalize_citation_aliases("Chosen [E2]", state()["evidence"])
        == f"Chosen [evidence:{'b' * 64}]"
    )
    for text in ("[E999]", "[E0]", "[E01]", "[e1]", "[E1,E2]"):
        with pytest.raises(UnknownCitationAlias):
            normalize_citation_aliases(text, state()["evidence"])


@pytest.mark.parametrize(
    "text",
    [
        '{"tool":"get_service_status","parameters":{}}',
        'get_service_status(service_id="synthetic")',
        '```\nget_service_status(service_id="synthetic")\nrestart_service(service_id="synthetic")\n```',
        '<tool_call>{"name":"restart_service","arguments":{}}</tool_call>',
    ],
)
def test_protocol_v2_only_classifies(text: str) -> None:
    assert (
        repair_reason(text, {"get_service_status", "restart_service"}, {"a" * 64})
        == "textual_tool_request"
    )
