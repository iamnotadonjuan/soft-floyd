"""Tests for agent/daily.py — build_daily_context and generate_daily_summary.

No real OpenAI calls; generate_daily_summary is tested via a mock client.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from coach.store.models import (
    Activity,
    Base,
    DailySummary,
    RiderProfile,
    WellnessDaily,
)


# ---------------------------------------------------------------------------
# In-memory DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_wellness(date: datetime.date = datetime.date(2026, 5, 20)) -> WellnessDaily:
    return WellnessDaily(
        date=date,
        hrv_overnight=55,
        sleep_score=80,
        resting_hr=48,
        body_battery_low=20,
        body_battery_high=85,
        acwr=0.85,
    )


def _make_activity(
    activity_id: int = 1,
    date: datetime.date = datetime.date(2026, 5, 19),
    tss_proxy: float = 70.0,
) -> Activity:
    return Activity(
        id=activity_id,
        start_time=datetime.datetime.combine(date, datetime.time(8, 0), tzinfo=datetime.UTC),
        sport="cycling",
        sub_sport="road",
        is_indoor=False,
        bike_type="road",
        distance_m=50_000,
        duration_s=7_200,
        elev_gain_m=500,
        avg_hr=140,
        max_hr=175,
        tss_proxy=tss_proxy,
    )


# ---------------------------------------------------------------------------
# build_daily_context — structure tests
# ---------------------------------------------------------------------------


def test_build_daily_context_no_data(db_session):
    """When there is no wellness or activity data, context should still be valid."""
    from coach.agent.daily import build_daily_context

    ctx = build_daily_context(db_session, datetime.date(2026, 5, 20))
    assert "## Date:" in ctx
    assert "no data available" in ctx or "no activities" in ctx


def test_build_daily_context_with_wellness(db_session):
    from coach.agent.daily import build_daily_context

    target = datetime.date(2026, 5, 20)
    db_session.add(_make_wellness(target))
    db_session.commit()

    ctx = build_daily_context(db_session, target)
    assert "HRV overnight: 55" in ctx
    assert "Sleep score: 80" in ctx
    assert "RHR: 48 bpm" in ctx


def test_build_daily_context_with_activity(db_session):
    from coach.agent.daily import build_daily_context

    target = datetime.date(2026, 5, 20)
    yesterday = target - datetime.timedelta(days=1)
    db_session.add(_make_activity(date=yesterday))
    db_session.commit()

    ctx = build_daily_context(db_session, target)
    assert "Recent Load" in ctx
    assert "road" in ctx


def test_build_daily_context_includes_profile(db_session):
    from coach.agent.daily import build_daily_context

    target = datetime.date(2026, 5, 20)
    row = RiderProfile(id=1, discipline="road", city="Medellín", country="CO")
    row.goals = ["climbing", "endurance"]
    row.updated_at = datetime.datetime.now(datetime.UTC)
    db_session.add(row)
    db_session.commit()

    ctx = build_daily_context(db_session, target)
    assert "Medellín" in ctx


def test_build_daily_context_no_profile_placeholder(db_session):
    from coach.agent.daily import build_daily_context

    ctx = build_daily_context(db_session, datetime.date(2026, 5, 20))
    assert "no rider profile set" in ctx


# ---------------------------------------------------------------------------
# generate_daily_summary — mocked OpenAI call
# ---------------------------------------------------------------------------


def _fake_openai_response(text: str = "You're well-rested. Go ride."):
    """Build a minimal OpenAI response-shaped object."""
    usage = SimpleNamespace(
        prompt_tokens=500,
        completion_tokens=80,
        prompt_tokens_details=SimpleNamespace(cached_tokens=400),
    )
    choice = SimpleNamespace(message=SimpleNamespace(content=text))
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.mark.asyncio
async def test_generate_daily_summary_writes_row(db_session):
    """generate_daily_summary should persist a DailySummary row with text and cost."""
    from coach.agent.daily import generate_daily_summary
    from coach.config import Config

    cfg = MagicMock(spec=Config)
    cfg.openai_api_key = "test-key"

    fake_response = _fake_openai_response("Solid HRV. Keep the effort light today.")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

    target = datetime.date(2026, 5, 20)
    db_session.add(_make_wellness(target))
    db_session.commit()

    with patch("coach.agent.daily.openai.AsyncOpenAI", return_value=mock_client):
        summary = await generate_daily_summary(db_session, cfg, target)

    assert isinstance(summary, DailySummary)
    assert summary.text == "Solid HRV. Keep the effort light today."
    assert summary.tokens_in == 500
    assert summary.tokens_out == 80
    assert summary.cache_read == 400
    assert summary.cost_usd is not None
    assert summary.cost_usd > 0


@pytest.mark.asyncio
async def test_generate_daily_summary_upserts_on_second_call(db_session):
    """Calling generate_daily_summary twice should update the row, not create a second one."""
    from sqlalchemy import select

    from coach.agent.daily import generate_daily_summary
    from coach.config import Config

    cfg = MagicMock(spec=Config)
    cfg.openai_api_key = "test-key"

    target = datetime.date(2026, 5, 20)

    for text in ["First summary.", "Updated summary."]:
        fake_response = _fake_openai_response(text)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
        with patch("coach.agent.daily.openai.AsyncOpenAI", return_value=mock_client):
            await generate_daily_summary(db_session, cfg, target)

    rows = list(db_session.execute(select(DailySummary)).scalars())
    assert len(rows) == 1
    assert rows[0].text == "Updated summary."


@pytest.mark.asyncio
async def test_generate_daily_summary_cost_positive(db_session):
    """Even with all-cached tokens, cost_usd should be a non-negative float."""
    from coach.agent.daily import generate_daily_summary
    from coach.config import Config

    cfg = MagicMock(spec=Config)
    cfg.openai_api_key = "test-key"

    # Simulate fully cached prompt (cache_read == prompt_tokens)
    usage = SimpleNamespace(
        prompt_tokens=500,
        completion_tokens=80,
        prompt_tokens_details=SimpleNamespace(cached_tokens=500),
    )
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Cached response."))],
        usage=usage,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

    target = datetime.date(2026, 5, 20)
    with patch("coach.agent.daily.openai.AsyncOpenAI", return_value=mock_client):
        summary = await generate_daily_summary(db_session, cfg, target)

    assert summary.cost_usd >= 0.0


# ---------------------------------------------------------------------------
# _context_block — profile block emitted or omitted
# ---------------------------------------------------------------------------


def test_context_block_includes_profile_when_present():
    from unittest.mock import MagicMock

    from coach.agent.coach import _context_block
    from coach.rag.retriever import RetrievalContext

    ctx = MagicMock(spec=RetrievalContext)
    ctx.profile_summary = "Discipline: road. Goals: climbing."
    ctx.current_card = "## Current Ride\nSome ride data."
    ctx.similar_cards = []
    ctx.recent_cards = []
    ctx.wellness_summary = None

    block = _context_block(ctx)
    assert "## Rider Profile" in block
    assert "Discipline: road" in block


def test_context_block_omits_profile_when_none():
    from unittest.mock import MagicMock

    from coach.agent.coach import _context_block
    from coach.rag.retriever import RetrievalContext

    ctx = MagicMock(spec=RetrievalContext)
    ctx.profile_summary = None
    ctx.current_card = "## Current Ride\nSome ride data."
    ctx.similar_cards = []
    ctx.recent_cards = []
    ctx.wellness_summary = None

    block = _context_block(ctx)
    assert "## Rider Profile" not in block
