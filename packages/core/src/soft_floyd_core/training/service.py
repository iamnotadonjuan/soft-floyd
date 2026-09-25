"""CRUD, generation orchestration, export and Garmin push for training
sessions — the one surface REST/MCP/coach adapters call, same rule as
every other `*/service.py` in this repo (AGENTS.md's core/adapter
layering). `intent.py`, `generator.py`, `sanitize.py` and `export.py` stay
narrow; this module wires them together and owns persistence.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.activities.service import get_training_summary, list_activities
from soft_floyd_core.bikes.service import BikeOut, list_bikes
from soft_floyd_core.garmin.sync import SyncRunner
from soft_floyd_core.llm.client import LLMClient
from soft_floyd_core.models import TrainingSession
from soft_floyd_core.profile.service import ProfileOut, get_profile
from soft_floyd_core.rag.service import Embedder, PassageOut
from soft_floyd_core.training import export as export_mod
from soft_floyd_core.training.generator import GeneratorResult
from soft_floyd_core.training.generator import generate_session as _run_generator
from soft_floyd_core.training.intent import recommend_intent
from soft_floyd_core.training.schemas import (
    SessionIntent,
    SessionRequest,
    SessionSourceOut,
    SessionStatus,
    Workout,
)

_SUMMARY_WEEKS = 8
_RECENT_RIDES = 5


def make_training_llm(api_key: str | None) -> LLMClient | None:
    """Same shape as coach.service.make_coach_llm — a monkeypatch seam for
    adapter tests, and the one place a missing key becomes None instead
    of a constructor error."""
    return LLMClient(api_key) if api_key else None


class SessionNotFoundError(Exception):
    pass


class ExportNotAvailableError(Exception):
    pass


class TrainingSessionOut(BaseModel):
    id: int
    planned_date: dt.date
    bike_id: int | None
    setting: str
    discipline: str
    request: SessionRequest
    intent: SessionIntent
    workout: Workout
    rationale: str
    adjustments: str | None
    sources: list[SessionSourceOut]
    status: SessionStatus
    garmin_workout_id: str | None
    sent_to_garmin_at: dt.datetime | None
    available_export_formats: list[str]
    created_at: dt.datetime
    updated_at: dt.datetime


def _bike_out(bikes: list[BikeOut], bike_id: int | None) -> BikeOut | None:
    return next((b for b in bikes if b.id == bike_id), None)


def _pick_bike(request: SessionRequest, bikes: list[BikeOut]) -> BikeOut | None:
    """The bike a session's targets get sanitized against. An explicit
    bike_id wins; otherwise an indoor session prefers the `indoor` bike,
    an outdoor one prefers a bike of the matching discipline (its primary
    if there's more than one), falling back to the garage's primary bike
    so a request never has to name one just to get sensor-honest targets.
    """
    if request.bike_id is not None:
        return _bike_out(bikes, request.bike_id)
    if request.setting == "indoor":
        indoor = next((b for b in bikes if b.kind == "indoor"), None)
        if indoor is not None:
            return indoor
    matching = [b for b in bikes if b.kind == request.discipline]
    if matching:
        return next((b for b in matching if b.is_primary), matching[0])
    return next((b for b in bikes if b.is_primary), bikes[0] if bikes else None)


def _export_formats(profile: ProfileOut, bike: BikeOut | None) -> list[str]:
    """`.fit` always works (every step falls back to a plain cue if it has
    no target). `.zwo`/`.erg` are ERG-style formats — every second needs
    *some* wattage — so they're only offered when the rider actually has
    a power meter and FTP to fill gaps from; see export.py's docstring.
    """
    formats = ["fit"]
    if bike is not None and bike.has_power_meter and profile.ftp_watts:
        formats += ["zwo", "erg"]
    return formats


def _sources_json(passages: list[PassageOut]) -> list[dict]:
    return [
        json.loads(
            SessionSourceOut(
                book_id=p.book_id,
                title=p.title,
                author=p.author,
                page_start=p.page_start,
                page_end=p.page_end,
            ).model_dump_json()
        )
        for p in passages
    ]


def _to_out(row: TrainingSession, *, export_formats: list[str]) -> TrainingSessionOut:
    return TrainingSessionOut(
        id=row.id,
        planned_date=row.planned_date,
        bike_id=row.bike_id,
        setting=row.setting,
        discipline=row.discipline,
        request=SessionRequest.model_validate(row.request),
        intent=SessionIntent.model_validate(row.intent),
        workout=Workout.model_validate(row.workout),
        rationale=row.rationale,
        adjustments=row.adjustments,
        sources=[SessionSourceOut.model_validate(s) for s in row.sources or []],
        status=row.status,  # type: ignore[arg-type]
        garmin_workout_id=row.garmin_workout_id,
        sent_to_garmin_at=row.sent_to_garmin_at,
        available_export_formats=export_formats,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get(session: Session, training_session_id: int) -> TrainingSession:
    row = session.get(TrainingSession, training_session_id)
    if row is None:
        raise SessionNotFoundError(f"No training session with id {training_session_id}")
    return row


def _out_for_row(session: Session, row: TrainingSession) -> TrainingSessionOut:
    profile = get_profile(session)
    bikes = list_bikes(session)
    return _to_out(row, export_formats=_export_formats(profile, _bike_out(bikes, row.bike_id)))


def list_sessions(session: Session) -> list[TrainingSessionOut]:
    profile = get_profile(session)
    bikes = list_bikes(session)
    rows = session.scalars(
        select(TrainingSession).order_by(
            TrainingSession.planned_date.desc(), TrainingSession.id.desc()
        )
    ).all()
    return [
        _to_out(row, export_formats=_export_formats(profile, _bike_out(bikes, row.bike_id)))
        for row in rows
    ]


def get_session(session: Session, training_session_id: int) -> TrainingSessionOut:
    return _out_for_row(session, _get(session, training_session_id))


async def _build(
    session: Session,
    llm: LLMClient,
    embedder: Embedder | None,
    request: SessionRequest,
    bike: BikeOut | None,
    *,
    budget_usd: float,
    now: dt.datetime | None,
) -> tuple[SessionIntent, GeneratorResult]:
    profile = get_profile(session)
    today = (now or dt.datetime.now(dt.UTC)).date()
    summary = get_training_summary(session, weeks=_SUMMARY_WEEKS, now=now)
    recent_rides = list_activities(session, limit=_RECENT_RIDES)
    intent = recommend_intent(request, profile, summary, recent_rides, today=today)
    result = await _run_generator(
        session,
        llm,
        embedder,
        request=request,
        intent=intent,
        profile=profile,
        bike=bike,
        budget_usd=budget_usd,
    )
    return intent, result


async def plan_session(
    session: Session,
    llm: LLMClient,
    embedder: Embedder | None,
    request: SessionRequest,
    *,
    budget_usd: float,
    now: dt.datetime | None = None,
) -> TrainingSessionOut:
    bikes = list_bikes(session)
    bike = _pick_bike(request, bikes)
    if request.bike_id is None and bike is not None:
        request = request.model_copy(update={"bike_id": bike.id})

    intent, result = await _build(
        session, llm, embedder, request, bike, budget_usd=budget_usd, now=now
    )

    row = TrainingSession(
        planned_date=request.planned_date,
        bike_id=bike.id if bike is not None else None,
        setting=request.setting,
        discipline=request.discipline,
        request=json.loads(request.model_dump_json()),
        intent=json.loads(intent.model_dump_json()),
        workout=json.loads(result.workout.model_dump_json()),
        rationale=result.rationale,
        adjustments=result.adjustments,
        sources=_sources_json(result.passages),
    )
    session.add(row)
    session.flush()
    return _out_for_row(session, row)


async def regenerate_session(
    session: Session,
    llm: LLMClient,
    embedder: Embedder | None,
    training_session_id: int,
    *,
    budget_usd: float,
    now: dt.datetime | None = None,
) -> TrainingSessionOut:
    row = _get(session, training_session_id)
    request = SessionRequest.model_validate(row.request)
    bikes = list_bikes(session)
    bike = _bike_out(bikes, row.bike_id)

    intent, result = await _build(
        session, llm, embedder, request, bike, budget_usd=budget_usd, now=now
    )

    row.intent = json.loads(intent.model_dump_json())
    row.workout = json.loads(result.workout.model_dump_json())
    row.rationale = result.rationale
    row.adjustments = result.adjustments
    row.sources = _sources_json(result.passages)
    # A regenerated workout is a different document — don't leave a stale
    # Garmin workout silently out of sync with what the rider now sees.
    row.garmin_workout_id = None
    row.sent_to_garmin_at = None
    session.flush()
    return _out_for_row(session, row)


def update_status(
    session: Session, training_session_id: int, status: SessionStatus
) -> TrainingSessionOut:
    row = _get(session, training_session_id)
    row.status = status
    session.flush()
    return _out_for_row(session, row)


def delete_session(session: Session, training_session_id: int) -> None:
    session.delete(_get(session, training_session_id))
    session.flush()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workout"


def export_session(session: Session, training_session_id: int, fmt: str) -> tuple[bytes, str, str]:
    """Returns (content, content_type, filename)."""
    row = _get(session, training_session_id)
    profile = get_profile(session)
    bikes = list_bikes(session)
    bike = _bike_out(bikes, row.bike_id)
    if fmt not in _export_formats(profile, bike):
        raise ExportNotAvailableError(f"{fmt} export isn't available for this session")

    workout = Workout.model_validate(row.workout)
    slug = _slugify(workout.name)
    if fmt == "fit":
        return export_mod.to_fit_workout(workout), "application/octet-stream", f"{slug}.fit"
    if fmt == "zwo":
        assert profile.ftp_watts is not None  # guaranteed by _export_formats's gate
        zwo = export_mod.to_zwo(workout, ftp_watts=profile.ftp_watts)
        return zwo.encode(), "application/xml", f"{slug}.zwo"
    if fmt == "erg":
        assert profile.ftp_watts is not None
        erg = export_mod.to_erg(workout, ftp_watts=profile.ftp_watts)
        return erg.encode(), "text/plain", f"{slug}.erg"
    raise ExportNotAvailableError(f"Unknown export format {fmt!r}")


async def send_to_garmin(
    session: Session, training_session_id: int, sync_runner: SyncRunner
) -> TrainingSessionOut:
    row = _get(session, training_session_id)
    workout = Workout.model_validate(row.workout)
    payload = export_mod.to_garmin_payload(workout)
    workout_id = await sync_runner.send_workout(payload, row.planned_date, row.garmin_workout_id)
    row.garmin_workout_id = workout_id
    row.sent_to_garmin_at = dt.datetime.now(dt.UTC)
    session.flush()
    return _out_for_row(session, row)
