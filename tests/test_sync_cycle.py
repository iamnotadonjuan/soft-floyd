"""run_sync_cycle against a real tmp SQLite and a FakeGarminClient — no
garminconnect import anywhere in this file.
"""

from __future__ import annotations

from soft_floyd_core.config import Settings
from soft_floyd_core.db import make_engine, make_session_factory, session_scope
from soft_floyd_core.garmin.errors import (
    GarminApiError,
    GarminNotFound,
    GarminRateLimited,
    ReauthRequired,
)
from soft_floyd_core.garmin.sync import backoff_seconds, run_sync_cycle
from soft_floyd_core.models import GarminSyncState


class FakeGarminClient:
    """Satisfies both list_recent_activities and download_fit (FitSource)."""

    def __init__(self, activities: list[dict], *, fit_bytes: bytes = b"", raise_on_list=None):
        self._activities = activities
        self._fit_bytes = fit_bytes
        self._raise_on_list = raise_on_list
        self.download_calls: list[int] = []
        self._raise_on_download: dict[int, Exception] = {}

    def raise_on_download(self, activity_id: int, exc: Exception) -> None:
        self._raise_on_download[activity_id] = exc

    def list_recent_activities(self, limit=20, start=0):
        if self._raise_on_list is not None:
            raise self._raise_on_list
        return self._activities

    def download_fit(self, activity_id, dest_path):
        self.download_calls.append(activity_id)
        if activity_id in self._raise_on_download:
            raise self._raise_on_download[activity_id]
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(self._fit_bytes)
        return dest_path


def _settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "db.sqlite", fit_dir=tmp_path / "fit")


def _activity(activity_id: int) -> dict:
    return {"activityId": activity_id, "startTimeLocal": "2026-04-15T08:00:00", "isIndoor": False}


def _session_factory(tmp_path):
    engine = make_engine(_settings(tmp_path).db_path)
    return make_session_factory(engine)


def test_empty_cursor_ingests_only_the_most_recent_activity(tmp_path, road_fit_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient(
        [_activity(1), _activity(2), _activity(3)], fit_bytes=road_fit_path.read_bytes()
    )

    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client)

    assert result.status == "ok"
    assert result.new_activity_ids == [3]  # bounded first run: newest only
    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1)
        assert state.last_seen_activity_id == 3


def test_second_cycle_with_no_new_activities_ingests_nothing(tmp_path, road_fit_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient([_activity(1)], fit_bytes=road_fit_path.read_bytes())

    with session_scope(sf) as session:
        run_sync_cycle(session, settings, client)

    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client)

    assert result.status == "ok"
    assert result.new_activity_ids == []


def test_two_new_activities_ingested_in_ascending_order(tmp_path, road_fit_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient([_activity(5)], fit_bytes=road_fit_path.read_bytes())
    with session_scope(sf) as session:
        run_sync_cycle(session, settings, client)  # bootstraps cursor to 5

    client._activities = [_activity(5), _activity(6), _activity(7)]  # noqa: SLF001
    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client)

    assert result.new_activity_ids == [6, 7]
    with session_scope(sf) as session:
        assert session.get(GarminSyncState, 1).last_seen_activity_id == 7


def test_not_found_skips_but_commits_the_rest(tmp_path, road_fit_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient([_activity(1)], fit_bytes=road_fit_path.read_bytes())
    with session_scope(sf) as session:
        run_sync_cycle(session, settings, client)  # bootstrap to 1

    client._activities = [_activity(1), _activity(2), _activity(3)]  # noqa: SLF001
    client.raise_on_download(2, GarminNotFound("gone"))

    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client)

    assert result.status == "ok"
    assert result.skipped == 1
    assert 3 in result.new_activity_ids
    assert 2 not in result.new_activity_ids


def test_reauth_required_does_not_bump_consecutive_errors(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient([], raise_on_list=ReauthRequired("needs login"))

    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client)

    assert result.status == "reauth_required"
    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1)
        assert state.consecutive_errors == 0
        assert state.last_error == "needs login"


def test_generic_error_bumps_consecutive_errors(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient([], raise_on_list=GarminApiError("upstream 500"))

    with session_scope(sf) as session:
        run_sync_cycle(session, settings, client)
    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client)

    assert result.status == "error"
    with session_scope(sf) as session:
        assert session.get(GarminSyncState, 1).consecutive_errors == 2


def test_rate_limited_reports_retry_after(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient([], raise_on_list=GarminRateLimited("slow down", retry_after_s=42))

    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client)

    assert result.status == "rate_limited"
    assert result.retry_after_s == 42


def test_should_stop_halts_cleanly_with_prior_activities_committed(tmp_path, road_fit_path):
    settings = _settings(tmp_path)
    sf = _session_factory(tmp_path)
    client = FakeGarminClient([_activity(1)], fit_bytes=road_fit_path.read_bytes())
    with session_scope(sf) as session:
        run_sync_cycle(session, settings, client)  # bootstrap to 1

    client._activities = [_activity(1), _activity(2), _activity(3)]  # noqa: SLF001
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 1  # allow the first candidate through, then stop

    with session_scope(sf) as session:
        result = run_sync_cycle(session, settings, client, should_stop=should_stop)

    assert result.new_activity_ids == [2]
    assert 3 not in result.new_activity_ids


def test_backoff_grows_and_caps():
    settings = Settings(poll_interval_minutes=10, poll_max_backoff_minutes=60)
    assert backoff_seconds(settings, 0) == 600
    assert backoff_seconds(settings, 1) == 1200
    assert backoff_seconds(settings, 2) == 2400
    assert backoff_seconds(settings, 20) == 3600  # capped


def test_backoff_does_not_overflow_at_very_high_error_counts():
    settings = Settings(poll_interval_minutes=10, poll_max_backoff_minutes=60)
    # must not raise, and must stay at the cap
    assert backoff_seconds(settings, 200) == 3600
