"""Per-activity ingest pipeline shared by poller and backfill."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from coach.classify.bike_type import classify
from coach.ingest.fit_parser import parse_fit
from coach.log import log
from coach.metrics.compute import compute_metrics
from coach.store.models import Activity, Lap, Metrics, Record, WellnessDaily

if TYPE_CHECKING:
    from coach.config import Config
    from coach.ingest.garmin_client import GarminClient

_RECORD_SIZE_LIMIT_BYTES = 3 * 1024 * 1024  # 3 MB


def _estimate_records_size(records: list) -> int:
    """Rough byte estimate for a list of RecordData (7 floats each ≈ 56 bytes)."""
    return len(records) * 56


def ingest_activity(
    session: Session,
    cfg: Config,
    garmin: GarminClient,
    summary: dict,
) -> Activity | None:
    """Full per-activity pipeline. Returns the Activity row or None if skipped."""
    activity_id: int = int(summary["activityId"])

    existing = session.get(Activity, activity_id)
    if existing is not None:
        log.debug("pipeline.skip_existing", activity_id=activity_id)
        return existing

    # Step 1 — insert bare activity row
    start_str = summary.get("startTimeLocal") or summary.get("startTimeGMT") or ""
    try:
        start_dt = datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
    except Exception:
        start_dt = datetime.datetime.now(datetime.UTC)

    activity = Activity(
        id=activity_id,
        start_time=start_dt,
        sport=str(
            summary.get("activityType", {}).get("typeKey", "")
            if isinstance(summary.get("activityType"), dict)
            else summary.get("activityType", "")
        ),
        sub_sport=str(
            summary.get("subActivityType", {}).get("typeKey", "")
            if isinstance(summary.get("subActivityType"), dict)
            else ""
        ),
        is_indoor=bool(summary.get("isIndoor", False)),
        distance_m=float(summary.get("distance", 0) or 0),
        duration_s=float(summary.get("duration", 0) or 0),
        elev_gain_m=float(summary.get("elevationGain", 0) or 0),
        avg_hr=summary.get("averageHR") and int(summary["averageHR"]),
        max_hr=summary.get("maxHR") and int(summary["maxHR"]),
        raw_summary_json=summary,
        bike_type="other",
    )
    session.add(activity)
    session.flush()

    # Step 2 — download FIT
    fit_path = cfg.fit_dir / f"{activity_id}.fit"
    try:
        garmin.download_fit(activity_id, fit_path)
        activity.fit_path = str(fit_path)
    except Exception as exc:
        log.warning("pipeline.fit_download_failed", activity_id=activity_id, error=str(exc))
        session.commit()
        return activity

    # Step 3 — parse FIT
    try:
        parsed = parse_fit(fit_path)
    except Exception as exc:
        log.warning("pipeline.fit_parse_failed", activity_id=activity_id, error=str(exc))
        session.commit()
        return activity

    # Upsert laps
    for lap in parsed.laps:
        lap_row = Lap(
            activity_id=activity_id,
            lap_index=lap.lap_index,
            distance_m=lap.distance_m,
            duration_s=lap.duration_s,
            avg_hr=lap.avg_hr,
            avg_speed=lap.avg_speed,
            elev_gain_m=lap.elev_gain_m,
        )
        session.add(lap_row)

    # Upsert records (size-gated)
    if parsed.records and _estimate_records_size(parsed.records) < _RECORD_SIZE_LIMIT_BYTES:
        for rec in parsed.records:
            r = Record(
                activity_id=activity_id,
                t_offset_s=rec.t_offset_s,
                hr=rec.hr,
                speed_mps=rec.speed_mps,
                altitude_m=rec.altitude_m,
                cadence=rec.cadence,
                lat=rec.lat,
                lon=rec.lon,
            )
            session.add(r)

    # Step 4 — compute metrics
    try:
        m_data = compute_metrics(parsed, lthr=cfg.lthr)
        tss_proxy = m_data.pop("tss_proxy", None)
        activity.tss_proxy = tss_proxy

        m = Metrics(activity_id=activity_id, **m_data)
        session.add(m)
    except Exception as exc:
        log.warning("pipeline.metrics_failed", activity_id=activity_id, error=str(exc))

    # Step 5 — wellness
    try:
        wellness_data = garmin.get_wellness(start_dt)
        date_key = start_dt.date()
        existing_w = session.get(WellnessDaily, date_key)
        if existing_w is None:
            w = WellnessDaily(
                date=date_key,
                hrv_overnight=wellness_data.get("hrv_overnight"),
                sleep_score=wellness_data.get("sleep_score"),
                body_battery_low=wellness_data.get("body_battery_low"),
                body_battery_high=wellness_data.get("body_battery_high"),
                resting_hr=wellness_data.get("resting_hr"),
            )
            session.add(w)
    except Exception as exc:
        log.warning("pipeline.wellness_failed", activity_id=activity_id, error=str(exc))

    # Step 6 — classify
    try:
        activity.bike_type = classify(summary, parsed)
    except Exception as exc:
        log.warning("pipeline.classify_failed", activity_id=activity_id, error=str(exc))

    session.commit()
    log.info("pipeline.activity_ingested", activity_id=activity_id, bike_type=activity.bike_type)
    return activity
