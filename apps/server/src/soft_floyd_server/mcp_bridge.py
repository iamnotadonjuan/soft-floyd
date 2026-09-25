"""The web coach's authenticated client of our own MCP endpoint."""

from __future__ import annotations

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from soft_floyd_core.coach.tools import SourceOut, ToolResult
from soft_floyd_core.config import Settings


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
        data = response.data
        if isinstance(data, ToolResult):
            return data
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        elif hasattr(data, "__dict__"):
            data = vars(data)
        if not isinstance(data, dict):
            raise RuntimeError("Invalid MCP coach-tool response")
        return ToolResult(
            content=str(data["content"]),
            status=str(data["status"]),
            sources=[SourceOut(**item) for item in data.get("sources", [])],
        )

    async def context(self) -> str:
        transport = StreamableHttpTransport(
            self._url,
            headers={"Authorization": f"Bearer {self._token}"},
            httpx_client_factory=self._httpx_client_factory,
        )
        async with Client(transport) as client:
            response = await client.call_tool("get_coach_context", {})
        return str(response.data)
