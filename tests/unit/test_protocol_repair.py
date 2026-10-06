"""Good/broken/alternate calibration of non-authorizing protocol correction."""

import asyncio
import inspect
import json
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_reliability_runtime.providers.contracts import (
    ChatResult,
    ModelSettings,
    ToolCall,
    ToolDefinition,
)
from agent_reliability_runtime.runtime.graph import decide
from agent_reliability_runtime.runtime.protocol import correction, repair_reason

EVIDENCE = "a" * 64
OTHER = "b" * 64
TOOLS = {"read_probe", "restart_probe"}


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            '{"name":"read_probe","arguments":{"query":"status"}}',
            "textual_tool_request",
        ),
        (
            '{"name":"restart_probe","arguments":{"service":"synthetic"}}',
            "textual_tool_request",
        ),
        ('{"name":"read_probe","arguments":{}}', "textual_tool_request"),
        ('{"name":"unknown","arguments":{}}', None),
        ('{"name":"read_probe","arguments":{},"extra":true}', None),
        ('{"name":"read_probe","arguments":[]}', None),
        ('prefix {"name":"read_probe","arguments":{}}', None),
        ('{"status":"healthy"}', None),
        (f"evidence_id: {EVIDENCE}", "citation_format"),
        ("Evidence ID: aaaaaaaa...", "citation_format"),
        ("Grounded (aaaaaaaa\u2026).", "citation_format"),
        (EVIDENCE, "citation_format"),
        (f"Grounded [evidence:{EVIDENCE}]", None),
        (f"Foreign [evidence:{OTHER}] evidence ID", None),
        ("Ordinary answer.", None),
        ("Grounded (bbbbbbbb...).", None),
    ],
)
def test_detector_calibration(text: str, expected: str | None) -> None:
    assert repair_reason(text, TOOLS, {EVIDENCE}) == expected


def test_ambiguous_prefix_and_correction_content() -> None:
    assert repair_reason("aaaaaaaa...", TOOLS, {EVIDENCE, "a" * 63 + "b"}) is None
    assert repair_reason("evidence_id", TOOLS, set()) is None
    message = correction("citation_format", {EVIDENCE})
    assert message.endswith(f"[evidence:{EVIDENCE}]")
    assert "arguments" not in correction("textual_tool_request", {EVIDENCE})


def fixture_state() -> dict[str, Any]:
    return dict(
        run_id="repair-fixture",
        provider_id="fixture",
        model_id="fixture",
        model_steps=0,
        tool_steps=0,
        protocol_repairs=0,
        budget=8,
        messages=[{"role": "user", "content": "Disposable investigation"}],
        evidence=[{"evidence_id": EVIDENCE}],
        memory_ids=[],
    )


def result(text: str | None, calls: tuple[ToolCall, ...] = ()) -> ChatResult:
    return ChatResult(
        provider_id="fixture",
        model_id="fixture",
        text=text,
        tool_calls=calls,
        finish_reason="tool_calls" if calls else "stop",
    )


def context_for_results(results: list[ChatResult]) -> Any:
    return SimpleNamespace(
        provider=SimpleNamespace(complete=AsyncMock(side_effect=results)),
        model_settings=ModelSettings(),
        tools=tuple(
            ToolDefinition(
                name=n, description="Disposable", parameters={"type": "object"}
            )
            for n in sorted(TOOLS)
        ),
        engine=Mock(),
        telemetry=SimpleNamespace(span=lambda *a, **kw: nullcontext(Mock())),
        gateway=SimpleNamespace(execute=AsyncMock()),
    )


async def decision(
    state: dict[str, Any], context: Any, fn: Any = decide
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        await fn(cast(Any, state), cast(Any, SimpleNamespace(context=context))),
    )


@pytest.fixture
def boundaries() -> Any:
    with (
        patch(
            "agent_reliability_runtime.runtime.graph.memory_scope",
            return_value=("local", "fixture"),
        ),
        patch("agent_reliability_runtime.runtime.graph.MemoryStore") as memory,
        patch("agent_reliability_runtime.runtime.graph.audit") as audited,
        patch("agent_reliability_runtime.runtime.graph.propose") as proposed,
    ):
        memory.return_value.resolve.return_value = []
        yield audited, proposed


