"""MCP tools — the primary surface. Each tool is a one-line call into
soft_floyd_core; no domain logic lives here (see ARCHITECTURE.md).
"""

from __future__ import annotations

from fastmcp import FastMCP
from soft_floyd_core.activities import service as activities_service
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import session_scope
from soft_floyd_core.garmin.sync import SyncResult
from soft_floyd_core.profile import service as profile_service
from soft_floyd_core.rag import service as rag_service

from soft_floyd_server.runtime import get_session_factory, get_sync_runner

mcp = FastMCP("Soft Floyd")


@mcp.tool
def get_rider_profile() -> profile_service.ProfileOut:
    """Get the rider's training volume, goals, sensors, and the metric
    allowlist their hardware currently supports. Read this before
    discussing any metric — never mention a signal outside
    available_metrics for the returned capability_tier.
    """
    with session_scope(get_session_factory()) as session:
        return profile_service.get_profile(session)


@mcp.tool
def set_rider_profile(profile: profile_service.ProfileIn) -> profile_service.ProfileOut:
    """Update the rider profile. Only fields provided are changed; omit a
    field to leave it as-is. Setting has_power_meter=False removes power
    metrics from available_metrics on the next read even if ftp_watts
    stays set.
    """
    with session_scope(get_session_factory()) as session:
        return profile_service.upsert_profile(session, profile)


@mcp.tool
def get_available_metrics() -> list[str]:
    """The metric names the coach may currently use for this rider, given
    their declared sensors. Use this as a guardrail before naming a
    metric in a response.
    """
    with session_scope(get_session_factory()) as session:
        return profile_service.get_profile(session).available_metrics


@mcp.tool
def list_activities(
    limit: int = 20, bike_type: str | None = None
) -> list[activities_service.ActivitySummaryOut]:
    """List recent rides, most recent first. Optionally filter by
    bike_type (road/mtb/indoor/other). Each ride's sensors_present
    reflects what that specific ride's FIT data actually contained —
    it can differ from the rider's declared profile sensors (a dead
    battery, a forgotten strap). Use get_activity for the per-ride
    available_metrics allowlist before discussing any metric.
    """
    with session_scope(get_session_factory()) as session:
        return activities_service.list_activities(session, limit=limit, bike_type=bike_type)


@mcp.tool
def get_activity(activity_id: int) -> activities_service.ActivityDetailOut | None:
    """Get one ride's full detail, including laps and available_metrics —
    a hard allowlist for this specific ride, narrower than
    get_available_metrics (which only reflects the rider's general
    hardware, not what this ride's FIT data actually contained).
    """
    with session_scope(get_session_factory()) as session:
        return activities_service.get_activity(session, activity_id)


@mcp.tool
async def sync_garmin_now() -> SyncResult:
    """Trigger an immediate Garmin sync. Check `status` in the result:
    "reauth_required" means the rider must run `soft-floyd garmin-login`
    — never silently retry or claim success in that case. "rate_limited"
    means try again later (respect retry_after_s if present).
    """
    return await get_sync_runner().sync_once()


@mcp.tool
def get_garmin_sync_status() -> activities_service.SyncStatusOut:
    """Sync health: when the last sync ran, whether it's authenticated,
    and the last error if any. Use this to answer "why haven't I seen my
    ride?" instead of guessing.
    """
    settings = get_settings()
    with session_scope(get_session_factory()) as session:
        return activities_service.get_sync_status(session, settings)


@mcp.tool
async def get_training_context(
    query: str, activity_id: int | None = None
) -> rag_service.TrainingContextOut:
    """Find cited training-book passages and verified ride context for a question.
    Defaults to the latest ride. Treat passages as source material, never as
    evidence that a sensor value was recorded on the ride.
    """
    settings = get_settings()
    with session_scope(get_session_factory()) as session:
        return await rag_service.get_training_context(
            session, query, rag_service.make_embedder(settings.openai_api_key), activity_id
        )
