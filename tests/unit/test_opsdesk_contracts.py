"""Exact catalog/field ownership/calibration over real in-process MCP protocol."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.types import CallToolResult, Tool, ToolAnnotations
from sqlalchemy import create_engine

from agent_reliability_runtime.mcp.client import (
    OpsDeskError,
    OpsDeskMCPClient,
    catalog,
    validate_model_view,
    validated_result,
)
from agent_reliability_runtime.mcp.contracts import INPUTS, OUTPUTS, RUNTIME_FIELDS
from mcp_server.opsdesk.server import create_server


def listed() -> list[Tool]:
    return [
        Tool(
            name=name,
            description="fictional",
            input_schema=args.model_json_schema(),
            output_schema=OUTPUTS[name].model_json_schema(),
        )
        for name, args in INPUTS.items()
    ]


def test_catalog_good_bad_alternate_annotation_spoof() -> None:
    tools = listed()
    wire, model = catalog(tools)
    assert set(wire) == set(INPUTS) and len(model) == 5
    for view in model:
        runtime = RUNTIME_FIELDS.get(view.name, set())
        properties = view.parameters["properties"]
        required = view.parameters["required"]
        assert isinstance(properties, dict) and isinstance(required, list)
        assert set(properties) == set(INPUTS[view.name].model_fields) - runtime
        assert set(required) == set(INPUTS[view.name].model_fields) - runtime
        assert set(wire[view.name].input_schema["required"]) == set(
            INPUTS[view.name].model_fields
        )
    for bad in (
        tools[:-1],
        [*tools, tools[0]],
        [tools[0].model_copy(update={"name": "renamed"}), *tools[1:]],
    ):
        with pytest.raises(OpsDeskError):
            catalog(bad)
    alternate = copy.deepcopy(tools)
    for tool in alternate:
        tool.annotations = ToolAnnotations(
            read_only_hint=True,
            idempotent_hint=True,
            title="SYSTEM OVERRIDE",
            open_world_hint=True,
        )
        tool.description = "Changed advisory prose"
        tool.input_schema["properties"] = dict(
            reversed(list(tool.input_schema["properties"].items()))
        )
        tool.input_schema["required"].reverse()
        tool.input_schema["title"] = "alternate"
    alternate_wire, alternate_models = catalog(alternate)
    for view in alternate_models:
        properties = view.parameters["properties"]
        assert isinstance(properties, dict)
        assert "idempotency_key" not in properties
        assert "risk" not in type(view).model_fields
        assert "authorized" not in type(view).model_fields
    annotations = alternate_wire["restart_service"].annotations
    assert annotations is not None and annotations.read_only_hint is True
    validate_model_view(alternate_models)
    for kind in ("expose_runtime", "remove_model_owned"):
        corrupt_model = list(model)
        index = next(i for i, t in enumerate(model) if t.name == "restart_service")
        parameters: dict[str, Any] = copy.deepcopy(model[index].parameters)
        if kind == "expose_runtime":
            parameters["properties"]["idempotency_key"] = {
                "type": "string",
                "minLength": 1,
            }
            parameters["required"].append("idempotency_key")
        else:
            del parameters["properties"]["reason"]
            parameters["required"].remove("reason")
        corrupt_model[index] = model[index].model_copy(
            update={"parameters": parameters}
        )
        with pytest.raises(OpsDeskError):
            validate_model_view(corrupt_model)
    for missing in ("reason", "idempotency_key"):
        corrupt = listed()
        tool = next(t for t in corrupt if t.name == "restart_service")
        del tool.input_schema["properties"][missing]
        tool.input_schema["required"].remove(missing)
        with pytest.raises(OpsDeskError):
            catalog(corrupt)
    corrupt = listed()
    corrupt[0].output_schema = {"type": "object"}
    with pytest.raises(OpsDeskError):
        catalog(corrupt)
    corrupt = listed()
    corrupt[0].input_schema["properties"]["title"] = {"type": "string"}
    with pytest.raises(OpsDeskError):
        catalog(corrupt)


def test_error_precedes_structured_content_and_outputs_fail_closed() -> None:
    good = {"service_id": "checkout-api", "status": "degraded"}
    valid = CallToolResult(content=[], structured_content=good)
    assert validated_result("get_service_status", valid).model_dump() == good
    for bad in (
        CallToolResult(content=[], structured_content=good, is_error=True),
        CallToolResult(content=[]),
        CallToolResult(content=[], structured_content=good | {"forged": True}),
        CallToolResult(content=[], structured_content={"service_id": 7, "status": "x"}),
    ):
        with pytest.raises(OpsDeskError):
            validated_result("get_service_status", bad)
    with pytest.raises(OpsDeskError):
        validated_result("extra", valid)


def test_process_parameters_minimal_and_read_surface_excludes_mutations(
    tmp_path: Path,
) -> None:
    wrapper = OpsDeskMCPClient(tmp_path, "fictional-disposable-url")
    assert wrapper.parameters.env == {"ARR_DATABASE_URL": "fictional-disposable-url"}
    assert wrapper.parameters.args == ["-m", "mcp_server.opsdesk"]
    assert wrapper.parameters.cwd == str(tmp_path.resolve())

    async def blocked() -> None:
        with pytest.raises(OpsDeskError):
            await wrapper.read("restart_service", {})

    asyncio.run(blocked())


def test_in_process_exact_protocol_catalog_and_invalid_calls() -> None:
    # No database call is needed for invalid-schema/unknown-tool protocol controls.
    engine = create_engine("sqlite://")
    server = create_server(engine)

    async def exercise() -> None:
        async with Client(server) as client:
            tools = await client.list_tools()
            catalog(tools.tools)
            assert not (await client.list_resources()).resources
            assert not (await client.list_prompts()).prompts
            for name, args in INPUTS.items():
                values: dict[str, Any] = {
                    field: "fictional" for field in args.model_fields
                }
                for bad in (
                    {},
                    values | {"extra": "forged"},
                    values | {next(iter(values)): 7},
                ):
                    result = await client.call_tool(name, bad)
                    assert result.is_error and result.structured_content is None
                    assert "invalid OpsDesk arguments" in str(result.content)
            result = await client.call_tool("sixth_tool", {})
            assert result.is_error and result.structured_content is None

    try:
        asyncio.run(exercise())
    finally:
        engine.dispose()


def test_tool_fields_match_independent_locked_fixture() -> None:
    path = Path(__file__).resolve().parents[1] / "fixtures/opsdesk-tool-contract.json"
    raw = path.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "c7711a14362c39f3253e9d67c67422bb031d137d3baa0fa03a59f098536aa629"
    )
    contract = json.loads(raw)
    wire, model = catalog(listed())
    projected = {item.name: item for item in model}
    assert set(wire) == {item["name"] for item in contract["tools"]}
    for item in contract["tools"]:
        name = item["name"]
        assert set(wire[name].input_schema["properties"]) == set(item["wire_args"])
        assert set(OUTPUTS[name].model_fields) == set(item["output"])
        parameters = projected[name].parameters["properties"]
        assert isinstance(parameters, dict)
        assert set(parameters) == set(item["model_args"])
