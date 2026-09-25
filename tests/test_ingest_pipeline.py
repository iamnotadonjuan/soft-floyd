"""ingest_activity — idempotency, failure handling, and the required
rule-1 proof: a rider profile claiming a power meter must never leak
into a specific ride's available metrics when that ride's own FIT data
has no power stream. See docs/design-docs/sensor-capability-model.md.
"""

from __future__ import annotations

from soft_floyd_core.activities import service as activities_service
from soft_floyd_core.activities.pipeline import ingest_activity
from soft_floyd_core.bikes.service import BikeIn, add_bike
from soft_floyd_core.config import Settings
from soft_floyd_core.db import make_engine, make_session_factory, session_scope
from soft_floyd_core.garmin.errors import GarminApiError
from soft_floyd_core.models import Activity
from soft_floyd_core.profile.service import ProfileIn, upsert_profile


class FakeFitSource:
    """Satisfies pipeline.FitSource — no garminconnect import anywhere here."""

    def __init__(self, fit_bytes: bytes, *, raise_: Exception | None = None):
        self._fit_bytes = fit_bytes
        self._raise = raise_

    def download_fit(self, activity_id, dest_path):
        if self._raise is not None:
            raise self._raise
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(self._fit_bytes)
        return dest_path


def _settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "db.sqlite", fit_dir=tmp_path / "fit")


def _summary(activity_id: int, **overrides) -> dict:
    base = {
        "activityId": activity_id,
        "startTimeLocal": "2026-04-15T08:00:00",
        "isIndoor": False,
    }
    base.update(overrides)
    return base


def test_rule_1_profile_claims_power_but_ride_has_none(tmp_path, mtb_fit_path):
    """The one test that proves the profile is a planning signal and the
    FIT stream is the analysis signal — they must not be conflated.
    """
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_path)
    sf = make_session_factory(engine)

    with session_scope(sf) as session:
        # Bike-mounted sensors live on Bike now, not RiderProfile — a
        # power-meter bike is the "profile claims power" half of this
        # test's premise (exec-plan 0004).
        add_bike(session, BikeIn(kind="mtb", has_power_meter=True))
        upsert_profile(session, ProfileIn(has_hr_monitor=True, ftp_watts=250))

    source = FakeFitSource(mtb_fit_path.read_bytes())
    with session_scope(sf) as session:
        activity = ingest_activity(session, settings, source, _summary(1))
        assert activity.has_power_data is False
        assert activity.fit_status == "ok"

    with session_scope(sf) as session:
        detail = activities_service.get_activity(session, 1)
        assert "ftp" not in detail.available_metrics
        assert "normalized_power" not in detail.available_metrics
        assert "hr_zones" in detail.available_metrics  # HR metrics still apply

        # The profile's own general allowlist still includes power metrics —
        # only the per-activity view excludes them.
        from soft_floyd_core.profile.service import get_profile

        profile_out = get_profile(session)
        assert "ftp" in profile_out.available_metrics


def test_idempotent_ingest_is_a_no_op_second_time(tmp_path, road_fit_path):
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_path)
    sf = make_session_factory(engine)
    source = FakeFitSource(road_fit_path.read_bytes())

    with session_scope(sf) as session:
        first = ingest_activity(session, settings, source, _summary(2))
        assert first.garmin_id == 2

    with session_scope(sf) as session:
        second = ingest_activity(session, settings, source, _summary(2))
        assert second.garmin_id == 2
        count = session.query(Activity).count()
        assert count == 1


def test_download_failure_leaves_partial_row(tmp_path):
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_path)
    sf = make_session_factory(engine)
    source = FakeFitSource(b"", raise_=ConnectionError("network down"))

    with session_scope(sf) as session:
        activity = ingest_activity(session, settings, source, _summary(3))
        assert activity.fit_status == "download_failed"
        assert activity.has_power_data is False
        assert activity.has_hr_data is False


def test_garmin_api_error_propagates_instead_of_degrading(tmp_path):
    """Auth/rate-limit failures must propagate so the sync cycle can
    decide how to back off — never silently swallowed into a partial row.
    """
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_path)
    sf = make_session_factory(engine)
    source = FakeFitSource(b"", raise_=GarminApiError("rate limited"))

    with session_scope(sf) as session:
        try:
            ingest_activity(session, settings, source, _summary(4))
            raise AssertionError("expected GarminApiError to propagate")
        except GarminApiError:
            pass


def test_parse_failure_leaves_partial_row(tmp_path):
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_path)
    sf = make_session_factory(engine)
    source = FakeFitSource(b"this is not a valid fit file")

    with session_scope(sf) as session:
        activity = ingest_activity(session, settings, source, _summary(5))
        assert activity.fit_status == "parse_failed"


def test_oversized_record_stream_is_not_persisted_but_sensor_flags_still_are(
    tmp_path, road_fit_path, monkeypatch
):
    """The 3MB size gate governs storage, not detection — record_count
    and has_*_data must reflect every parsed record even when the raw
    stream itself is dropped.
    """
    import soft_floyd_core.activities.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "_RECORD_SIZE_LIMIT_BYTES", 1)  # force the gate to trip

    settings = _settings(tmp_path)
    engine = make_engine(settings.db_path)
    sf = make_session_factory(engine)
    source = FakeFitSource(road_fit_path.read_bytes())

    with session_scope(sf) as session:
        activity = ingest_activity(session, settings, source, _summary(6))
        assert activity.records_stored is False
        assert activity.record_count == 100
        assert activity.has_power_data is True
        from soft_floyd_core.models import Record

        assert session.query(Record).filter_by(activity_id=6).count() == 0
