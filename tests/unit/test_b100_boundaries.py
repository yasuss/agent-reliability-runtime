"""B100 bounded retry, citation and settings calibration without infrastructure."""

import asyncio
from inspect import unwrap
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from agent_reliability_runtime.mcp.client import OpsDeskError
from agent_reliability_runtime.mcp.contracts import Service
from agent_reliability_runtime.policy import propose
from agent_reliability_runtime.providers.contracts import (
    ChatMessage,
    ChatRequest,
    ModelSettings,
)
from agent_reliability_runtime.providers.http import (
    HTTPProviderConfig,
    OpenAICompatibleChatProvider,
)
from agent_reliability_runtime.retrieval.citations import (
    citation_ids,
    validate_citations,
)
from agent_reliability_runtime.runtime.graph import execute_tool


@pytest.mark.parametrize("seed", [-1, True, 1.0, "101"])
def test_seed_strict(seed: object) -> None:
    with pytest.raises(ValidationError):
        ModelSettings(seed=seed)  # type: ignore[arg-type]


def test_citation_calibration() -> None:
    a, b = "a" * 64, "b" * 64
    assert validate_citations(f"[evidence:{a}]", {a}) == [a]
    with pytest.raises(ValueError):
        validate_citations(f"[evidence:{b}]", {a})
    assert validate_citations(f"[evidence:{b}] [evidence:{a}]", {a, b}) == [b, a]
    assert citation_ids(a + " [evidence:ABC]") == []


@pytest.mark.parametrize("seed", [None, 101])
def test_seed_wire_only_configured(seed: int | None) -> None:
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "fixture",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    provider = OpenAICompatibleChatProvider(
        HTTPProviderConfig("generic-vllm", "fixture", "http://localhost/v1"),
        transport=httpx.MockTransport(respond),
    )
    asyncio.run(
        provider.complete(
            ChatRequest(
                messages=(ChatMessage(role="user", content="test"),),
                settings=ModelSettings(seed=seed),
            )
        )
    )
    assert ("seed" in seen[0]) == (seed is not None)


@pytest.mark.parametrize(
    "failures,side,expected_calls,failed,retries",
    [
        (0, False, 1, False, 0),
        (1, False, 2, False, 1),
        (2, False, 2, True, 1),
        (1, True, 1, True, 0),
    ],
)
def test_retry_calibration(
    failures: int, side: bool, expected_calls: int, failed: bool, retries: int
) -> None:
    action = propose(
        "run",
        "restart_service" if side else "get_service_status",
        {"service_id": "checkout-api", **({"reason": "fixture"} if side else {})},
    )
    gateway = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                *[OpsDeskError("bounded")] * failures,
                Service(service_id="checkout-api", status="degraded"),
            ]
        )
    )
    context = SimpleNamespace(gateway=gateway, fault_hook=None)
    state = {
        "action": action.model_dump(),
        "approval_id": None,
        "tool_steps": 0,
        "run_id": "run",
    }
    result: dict[str, Any]
    with patch("agent_reliability_runtime.runtime.graph.audit") as audited:
        if side:
            with pytest.raises(OpsDeskError):
                asyncio.run(
                    unwrap(execute_tool)(state, SimpleNamespace(context=context))
                )
            result = {"status": "FAILED"}
        else:
            result = asyncio.run(
                unwrap(execute_tool)(state, SimpleNamespace(context=context))
            )
    assert gateway.execute.await_count == expected_calls
    assert (result.get("status") == "FAILED") == failed
    assert audited.call_count == retries
    if not failed:
        assert result["tool_steps"] == 1
