"""Profile and daily-summary FastAPI routes (Phase 4)."""

from __future__ import annotations

import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from coach.store.models import DailySummary, RiderProfile
from coach.store.session import get_sync_session

GOAL_SLUG = Literal["climbing", "descending", "endurance", "sprinting", "intervals", "recovery"]

router = APIRouter()


class RiderProfileIn(BaseModel):
    discipline: Literal["road", "mtb", "gravel"]
    city: str | None = None
    country: str | None = None
    terrain_notes: str | None = None
    goals: list[GOAL_SLUG] = []
    freeform_notes: str | None = None


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get("/api/profile")
def get_profile():
    session = get_sync_session()
    try:
        row = session.get(RiderProfile, 1)
        if row is None:
            raise HTTPException(status_code=404, detail="Profile not set")
        return {
            "discipline": row.discipline,
            "city": row.city,
            "country": row.country,
            "terrain_notes": row.terrain_notes,
            "goals": row.goals,
            "freeform_notes": row.freeform_notes,
            "updated_at": row.updated_at.isoformat(),
        }
    finally:
        session.close()


@router.put("/api/profile")
def put_profile(body: RiderProfileIn):
    session = get_sync_session()
    try:
        row = session.get(RiderProfile, 1)
        if row is None:
            row = RiderProfile(id=1)
            session.add(row)
        row.discipline = body.discipline
        row.city = body.city
        row.country = body.country
        row.terrain_notes = body.terrain_notes
        row.goals = list(body.goals)
        row.freeform_notes = body.freeform_notes
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------


@router.get("/api/summary/daily")
def get_daily_summary(date: str | None = Query(None)):
    session = get_sync_session()
    try:
        target = datetime.date.fromisoformat(date) if date else datetime.date.today()
        row = session.execute(
            select(DailySummary).where(DailySummary.date == target)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No summary for that date")
        return {
            "date": str(row.date),
            "text": row.text,
            "generated_at": row.generated_at.isoformat(),
            "cost_usd": row.cost_usd,
        }
    finally:
        session.close()


@router.post("/api/summary/daily")
async def post_daily_summary(date: str | None = Query(None)):
    """Force-generate (or regenerate) today's readiness summary."""
    from coach.agent.daily import generate_daily_summary
    from coach.config import get_config

    cfg = get_config()
    if not cfg.openai_api_key:
        raise HTTPException(status_code=503, detail="COACH_OPENAI_API_KEY not configured")

    session = get_sync_session()
    try:
        target = datetime.date.fromisoformat(date) if date else datetime.date.today()
        summary = await generate_daily_summary(session, cfg, target)
        return {"date": str(summary.date), "text": summary.text, "cost_usd": summary.cost_usd}
    finally:
        session.close()
