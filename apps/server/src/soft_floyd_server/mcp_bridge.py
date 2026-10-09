"""The web coach's authenticated client of our own MCP endpoint."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from soft_floyd_core.coach.tools import SourceOut, ToolResult
from soft_floyd_core.config import Settings


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return vars(value)
    raise RuntimeError("Invalid MCP coach-tool response")


def _tool_result(response: Any) -> ToolResult:
    # FastMCP's `data` may contain generated Pydantic Root objects, while
    # `structured_content` retains the JSON-compatible mappings.
    data = response.structured_content or response.data
    if isinstance(data, ToolResult):
        return data
    fields = _mapping(data)
    return ToolResult(
        content=str(fields["content"]),
        status=str(fields["status"]),
        sources=[SourceOut.model_validate(_mapping(item)) for item in fields.get("sources", [])],
        training_session_ids=[int(i) for i in fields.get("training_session_ids", [])],
    )


class CoachMCPBridge:
    def __init__(self, settings: Settings, token: str, httpx_client_factory=None):
        self._url = settings.internal_mcp_url
        self._token = token
        self._httpx_client_factory = httpx_client_factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def run(self, name: str, arguments: str) -> ToolResult:
        transport = StreamableHttpTransport(
            self._url,
            headers={"Authorization": f"Bearer {self._token}"},
            httpx_client_factory=self._httpx_client_factory,
        )
        async with Client(transport) as client:
            response = await client.call_tool(
                "run_coach_tool", {"name": name, "arguments": arguments}
            )
        return _tool_result(response)

    async def context(self) -> str:
        transport = StreamableHttpTransport(
            self._url,
            headers={"Authorization": f"Bearer {self._token}"},
            httpx_client_factory=self._httpx_client_factory,
        )
        async with Client(transport) as client:
            response = await client.call_tool("get_coach_context", {})
        return str(response.data)
