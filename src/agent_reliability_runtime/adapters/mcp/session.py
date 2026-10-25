"""Generic stdio MCP session; transport data never grants authorization."""

from typing import Any, Self

from mcp import Client, StdioServerParameters


class MCPTransportError(Exception):
    """Bounded transport failure with no raw credential diagnostics."""


class StdioSession:
    def __init__(self, parameters: StdioServerParameters) -> None:
        self.parameters = parameters
        self._client = Client(parameters, read_timeout_seconds=30)

    async def __aenter__(self) -> Self:
        await self._client.__aenter__()
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
