"""REST routes for the web UI. Thin adapter over soft_floyd_core — same
rule as mcp_server.py: no domain logic here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from soft_floyd_core.activities import service as activities_service
from soft_floyd_core.auth import service as auth_service
from soft_floyd_core.bikes import service as bikes_service
from soft_floyd_core.coach import memory as coach_memory
from soft_floyd_core.coach import service as coach_service
from soft_floyd_core.config import get_settings
from soft_floyd_core.connections import service as connections_service
from soft_floyd_core.db import session_scope
from soft_floyd_core.garmin.errors import GarminApiError, GarminRateLimited
from soft_floyd_core.garmin.sync import (
    LoginAlreadyInProgress,
    LoginStartResult,
    NoPendingLoginError,
    SyncResult,
)
from soft_floyd_core.llm.usage import BudgetExceededError
from soft_floyd_core.log import get_logger
from soft_floyd_core.profile import service as profile_service
from soft_floyd_core.rag import service as rag_service

from soft_floyd_server.mcp_bridge import CoachMCPBridge
from soft_floyd_server.runtime import current_sync_runner, get_session_factory

router = APIRouter()
_log = get_logger(__name__)


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
    limit: int = 20,
    bike_type: str | None = None,
    before_start_time: dt.datetime | None = None,
    before_id: int | None = None,
) -> list[activities_service.ActivitySummaryOut]:
    if (before_start_time is None) != (before_id is None):
        raise HTTPException(status_code=422, detail="Both activity cursor fields are required")
    with session_scope(get_session_factory()) as session:
        return activities_service.list_activities(
            session,
            limit=limit,
            bike_type=bike_type,
            before_start_time=before_start_time,
            before_id=before_id,
        )


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
    return await current_sync_runner().sync_once()


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


@router.get("/training-summary", response_model=activities_service.TrainingSummaryOut)
def get_training_summary(weeks: int = 8) -> activities_service.TrainingSummaryOut:
    with session_scope(get_session_factory()) as session:
        return activities_service.get_training_summary(session, weeks)


@router.get("/bikes", response_model=list[bikes_service.BikeOut])
def list_bikes() -> list[bikes_service.BikeOut]:
    with session_scope(get_session_factory()) as session:
        return bikes_service.list_bikes(session)


@router.post("/bikes", response_model=bikes_service.BikeOut)
def add_bike(data: bikes_service.BikeIn) -> bikes_service.BikeOut:
    with session_scope(get_session_factory()) as session:
        return bikes_service.add_bike(session, data)


@router.patch("/bikes/{bike_id}", response_model=bikes_service.BikeOut)
def update_bike(bike_id: int, data: bikes_service.BikeIn) -> bikes_service.BikeOut:
    with session_scope(get_session_factory()) as session:
        try:
            return bikes_service.update_bike(session, bike_id, data)
        except bikes_service.BikeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/bikes/{bike_id}", status_code=204)
def delete_bike(bike_id: int) -> None:
    with session_scope(get_session_factory()) as session:
        try:
            bikes_service.delete_bike(session, bike_id)
        except bikes_service.BikeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except bikes_service.LastBikeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/connections", response_model=list[connections_service.ConnectionOut])
def list_connections() -> list[connections_service.ConnectionOut]:
    settings = get_settings()
    with session_scope(get_session_factory()) as session:
        return connections_service.list_connections(session, settings)


class GarminLoginIn(BaseModel):
    email: str
    password: str


class GarminMfaIn(BaseModel):
    code: str


def _map_garmin_login_error(exc: GarminApiError) -> HTTPException:
    status_code = 429 if isinstance(exc, GarminRateLimited) else 502
    return HTTPException(status_code=status_code, detail=str(exc))


@router.post("/connections/garmin/login", response_model=LoginStartResult)
async def garmin_login(data: GarminLoginIn) -> LoginStartResult:
    """Starts a Garmin login from the browser. The password lives only in
    this request body and the login worker thread's stack — it is never
    written to the DB, config, or a log line. See docs/SECURITY.md.
    """
    try:
        return await current_sync_runner().login(data.email, data.password)
    except LoginAlreadyInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GarminApiError as exc:
        raise _map_garmin_login_error(exc) from exc


@router.post("/connections/garmin/mfa", response_model=LoginStartResult)
async def garmin_submit_mfa(data: GarminMfaIn) -> LoginStartResult:
    try:
        return await current_sync_runner().submit_mfa(data.code)
    except NoPendingLoginError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GarminApiError as exc:
        raise _map_garmin_login_error(exc) from exc


@router.delete("/connections/garmin", status_code=204)
def garmin_disconnect() -> None:
    from soft_floyd_core.garmin.login import clear_login_block

    current_sync_runner().logout()
    with session_scope(get_session_factory()) as session:
        clear_login_block(session)


@router.get("/coach/conversations", response_model=list[coach_service.ConversationOut])
def list_coach_conversations() -> list[coach_service.ConversationOut]:
    with session_scope(get_session_factory()) as session:
        return coach_service.list_conversations(session)


@router.post("/coach/conversations", response_model=coach_service.ConversationOut)
def create_coach_conversation() -> coach_service.ConversationOut:
    with session_scope(get_session_factory()) as session:
        return coach_service.create_conversation(session)


@router.get(
    "/coach/conversations/{conversation_id}",
    response_model=coach_service.ConversationDetailOut,
)
def get_coach_conversation(conversation_id: int) -> coach_service.ConversationDetailOut:
    with session_scope(get_session_factory()) as session:
        try:
            return coach_service.get_conversation(session, conversation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/coach/conversations/{conversation_id}", status_code=204)
def delete_coach_conversation(conversation_id: int) -> None:
    with session_scope(get_session_factory()) as session:
        try:
            coach_service.delete_conversation(session, conversation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


class CoachMessageIn(BaseModel):
    text: str


def _sse(event: coach_service.CoachEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json(exclude_none=True)}\n\n"


@router.post("/coach/conversations/{conversation_id}/messages")
async def send_coach_message(
    conversation_id: int, data: CoachMessageIn, request: Request
) -> StreamingResponse:
    """Streams the coach's reply as Server-Sent Events: `delta` (text),
    `tool_status`, `sources`, then `done` with the saved message — or
    `error`. Anything that can reject the turn is checked first so it
    still gets a real status code instead of a 200 stream.
    """
    settings = get_settings()
    llm = coach_service.make_coach_llm(settings.openai_api_key)
    if llm is None:
        raise HTTPException(
            status_code=400, detail="SOFT_FLOYD_OPENAI_API_KEY is required for the coach"
        )
    with session_scope(get_session_factory()) as session:
        try:
            coach_service.check_turn(
                session, conversation_id, data.text, settings.llm_monthly_budget_usd
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BudgetExceededError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        mcp_token = auth_service.issue_mcp_token(
            session, settings, request.cookies["soft_floyd_session"]
        )

    async def stream() -> AsyncIterator[str]:
        try:
            async with CoachMCPBridge(settings, mcp_token) as bridge:
                with session_scope(get_session_factory()) as session:
                    async for event in coach_service.run_turn(
                        session,
                        conversation_id,
                        data.text,
                        llm,
                        settings.llm_monthly_budget_usd,
                        tool_runner=bridge.run,
                        context_provider=bridge.context,
                    ):
                        yield _sse(event)
        except (ValueError, LookupError) as exc:  # the stream is already 200; report in-band
            yield _sse(coach_service.CoachEvent(type="error", text=str(exc)))
        except Exception as exc:
            _log.warning("coach_turn_failed", error_type=type(exc).__name__)
            detail = "The coach hit an error talking to the model. Please try again."
            yield _sse(coach_service.CoachEvent(type="error", text=detail))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/coach/memory", response_model=list[coach_memory.MemoryNoteOut])
def list_coach_memory() -> list[coach_memory.MemoryNoteOut]:
    with session_scope(get_session_factory()) as session:
        return coach_memory.list_notes(session)


@router.delete("/coach/memory/{note_id}", status_code=204)
def delete_coach_memory(note_id: int) -> None:
    with session_scope(get_session_factory()) as session:
        try:
            coach_memory.delete_note(session, note_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
