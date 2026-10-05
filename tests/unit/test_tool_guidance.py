"""Generic advisory descriptions; exact schemas and trusted risk stay authoritative."""

import asyncio
from unittest.mock import Mock

from agent_reliability_runtime.mcp.client import catalog
from agent_reliability_runtime.mcp.contracts import INPUTS, RUNTIME_FIELDS
from mcp_server.opsdesk.server import create_server


def test_generic_tool_guidance_and_model_ownership() -> None:
    wire, model = catalog(asyncio.run(create_server(Mock()).list_tools()))
    assert len(model) == 5 and set(wire) == set(INPUTS)
    for tool in model:
        text = tool.description
        if tool.name in {"get_incident", "get_service_status"}:
            assert "read-only" in text and "never changes state" in text
        else:
            assert ("explicitly requests" in text) or ("explicitly asks" in text)
            assert "side effect" in text and "exact approval" in text
        for forbidden in ("S01", "S02", "INC-1001", "INC-1002", "checkout-api", "G8"):
            assert forbidden not in text
        properties = tool.parameters["properties"]
        assert isinstance(properties, dict)
        assert set(properties) == set(
            INPUTS[tool.name].model_fields
        ) - RUNTIME_FIELDS.get(tool.name, set())
