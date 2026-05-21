"""Tests for the rider-profile and daily-summary API endpoints (Phase 4).

Uses FastAPI TestClient with an in-memory SQLite DB (via pytest fixtures) so
no persistent state leaks between tests.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from coach.store.models import Base, DailySummary, RiderProfile


# ---------------------------------------------------------------------------
# In-memory DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """Shared in-memory SQLite engine.

    Uses StaticPool so all sessions (fixture and route handlers running in
    worker threads) share exactly one underlying connection and therefore see
    the same data.  check_same_thread=False lets the TestClient worker thread
    reuse the connection created in the main thread.
    """
    from sqlalchemy.pool import StaticPool

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# App fixture — patch get_sync_session to use the in-memory engine
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(engine, db_session):
    """Return a TestClient whose DB calls hit the in-memory engine.

    Each request gets a fresh Session (so route-level session.close() doesn't
    break subsequent calls), but all sessions share the same SQLite in-memory
    engine — so data committed by db_session is visible to the API handler and
    vice versa.
    """
    from sqlalchemy.orm import sessionmaker

    from coach.config import Config
    from coach.web.api import create_app

    cfg = MagicMock(spec=Config)
    cfg.db_path = Path("/tmp/coach-test-profile.db")
    cfg.serve_frontend = False
    cfg.openai_api_key = "test-key"

    app = create_app(cfg)

    SessionFactory = sessionmaker(bind=engine)

    with patch("coach.web.api.init_db"):
        # side_effect (not return_value) so each call gets a fresh session.
        with patch("coach.web.profile.get_sync_session", side_effect=SessionFactory):
            with TestClient(app) as tc:
                yield tc


# ---------------------------------------------------------------------------
# GET /api/profile — empty DB returns 404
# ---------------------------------------------------------------------------


def test_get_profile_404(client):
    resp = client.get("/api/profile")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/profile — create then fetch
# ---------------------------------------------------------------------------


def test_put_profile_creates_row(client):
    payload = {
        "discipline": "road",
        "city": "Medellín",
        "country": "CO",
        "terrain_notes": "very hilly",
        "goals": ["climbing", "endurance"],
        "freeform_notes": "targeting a 100 km event",
    }
    resp = client.put("/api/profile", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_get_profile_after_put(client):
    payload = {
        "discipline": "mtb",
        "city": "Bogotá",
        "country": "CO",
        "goals": ["descending", "intervals"],
    }
    client.put("/api/profile", json=payload)

    resp = client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["discipline"] == "mtb"
    assert data["city"] == "Bogotá"
    assert set(data["goals"]) == {"descending", "intervals"}


def test_put_profile_updates_existing(client):
    """Second PUT should update the row, not create a duplicate."""
    client.put("/api/profile", json={"discipline": "road", "goals": ["endurance"]})
    client.put("/api/profile", json={"discipline": "gravel", "goals": ["climbing"]})

    resp = client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["discipline"] == "gravel"
    assert data["goals"] == ["climbing"]


def test_put_profile_invalid_discipline(client):
    resp = client.put("/api/profile", json={"discipline": "bmx", "goals": ["endurance"]})
    assert resp.status_code == 422


def test_put_profile_invalid_goal(client):
    resp = client.put("/api/profile", json={"discipline": "road", "goals": ["flying"]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/summary/daily — returns 404 when no row
# ---------------------------------------------------------------------------


def test_get_daily_summary_404(client):
    resp = client.get("/api/summary/daily")
    assert resp.status_code == 404


def test_get_daily_summary_with_date_param(client, db_session):
    """Directly insert a row and verify the endpoint returns it."""
    target = datetime.date(2026, 5, 1)
    row = DailySummary(
        date=target,
        text="Great recovery day.",
        tokens_in=1000,
        tokens_out=150,
        cache_read=800,
        cost_usd=0.001,
        generated_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(row)
    db_session.commit()

    resp = client.get(f"/api/summary/daily?date={target}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-05-01"
    assert data["text"] == "Great recovery day."
    assert data["cost_usd"] == pytest.approx(0.001, abs=1e-6)


# ---------------------------------------------------------------------------
# build_profile_summary unit test (no HTTP layer)
# ---------------------------------------------------------------------------


def test_build_profile_summary_none_when_empty(db_session):
    from coach.agent.profile import build_profile_summary

    result = build_profile_summary(db_session)
    assert result is None


def test_build_profile_summary_full(db_session):
    from coach.agent.profile import build_profile_summary

    row = RiderProfile(
        id=1,
        discipline="road",
        city="Medellín",
        country="CO",
        terrain_notes="very hilly, 1500m typical",
    )
    row.goals = ["climbing", "endurance"]
    row.updated_at = datetime.datetime.now(datetime.UTC)
    db_session.add(row)
    db_session.commit()

    summary = build_profile_summary(db_session)
    assert summary is not None
    assert "road" in summary
    assert "Medellín" in summary
    assert "climbing" in summary
    assert "endurance" in summary


def test_build_profile_summary_omits_absent_fields(db_session):
    from coach.agent.profile import build_profile_summary

    row = RiderProfile(id=1, discipline="mtb")
    row.goals = []
    row.updated_at = datetime.datetime.now(datetime.UTC)
    db_session.add(row)
    db_session.commit()

    summary = build_profile_summary(db_session)
    assert summary is not None
    assert "Trains in" not in summary
    assert "goals:" not in summary.lower() or "Training goals:" not in summary
