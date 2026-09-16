"""REST routes for the web UI. Thin adapter over soft_floyd_core — same
rule as mcp_server.py: no domain logic here.
"""

from __future__ import annotations

from fastapi import APIRouter
from soft_floyd_core.db import session_scope
from soft_floyd_core.profile import service as profile_service

from soft_floyd_server.runtime import get_session_factory

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/profile", response_model=profile_service.ProfileOut)
def get_profile() -> profile_service.ProfileOut:
    with session_scope(get_session_factory()) as session:
        return profile_service.get_profile(session)


@router.put("/profile", response_model=profile_service.ProfileOut)
def put_profile(data: profile_service.ProfileIn) -> profile_service.ProfileOut:
    with session_scope(get_session_factory()) as session:
        return profile_service.upsert_profile(session, data)


@router.get("/activities")
def list_activities(limit: int = 20, discipline: str | None = None) -> list[dict]:
    """Always empty until Garmin sync ships — see docs/product-specs/garmin-sync.md."""
    return []
