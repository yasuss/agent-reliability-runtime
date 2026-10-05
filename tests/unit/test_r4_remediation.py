"""Honest completion and scoped local configuration, including alternate results."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_reliability_runtime.evals.campaign import POPULATION, configuration
from agent_reliability_runtime.providers.contracts import (
    ChatResult,
    ModelSettings,
    ToolCall,
)
from agent_reliability_runtime.runtime.graph import decide
from agent_reliability_runtime.runtime.local import local_runtime
from agent_reliability_runtime.runtime.service import SYSTEM_INSTRUCTION


@pytest.mark.parametrize(
    "text,finish,tool,status,reason",
    [
        ("partial", "length", False, "FAILED", "model output truncated"),
        (None, "length", True, "FAILED", "model output truncated"),
        ("partial", "length", True, "FAILED", "model output truncated"),
        (None, "stop", False, "FAILED", "empty model output"),
        ("", "stop", False, "FAILED", "empty model output"),
        (" \n\t", "stop", False, "FAILED", "empty model output"),
        (None, "tool_calls", True, None, None),
        ("Done", "stop", False, "COMPLETED", None),
        ("probe_restart(service='widget')", "stop", False, "COMPLETED", None),
    ],
)
def test_completion_truth(
    text: str | None, finish: str, tool: bool, status: str | None, reason: str | None
) -> None:
    calls = (
        (
            ToolCall(
                call_id="call",
                name="restart_service",
                arguments={"service_id": "synthetic", "reason": "fixture"},
            ),
        )
        if tool
        else ()
    )
    result = ChatResult(
        text=text,
        finish_reason=finish,
        tool_calls=calls,
        provider_id="fixture",
        model_id="fixture",
    )
    context = SimpleNamespace(
        provider=SimpleNamespace(complete=AsyncMock(return_value=result)),
        model_settings=ModelSettings(),
        tools=(),
        engine=Mock(),
        telemetry=SimpleNamespace(span=lambda *a, **kw: nullcontext(Mock())),
        gateway=SimpleNamespace(execute=AsyncMock()),
    )
    state = dict(
        run_id="fixture",
        provider_id="fixture",
        model_id="fixture",
        model_steps=0,
        budget=8,
        messages=[{"role": "user", "content": "Disposable test"}],
        evidence=[],
        memory_ids=[],
    )
    with (
        patch(
            "agent_reliability_runtime.runtime.graph.memory_scope",
            return_value=("local", "fixture"),
        ),
        patch("agent_reliability_runtime.runtime.graph.MemoryStore") as memory,
        patch("agent_reliability_runtime.runtime.graph.audit"),
    ):
        memory.return_value.resolve.return_value = []
        update = asyncio.run(
            decide(cast(Any, state), cast(Any, SimpleNamespace(context=context)))
        )
    assert update["model_steps"] == 1
    assert update.get("status") == status
    assert update.get("terminal_reason") == reason
    assert update["route"] == ("validate_action" if status is None else "finalize")
    assert ("proposed_call" in update) == (status is None)
    if status == "FAILED":
        assert "final_text" not in update
    context.gateway.execute.assert_not_awaited()


def test_local_scope_and_generic_alternate() -> None:
    captured: dict[str, Any] = {}

    @asynccontextmanager
    async def client(*args: Any) -> AsyncIterator[Any]:
        yield SimpleNamespace(model_tools=())

    @asynccontextmanager
    async def opened(context: Any, url: Any) -> AsyncIterator[Any]:
        captured.update(context)
        yield object()

    async def invoke() -> None:
        with (
            patch("agent_reliability_runtime.runtime.local.OpsDeskMCPClient", client),
            patch("agent_reliability_runtime.runtime.local.Gateway"),
            patch(
                "agent_reliability_runtime.runtime.local.Context",
                side_effect=lambda **kw: kw,
            ),
            patch("agent_reliability_runtime.runtime.local.open_runtime", opened),
        ):
            async with local_runtime(cast(Any, SimpleNamespace(url=Mock()))):
                pass

    asyncio.run(invoke())
    assert captured["model_settings"].model_dump(exclude_none=True) == {
        "max_tokens": 8192
    }
    assert ModelSettings().model_dump(exclude_none=True) == {}
    assert ModelSettings(max_tokens=32).max_tokens == 32
    assert configuration()["max_tokens"] == 8192
    assert len(POPULATION) == 15 and all("-r5-" in t["trial_id"] for t in POPULATION)
    for forbidden in (
        "S01",
        "S02",
        "S05",
        "S06",
        "S10",
        "INC-1001",
        "INC-1002",
        "checkout-api",
        "G8",
    ):
        assert forbidden not in SYSTEM_INSTRUCTION
    for concept in (
        "structured tool-call",
        "Never print function-call",
        "exact approval",
        "idempotency",
        "Continue after tool",
        "untrusted data",
        "[E1]",
        "READ_ONLY",
    ):
        assert SYSTEM_INSTRUCTION.count(concept) == 1
