"""Stdio infrastructure; production execution enters through policy.Gateway."""

import copy
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, RequestParamsMeta, Tool
from pydantic import ValidationError

from agent_reliability_runtime.contracts.domain import Record
from agent_reliability_runtime.mcp.contracts import (
    DIGEST_META,
    INPUTS,
    OUTPUTS,
    RUN_META,
    RUNTIME_FIELDS,
    ReceiptEnvelope,
)
from agent_reliability_runtime.providers.contracts import ToolDefinition

if TYPE_CHECKING:
    from agent_reliability_runtime.policy import Action


class OpsDeskError(Exception):
    """Bounded infrastructure failure with no raw wire/credential diagnostics."""


def semantic_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Ignore annotation-only titles/descriptions and unordered required lists."""
    result = {}
    for key, value in schema.items():
        if key in {"title", "description"}:
            continue
        if key == "properties" and isinstance(value, dict):
            # Property *names* are structural even when named title/description.
            value = {name: semantic_schema(shape) for name, shape in value.items()}
        elif isinstance(value, dict):
            value = semantic_schema(value)
        elif key == "required" and isinstance(value, list):
            value = sorted(value)
        result[key] = value
    return result


def catalog(
    tools: Sequence[Tool],
) -> tuple[dict[str, Tool], tuple[ToolDefinition, ...]]:
    if len(tools) != 5 or {t.name for t in tools} != set(INPUTS):
        raise OpsDeskError("OpsDesk exact-five catalog mismatch")
    wire = {}
    model = []
    for tool in sorted(tools, key=lambda t: t.name):
        if semantic_schema(tool.input_schema) != semantic_schema(
            INPUTS[tool.name].model_json_schema()
        ):
            raise OpsDeskError("OpsDesk argument ownership/schema mismatch")
        if tool.output_schema is None or semantic_schema(
            tool.output_schema
        ) != semantic_schema(OUTPUTS[tool.name].model_json_schema()):
            raise OpsDeskError("OpsDesk output schema mismatch")
        wire[tool.name] = tool.model_copy(deep=True)
        projected = copy.deepcopy(tool.input_schema)
        for field in RUNTIME_FIELDS.get(tool.name, set()):
            del projected["properties"][field]
            projected["required"].remove(field)
        model.append(
            ToolDefinition.model_validate(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": projected,
                }
            )
        )
    validate_model_view(model)
    return wire, tuple(model)


def validate_model_view(model: Sequence[ToolDefinition]) -> None:
    if len(model) != 5 or {tool.name for tool in model} != set(INPUTS):
        raise OpsDeskError("model catalog mismatch")
    for tool in model:
        expected = INPUTS[tool.name].model_json_schema()
        for field in RUNTIME_FIELDS.get(tool.name, set()):
            del expected["properties"][field]
            expected["required"].remove(field)
        if semantic_schema(tool.parameters) != semantic_schema(expected):
            raise OpsDeskError("model field ownership mismatch")


def validated_result(name: str, result: CallToolResult) -> Record:
    if result.is_error:
        raise OpsDeskError("OpsDesk tool failed")
    if name not in OUTPUTS or result.structured_content is None:
        raise OpsDeskError("OpsDesk structured output missing")
    try:
        return OUTPUTS[name].model_validate(result.structured_content)
    except ValidationError:
        pass
    raise OpsDeskError("OpsDesk structured output invalid")


class OpsDeskMCPClient:
    def __init__(self, root: Path, database_url: str) -> None:
        self.parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.opsdesk"],
            cwd=str(root.resolve()),
            env={"ARR_DATABASE_URL": database_url},
        )
        self._client = Client(self.parameters, read_timeout_seconds=30)
        self.wire_tools: dict[str, Tool] = {}
        self.model_tools: tuple[ToolDefinition, ...] = ()

    async def __aenter__(self) -> "OpsDeskMCPClient":
        await self._client.__aenter__()
        try:
            listed = await self._client.list_tools()
            self.wire_tools, self.model_tools = catalog(listed.tools)
        except BaseException:
            await self._client.__aexit__(*sys.exc_info())
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @property
    def protocol_version(self) -> str:
        return self._client.protocol_version

    @property
    def server_info(self) -> dict[str, Any]:
        info = self._client.server_info
        return info.model_dump() if info else {}

    async def read(self, name: str, arguments: dict[str, Any]) -> Record:
        if name not in {"get_incident", "get_service_status"}:
            raise OpsDeskError("read surface excludes raw mutations")
        return validated_result(name, await self._client.call_tool(name, arguments))

    async def raw_wire_call_for_testing(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> Record:
        """Unsafe infrastructure/test-only surface; never connect to a graph."""
        return validated_result(
            name,
            await self._client.call_tool(
                name,
                arguments,
                meta=cast(RequestParamsMeta, meta) if meta is not None else None,
            ),
        )

    async def _dispatch_effect(self, action: "Action") -> ReceiptEnvelope:
        """Internal transport hook for Gateway; does not authorize by itself."""
        result = await self.raw_wire_call_for_testing(
            action.tool_name,
            action.normalized_args,
            meta={RUN_META: action.run_id, DIGEST_META: action.action_digest},
        )
        return ReceiptEnvelope.model_validate(result.model_dump())
