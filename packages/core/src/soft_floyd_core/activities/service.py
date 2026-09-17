"""Read queries + Pydantic Out models for activities and sync status.

Both `mcp_server.py` and `http_api.py` call these functions directly —
see ARCHITECTURE.md's load-bearing constraint. `available_metrics_for_activity`
is the point of the whole sensor-presence exercise: it intersects the
rider's profile-level allowlist (what their declared hardware supports in
general) with what THIS ride's own FIT data actually contains, so a
dead-battery ride never gets power metrics just because the profile says
there's a power meter.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.config import Settings
from soft_floyd_core.models import Activity, GarminSyncState, Lap
from soft_floyd_core.profile.service import get_profile


class LapOut(BaseModel):
    lap_index: int
    distance_m: float
    duration_s: float
    avg_hr: int | None
    avg_speed_mps: float | None
    avg_power_w: int | None
    avg_cadence: int | None
    elev_gain_m: float


class ActivitySummaryOut(BaseModel):
    id: int
    start_time: dt.datetime
    sport: str
    sub_sport: str
    bike_type: str
    is_indoor: bool
    distance_m: float
    duration_s: float
    elev_gain_m: float
    avg_hr: int | None
    max_hr: int | None
    avg_power_w: int | None
    avg_cadence: int | None
    sensors_present: list[str]
    fit_status: str


class ActivityDetailOut(ActivitySummaryOut):
    laps: list[LapOut]
    record_count: int
    records_stored: bool
    available_metrics: list[str]


class SyncStatusOut(BaseModel):
    last_seen_activity_id: int | None
    last_sync_at: dt.datetime | None
    last_status: str
    last_error: str | None
    consecutive_errors: int
    poll_interval_minutes: int
    authenticated: bool


# Metric name -> the stream it requires, or None if it needs no sensor
# beyond the Garmin summary itself (duration/distance/elevation survive
# even a failed FIT download). Deliberately coarse for this plan — see
# docs/exec-plans/tech-debt-tracker.md; refine per-metric in the
# training-metrics exec-plan (e.g. decoupling really needs two streams).
_STREAM_BY_METRIC: dict[str, str | None] = {
    "ftp": "power",
    "normalized_power": "power",
    "intensity_factor": "power",
    "training_stress_score": "power",
    "power_curve": "power",
    "hr_zones": "hr",
    "hr_drift": "hr",
    "decoupling": "hr",
    "trimp": "hr",
    "gap": "gps",
    "vam": "gps",
    "cadence_distribution": "cadence",
    "duration": None,
    "distance": None,
    "elevation_gain": None,
    "avg_speed": "speed",
}


def _sensors_present(activity: Activity) -> list[str]:
    present = []
    if activity.has_power_data:
        present.append("power")
    if activity.has_hr_data:
        present.append("hr")
    if activity.has_cadence_data:
        present.append("cadence")
    if activity.has_speed_data:
        present.append("speed")
    if activity.has_gps_data:
        present.append("gps")
    return present


def _to_summary_out(activity: Activity) -> ActivitySummaryOut:
    return ActivitySummaryOut(
        id=activity.id,
        start_time=activity.start_time,
        sport=activity.sport,
        sub_sport=activity.sub_sport,
        bike_type=activity.bike_type,
        is_indoor=activity.is_indoor,
        distance_m=activity.distance_m,
        duration_s=activity.duration_s,
        elev_gain_m=activity.elev_gain_m,
        avg_hr=activity.avg_hr,
        max_hr=activity.max_hr,
        avg_power_w=activity.avg_power_w,
        avg_cadence=activity.avg_cadence,
        sensors_present=_sensors_present(activity),
        fit_status=activity.fit_status,
    )


def list_activities(
    session: Session, *, limit: int = 20, bike_type: str | None = None
) -> list[ActivitySummaryOut]:
    stmt = select(Activity).order_by(Activity.start_time.desc()).limit(limit)
    if bike_type is not None:
        stmt = stmt.where(Activity.bike_type == bike_type)
    activities = session.scalars(stmt).all()
    return [_to_summary_out(a) for a in activities]


def available_metrics_for_activity(session: Session, activity: Activity) -> list[str]:
    # get_profile() auto-creates the single-row profile if it doesn't exist
    # yet (same as every other reader) — a raw session.get() here would
    # silently return [] for a rider who hasn't touched /api/profile yet.
    profile_metrics = get_profile(session).available_metrics

    if activity.fit_status != "ok":
        # We never parsed this ride's streams — only sensor-independent
        # metrics survive a failed download/parse.
        return [m for m in profile_metrics if _STREAM_BY_METRIC.get(m) is None]

    present = set(_sensors_present(activity))
    result = []
    for metric in profile_metrics:
        stream = _STREAM_BY_METRIC.get(metric)
        if stream is None or stream in present:
            result.append(metric)
    return result


def get_activity(session: Session, activity_id: int) -> ActivityDetailOut | None:
    activity = session.get(Activity, activity_id)
    if activity is None:
        return None

    laps = session.scalars(
        select(Lap).where(Lap.activity_id == activity_id).order_by(Lap.lap_index)
    ).all()

    return ActivityDetailOut(
        **_to_summary_out(activity).model_dump(),
        laps=[
            LapOut(
                lap_index=lap.lap_index,
                distance_m=lap.distance_m,
                duration_s=lap.duration_s,
                avg_hr=lap.avg_hr,
                avg_speed_mps=lap.avg_speed_mps,
                avg_power_w=lap.avg_power_w,
                avg_cadence=lap.avg_cadence,
                elev_gain_m=lap.elev_gain_m,
            )
            for lap in laps
        ],
        record_count=activity.record_count,
        records_stored=activity.records_stored,
        available_metrics=available_metrics_for_activity(session, activity),
    )


def get_sync_status(session: Session, settings: Settings) -> SyncStatusOut:
    state = session.get(GarminSyncState, 1)
    authenticated = (settings.garmin_token_dir / "garmin_tokens.json").exists()
    if state is None:
        return SyncStatusOut(
            last_seen_activity_id=None,
            last_sync_at=None,
            last_status="never",
            last_error=None,
            consecutive_errors=0,
            poll_interval_minutes=settings.poll_interval_minutes,
            authenticated=authenticated,
        )
    return SyncStatusOut(
        last_seen_activity_id=state.last_seen_activity_id,
        last_sync_at=state.last_sync_at,
        last_status=state.last_status,
        last_error=state.last_error,
        consecutive_errors=state.consecutive_errors,
        poll_interval_minutes=settings.poll_interval_minutes,
        authenticated=authenticated,
    )
