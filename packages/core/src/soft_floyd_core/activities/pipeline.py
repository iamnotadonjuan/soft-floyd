"""Per-activity ingest pipeline: Garmin summary -> parsed FIT -> stored Activity.

Ported from v0 (`v0-legacy:src/coach/ingest/pipeline.py`)'s proven shape
(idempotent, bare-row-first-then-enrich, classify last) with v0's metrics/
wellness/embed steps removed (out of scope for this plan — see
docs/design-docs/training-signal-model.md) and sensor-presence detection
added (the whole point of this plan — see
docs/design-docs/sensor-capability-model.md rule 1).

Depends on `FitSource` (a `Protocol`, not `soft_floyd_core.garmin` itself)
so this module — and every test of it — never needs to import
`garminconnect`. Dependency direction is garmin -> activities, never the
reverse; `GarminClient` satisfies `FitSource` structurally.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from soft_floyd_core.activities.classify import classify
from soft_floyd_core.activities.fit_parser import ParsedFit, parse_fit
from soft_floyd_core.activities.sensors import detect_sensor_streams
from soft_floyd_core.config import Settings
from soft_floyd_core.log import get_logger
from soft_floyd_core.models import Activity, Lap, Record

log = get_logger(__name__)

# A ride's record stream is only persisted below this estimated size —
# same 3MB cap as v0, bumped per-record estimate (56->64 bytes) for the
# new power_w column.
_RECORD_SIZE_LIMIT_BYTES = 3 * 1024 * 1024
_BYTES_PER_RECORD_ESTIMATE = 64


class FitSource(Protocol):
    def download_fit(self, activity_id: int, dest_path: Path) -> Path: ...


def _parse_start_time(summary: dict) -> dt.datetime:
    start_str = summary.get("startTimeLocal") or summary.get("startTimeGMT") or ""
    try:
        return dt.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    except Exception:
        return dt.datetime.now(dt.UTC)


def _type_key(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("typeKey", ""))
    return str(value or "")


def _bare_activity(activity_id: int, summary: dict) -> Activity:
    return Activity(
        id=activity_id,
        start_time=_parse_start_time(summary),
        sport=_type_key(summary.get("activityType")),
        sub_sport=_type_key(summary.get("subActivityType")),
        is_indoor=bool(summary.get("isIndoor", False)),
        distance_m=float(summary.get("distance", 0) or 0),
        duration_s=float(summary.get("duration", 0) or 0),
        elev_gain_m=float(summary.get("elevationGain", 0) or 0),
        avg_hr=summary.get("averageHR") and int(summary["averageHR"]),
        max_hr=summary.get("maxHR") and int(summary["maxHR"]),
        raw_summary_json=summary,
        bike_type="other",
        fit_status="pending",
    )


def _estimated_record_bytes(parsed: ParsedFit) -> int:
    return len(parsed.records) * _BYTES_PER_RECORD_ESTIMATE


def _apply_sensor_data(activity: Activity, parsed: ParsedFit) -> None:
    streams = detect_sensor_streams(parsed)
    activity.has_power_data = streams.power
    activity.has_hr_data = streams.hr
    activity.has_cadence_data = streams.cadence
    activity.has_speed_data = streams.speed
    activity.has_gps_data = streams.gps
    activity.avg_power_w = parsed.session.avg_power_w
    activity.max_power_w = parsed.session.max_power_w
    activity.avg_cadence = parsed.session.avg_cadence
    activity.record_count = len(parsed.records)


def ingest_activity(
    session: Session,
    settings: Settings,
    source: FitSource,
    summary: dict,
) -> Activity | None:
    """Full per-activity pipeline. Idempotent: returns the existing row
    unchanged if this activity was already ingested."""
    activity_id = int(summary["activityId"])

    existing = session.get(Activity, activity_id)
    if existing is not None:
        log.debug("pipeline.skip_existing", activity_id=activity_id)
        return existing

    activity = _bare_activity(activity_id, summary)
    session.add(activity)
    session.flush()

    fit_path = settings.fit_dir / f"{activity_id}.fit"
    try:
        source.download_fit(activity_id, fit_path)
        activity.fit_path = str(fit_path)
    except Exception as exc:
        # GarminApiError (auth/rate-limit) must propagate so the sync cycle
        # can decide how to back off; anything else degrades to a partial row.
        from soft_floyd_core.garmin.errors import GarminApiError

        if isinstance(exc, GarminApiError):
            raise
        log.warning("pipeline.fit_download_failed", activity_id=activity_id, error=str(exc))
        activity.fit_status = "download_failed"
        session.commit()
        return activity

    try:
        parsed = parse_fit(fit_path)
    except Exception as exc:
        log.warning("pipeline.fit_parse_failed", activity_id=activity_id, error=str(exc))
        activity.fit_status = "parse_failed"
        session.commit()
        return activity

    for lap in parsed.laps:
        session.add(
            Lap(
                activity_id=activity_id,
                lap_index=lap.lap_index,
                distance_m=lap.distance_m,
                duration_s=lap.duration_s,
                avg_hr=lap.avg_hr,
                avg_speed_mps=lap.avg_speed_mps,
                avg_power_w=lap.avg_power_w,
                avg_cadence=lap.avg_cadence,
                elev_gain_m=lap.elev_gain_m,
            )
        )

    # Sensor presence and record_count are derived from every parsed
    # record regardless of whether we persist the raw stream below — the
    # 3MB size gate governs storage, not detection.
    _apply_sensor_data(activity, parsed)

    if parsed.records and _estimated_record_bytes(parsed) < _RECORD_SIZE_LIMIT_BYTES:
        for rec in parsed.records:
            session.add(
                Record(
                    activity_id=activity_id,
                    t_offset_s=rec.t_offset_s,
                    hr=rec.hr,
                    speed_mps=rec.speed_mps,
                    altitude_m=rec.altitude_m,
                    cadence=rec.cadence,
                    power_w=rec.power_w,
                    lat=rec.lat,
                    lon=rec.lon,
                )
            )
        activity.records_stored = True
    else:
        activity.records_stored = False

    activity.bike_type = classify(summary, parsed)
    activity.fit_status = "ok"

    session.commit()
    log.info(
        "pipeline.activity_ingested",
        activity_id=activity_id,
        bike_type=activity.bike_type,
        has_power_data=activity.has_power_data,
    )
    return activity
