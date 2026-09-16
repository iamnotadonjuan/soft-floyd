"""Exercises the MCP surface in-process (no HTTP), and checks it agrees
with the REST surface on the same underlying profile — the point of
sharing soft_floyd_core between both adapters.
"""

from fastmcp import Client
from soft_floyd_server.mcp_server import mcp


async def test_tools_are_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    assert {
        "get_rider_profile",
        "set_rider_profile",
        "get_available_metrics",
        "list_activities",
    } <= names


async def test_mcp_and_rest_agree_on_capability_tier(client):
    """`client` here is the REST TestClient fixture from conftest.py — it
    already points SOFT_FLOYD_DB_PATH at an isolated tmp file, so both
    surfaces below read/write the same database.
    """
    client.put("/api/profile", json={"has_power_meter": True, "ftp_watts": 250})

    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("get_rider_profile", {})

    rest_profile = client.get("/api/profile").json()
    assert result.data.capability_tier == rest_profile["capability_tier"] == "power"