@pytest.mark.parametrize("name", ["read_probe", "restart_probe"])
def test_text_never_authorizes_before_later_structured_decision(
    boundaries: Any, name: str
) -> None:
    audited, proposed = boundaries
    state = fixture_state()
    draft = json.dumps({"name": name, "arguments": {"service": "synthetic"}})
    context = context_for_results(
        [
            result(draft),
            result(
                None,
                (
                    ToolCall(
                        name="get_service_status"
                        if name == "read_probe"
                        else "restart_service",
                        arguments={
                            "service_id": "synthetic",
                            **(
                                {"reason": "fixture"} if name == "restart_probe" else {}
                            ),
                        },
                    ),
                ),
            ),
        ]
    )
    first = asyncio.run(decision(state, context))
    assert first["route"] == "decide" and "proposed_call" not in first
    assert first["protocol_repairs"] == 1 and first["model_steps"] == 1
    proposed.assert_not_called()
    context.gateway.execute.assert_not_awaited()
    payload = [
        c.args[3]
        for c in audited.call_args_list
        if c.args[2] == "model.protocol_repair"
    ]
    assert payload == [
        {"reason": "textual_tool_request", "repair_number": 1, "model_step": 1}
    ]
    second = asyncio.run(decision(state | first, context))
    assert second["route"] == "validate_action" and second["model_steps"] == 2
    assert second["proposed_call"]["name"] == (
        "get_service_status" if name == "read_probe" else "restart_service"
    )
    assert context.provider.complete.await_count == 2
    proposed.assert_not_called()
    context.gateway.execute.assert_not_awaited()


@pytest.mark.parametrize("budget", [8, 12])
def test_repairs_charge_model_budget_and_third_fails(
    boundaries: Any, budget: int
) -> None:
    state = fixture_state() | {"budget": budget}
    context = context_for_results([result("evidence ID: aaaaaaaa...")] * 3)
    for step in (1, 2):
        update = asyncio.run(decision(state, context))
        state |= update
        assert state["model_steps"] == step and state["protocol_repairs"] == step
        assert state["route"] == "decide"
    final = asyncio.run(decision(state, context))
    assert final["status"] == "FAILED" and final["model_steps"] == 3
    assert final["terminal_reason"] == "model protocol repair budget exhausted"
    state["model_steps"] = budget
    exhausted = asyncio.run(decision(state, context))
    assert exhausted["status"] == "BUDGET_EXCEEDED"
    assert context.provider.complete.await_count == 3


@pytest.mark.parametrize(
    "text,expected,repairs",
    [
        ("Evidence ID: aaaaaaaa...", None, 1),
        (f"Grounded [evidence:{EVIDENCE}]", "COMPLETED", 0),
        (f"Foreign [evidence:{OTHER}]", "FAILED", 0),
        ("Ordinary valid final.", "COMPLETED", 0),
    ],
)
def test_final_calibration(
    boundaries: Any, text: str, expected: str | None, repairs: int
) -> None:
    state = fixture_state()
    context = context_for_results(
        [result(text), result(f"Grounded [evidence:{EVIDENCE}]")]
    )
    first = asyncio.run(decision(state, context))
    assert first.get("status") == expected
    assert first.get("protocol_repairs", 0) == repairs
    if repairs:
        assert asyncio.run(decision(state | first, context))["status"] == "COMPLETED"


def test_structured_side_effect_with_bad_text_never_repairs(boundaries: Any) -> None:
    context = context_for_results(
        [
            result(
                "evidence ID: invalid",
                (
                    ToolCall(
                        name="restart_service",
                        arguments={"service_id": "synthetic", "reason": "fixture"},
                    ),
                ),
            )
        ]
    )
    update = asyncio.run(decision(fixture_state(), context))
    assert update["route"] == "validate_action" and "protocol_repairs" not in update


def test_mutant_text_promoted_to_call_is_detected(boundaries: Any) -> None:
    """The same safety oracle rejects a deliberately promoted textual request."""
    import agent_reliability_runtime.runtime.graph as graph_module

    source = inspect.getsource(decide)
    needle = '"protocol_repairs": repairs + 1,'
    assert source.count(needle) == 1
    mutant = source.replace(
        needle, needle + '\n                "proposed_call": json.loads(result.text),'
    )
    namespace = dict(vars(graph_module))
    exec(compile(mutant, "<non-authorizing-mutant>", "exec"), namespace)
    text = '{"name":"restart_probe","arguments":{}}'

    def oracle(fn: Any) -> None:
        update = asyncio.run(
            decision(fixture_state(), context_for_results([result(text)]), fn)
        )
        assert update["route"] == "decide" and "proposed_call" not in update

    oracle(decide)
    with pytest.raises(AssertionError):
        oracle(namespace["decide"])
