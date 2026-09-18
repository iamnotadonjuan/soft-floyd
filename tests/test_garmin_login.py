"""perform_login's cooldown against a real tmp SQLite — a hand-written
fake GarminClient (not a real GarminClient/garminconnect.Garmin) so no
network call is ever possible here regardless of the cooldown logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from soft_floyd_core.config import Settings
from soft_floyd_core.db import make_engine, make_session_factory, session_scope
from soft_floyd_core.garmin.errors import GarminRateLimited
from soft_floyd_core.garmin.login import clear_login_block, perform_login
from soft_floyd_core.models import GarminSyncState


class FakeGarminClient:
    """Stands in for GarminClient. Records whether login() was called at
    all, so a refusal-without-network-call can be asserted directly."""

    def __init__(self, *, raise_on_login: Exception | None = None):
        self._raise_on_login = raise_on_login
        self.login_calls = 0

    def login(self, email, password, mfa_callback):
        self.login_calls += 1
        if self._raise_on_login is not None:
            raise self._raise_on_login


def _settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "db.sqlite", garmin_login_cooldown_minutes=30)


def _session_factory(tmp_path):
    engine = make_engine(_settings(tmp_path).db_path)
    return make_session_factory(engine)


def test_successful_login_clears_any_prior_block_and_resets_errors(tmp_path):
    """A block that has already elapsed shouldn't stop the login, and
    error state left over from before the login (e.g. sync failures
    while logged out) should be cleared once it succeeds."""
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient()

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1) or GarminSyncState(id=1)
        session.add(state)
        state.login_blocked_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        state.consecutive_errors = 4
        state.last_status = "error"
        session.commit()

    with session_scope(sf) as session:
        perform_login(session, settings, client, "rider@example.com", "hunter2", lambda: "0")

    assert client.login_calls == 1
    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1)
        assert state.login_blocked_until is None
        assert state.consecutive_errors == 0


def test_a_429_sets_a_cooldown_using_retry_after(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient(raise_on_login=GarminRateLimited("slow down", retry_after_s=120))

    with session_scope(sf) as session:
        with pytest.raises(GarminRateLimited):
            perform_login(session, settings, client, "rider@example.com", "hunter2", lambda: "0")

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1)
        remaining = (
            state.login_blocked_until - datetime.now(UTC).replace(tzinfo=None)
        ).total_seconds()
        assert 110 < remaining <= 120


def test_a_429_without_retry_after_falls_back_to_configured_cooldown(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient(raise_on_login=GarminRateLimited("slow down"))

    with session_scope(sf) as session:
        with pytest.raises(GarminRateLimited):
            perform_login(session, settings, client, "rider@example.com", "hunter2", lambda: "0")

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1)
        remaining = (
            state.login_blocked_until - datetime.now(UTC).replace(tzinfo=None)
        ).total_seconds()
        assert 1790 < remaining <= 1800  # ~30 minutes


def test_a_second_attempt_during_cooldown_is_refused_without_a_network_call(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1) or GarminSyncState(id=1)
        session.add(state)
        state.login_blocked_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10)
        session.commit()

    client = FakeGarminClient()
    with session_scope(sf) as session:
        with pytest.raises(GarminRateLimited, match="cooldown"):
            perform_login(session, settings, client, "rider@example.com", "hunter2", lambda: "0")

    assert client.login_calls == 0  # refused locally, no network call


def test_cooldown_that_has_already_elapsed_allows_a_fresh_attempt(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1) or GarminSyncState(id=1)
        session.add(state)
        state.login_blocked_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        session.commit()

    client = FakeGarminClient()
    with session_scope(sf) as session:
        perform_login(session, settings, client, "rider@example.com", "hunter2", lambda: "0")

    assert client.login_calls == 1


def test_clear_login_block_removes_an_active_cooldown(tmp_path):
    sf = _session_factory(tmp_path)

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1) or GarminSyncState(id=1)
        session.add(state)
        state.login_blocked_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=10)
        session.commit()

    with session_scope(sf) as session:
        clear_login_block(session)

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1)
        assert state.login_blocked_until is None
