"""Exercises the MCP surface in-process (no HTTP), and checks it agrees
with the REST surface on the same underlying profile — the point of
sharing soft_floyd_core between both adapters.
"""

from fastmcp import Client
from pydantic import TypeAdapter
from soft_floyd_server.mcp_server import mcp


def _as_json(obj):
    """FastMCP reconstructs a tool's structured result as a dynamically
    generated dataclass ("Root"), not the original Pydantic/dataclass
    type — it has no .model_dump(). TypeAdapter handles both Pydantic
    models and plain dataclasses uniformly, including datetime -> ISO
    string, matching what the REST side's .json() already produced.
    """
    return TypeAdapter(type(obj)).dump_python(obj, mode="json")


async def test_tools_are_registered():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    assert {
        "get_rider_profile",
        "set_rider_profile",
        "get_available_metrics",
        "list_bikes",
        "add_bike",
        "update_bike",
        "delete_bike",
        "get_connections",
        "list_activities",
        "get_activity",
        "sync_garmin_now",
        "get_garmin_sync_status",
    } <= names
    # Deliberate: a Garmin login takes a password, which never belongs
    # behind an LLM tool-call. Browser-only, see http_api.py — exec-plan 0004.
    assert "garmin_login" not in names
    assert "submit_garmin_mfa" not in names


async def test_mcp_and_rest_agree_on_capability_tier(client):
    """`client` here is the REST TestClient fixture from conftest.py — it
    already points SOFT_FLOYD_DB_PATH at an isolated tmp file, so both
    surfaces below read/write the same database.
    """
    client.post("/api/bikes", json={"kind": "road", "has_power_meter": True})
    client.put("/api/profile", json={"ftp_watts": 250})

    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("get_rider_profile", {})

    rest_profile = client.get("/api/profile").json()
    assert result.data.capability_tier == rest_profile["capability_tier"] == "power"


async def test_mcp_and_rest_agree_on_usual_ride_days(client):
    rest_profile = client.put("/api/profile", json={"available_days": ["tue", "thu", "sat"]}).json()
    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("get_rider_profile", {})
    assert result.data.weekly_rides == rest_profile["weekly_rides"] == 3


async def test_mcp_and_rest_agree_on_bikes(client):
    client.post("/api/bikes", json={"kind": "road", "has_power_meter": True})
    client.post("/api/bikes", json={"kind": "mtb"})

    rest_bikes = client.get("/api/bikes").json()

    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("list_bikes", {})

    mcp_bikes = [_as_json(b) for b in result.data]
    assert mcp_bikes == rest_bikes


async def test_mcp_and_rest_agree_on_connections(client):
    rest_connections = client.get("/api/connections").json()

    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("get_connections", {})

    mcp_connections = [_as_json(c) for c in result.data]
    assert mcp_connections == rest_connections


async def test_mcp_and_rest_agree_on_activity_list(client, road_fit_path):
    """Same drift guard as the profile test above, extended to the new
    activities surface — seed one ride, confirm MCP and REST serialize
    the same data (see ARCHITECTURE.md's load-bearing constraint).
    """
    from soft_floyd_core.activities.pipeline import ingest_activity
    from soft_floyd_core.config import get_settings
    from soft_floyd_core.db import session_scope
    from soft_floyd_server.runtime import get_session_factory

    class _FakeFitSource:
        def download_fit(self, activity_id, dest_path):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(road_fit_path.read_bytes())
            return dest_path

    summary = {"activityId": 1, "startTimeLocal": "2026-04-15T08:00:00", "isIndoor": False}
    with session_scope(get_session_factory()) as session:
        ingest_activity(session, get_settings(), _FakeFitSource(), summary)

    rest_activities = client.get("/api/activities").json()

    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("list_activities", {})

    mcp_activities = [_as_json(a) for a in result.data]
    assert mcp_activities == rest_activities


async def test_mcp_and_rest_agree_on_activity_cursor(client, road_fit_path):
    from tests.test_activities_api import _seed_activity

    _seed_activity(1, road_fit_path)
    _seed_activity(2, road_fit_path)
    cursor = client.get("/api/activities", params={"limit": 1}).json()[0]
    args = {
        "limit": 1,
        "before_start_time": cursor["start_time"],
        "before_id": cursor["id"],
    }
    rest_activities = client.get("/api/activities", params=args).json()
    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("list_activities", args)
    assert [_as_json(ride) for ride in result.data] == rest_activities


async def test_mcp_and_rest_agree_on_sync_result(client, monkeypatch):
    """Patches the shared SyncRunner (both surfaces call get_sync_runner())
    to return a fixed SyncResult, so this asserts serialization agreement
    without touching Garmin at all.

    Both mcp_server.py and http_api.py did `from runtime import
    get_sync_runner` — each module holds its own local binding to that
    function object, so patching `runtime.get_sync_runner` alone would
    miss both. Patch each module's own name instead.
    """
    from soft_floyd_core.garmin.sync import SyncResult
    from soft_floyd_server import http_api, mcp_server

    fixed = SyncResult(new_activity_ids=[42], skipped=1, status="ok", message=None)

    class _FakeRunner:
        async def sync_once(self):
            return fixed

    monkeypatch.setattr(mcp_server, "get_sync_runner", lambda: _FakeRunner())
    monkeypatch.setattr(http_api, "get_sync_runner", lambda: _FakeRunner())

    rest_result = client.post("/api/sync/garmin").json()

    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("sync_garmin_now", {})

    assert _as_json(result.data) == rest_result
