"""MCP tools — the primary surface. Each tool is a one-line call into
soft_floyd_core; no domain logic lives here (see ARCHITECTURE.md).
"""

from __future__ import annotations

from fastmcp import FastMCP
from soft_floyd_core.db import session_scope
from soft_floyd_core.profile import service as profile_service

from soft_floyd_server.runtime import get_session_factory

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
def list_activities(limit: int = 20, discipline: str | None = None) -> list[dict]:
    """List recent rides. Always empty until Garmin sync ships — see
    docs/product-specs/garmin-sync.md.
    """
    return []
