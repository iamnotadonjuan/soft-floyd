"""REST routes for the web UI. Thin adapter over soft_floyd_core — same
rule as mcp_server.py: no domain logic here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from soft_floyd_core.activities import service as activities_service
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import session_scope
from soft_floyd_core.garmin.sync import SyncResult
from soft_floyd_core.profile import service as profile_service
from soft_floyd_core.rag import service as rag_service

from soft_floyd_server.runtime import get_session_factory, get_sync_runner

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


@router.get("/activities", response_model=list[activities_service.ActivitySummaryOut])
def list_activities(
    limit: int = 20, bike_type: str | None = None
) -> list[activities_service.ActivitySummaryOut]:
    with session_scope(get_session_factory()) as session:
        return activities_service.list_activities(session, limit=limit, bike_type=bike_type)


@router.get("/activities/{activity_id}", response_model=activities_service.ActivityDetailOut)
def get_activity(activity_id: int) -> activities_service.ActivityDetailOut:
    with session_scope(get_session_factory()) as session:
        detail = activities_service.get_activity(session, activity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return detail


@router.post("/sync/garmin", response_model=SyncResult)
async def sync_garmin() -> SyncResult:
    """200 even on reauth_required/rate_limited — the request succeeded,
    the sync didn't; `status` says which. Keeps this identical to the MCP
    tool's return shape, which the cross-surface agreement test asserts.
    """
    return await get_sync_runner().sync_once()


@router.get("/sync/garmin/status", response_model=activities_service.SyncStatusOut)
def sync_garmin_status() -> activities_service.SyncStatusOut:
    settings = get_settings()
    with session_scope(get_session_factory()) as session:
        return activities_service.get_sync_status(session, settings)


@router.get("/training-context", response_model=rag_service.TrainingContextOut)
async def get_training_context(
    query: str, activity_id: int | None = None
) -> rag_service.TrainingContextOut:
    settings = get_settings()
    try:
        with session_scope(get_session_factory()) as session:
            return await rag_service.get_training_context(
                session, query, rag_service.make_embedder(settings.openai_api_key), activity_id
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
