from __future__ import annotations

import asyncio
import datetime
from pathlib import Path

from coach.config import Config
from coach.ingest.garmin_client import GarminClient, ReauthRequired
from coach.ingest.pipeline import ingest_activity
from coach.log import log
from coach.store.session import get_sync_session, init_db


async def run_backfill(cfg: Config, days: int = 365) -> None:
    init_db(cfg.db_path)
    garmin = GarminClient(cfg)
    try:
        garmin.load_from_disk()
    except ReauthRequired as exc:
        log.error("backfill.reauth_required", error=str(exc))
        raise

    end_dt = datetime.datetime.now(datetime.UTC)
    start_dt = end_dt - datetime.timedelta(days=days)

    log.info("backfill.start", days=days, from_date=start_dt.isoformat())

    page = 0
    page_size = 20
    total = 0

    while True:
        try:
            activities = garmin.list_activities(
                start_dt=start_dt, limit=page_size, start=page * page_size
            )
        except ReauthRequired as exc:
            log.error("backfill.reauth_required", error=str(exc))
            raise
        except Exception as exc:
            log.error("backfill.list_failed", page=page, error=str(exc))
            break

        if not activities:
            break

        # Filter to activities within our date range
        in_range = []
        for a in activities:
            start_str = a.get("startTimeLocal") or a.get("startTimeGMT") or ""
            try:
                act_dt = datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if act_dt.tzinfo is None:
                    act_dt = act_dt.replace(tzinfo=datetime.UTC)
                if act_dt >= start_dt:
                    in_range.append(a)
            except Exception:
                in_range.append(a)

        for summary in in_range:
            session = get_sync_session()
            try:
                ingest_activity(session, cfg, garmin, summary)
                total += 1
            except Exception as exc:
                log.error(
                    "backfill.activity_failed",
                    activity_id=summary.get("activityId"),
                    error=str(exc),
                )
            finally:
                session.close()

            # Throttle: ≤1 req/sec to respect undocumented Garmin rate limits
            await asyncio.sleep(1.0)

        page += 1

        if len(activities) < page_size:
            break

    log.info("backfill.complete", total_ingested=total)


async def ingest_single_fit(cfg: Config, fit_path: Path) -> None:
    """Manually ingest a local FIT file without Garmin API access."""
    import hashlib

    from coach.classify.bike_type import classify
    from coach.ingest.fit_parser import parse_fit
    from coach.metrics.compute import compute_metrics
    from coach.store.models import Activity, Lap, Metrics

    init_db(cfg.db_path)
    parsed = parse_fit(fit_path)

    # Derive a stable activity ID from the file path
    fake_id = int(hashlib.md5(str(fit_path).encode()).hexdigest()[:8], 16)
    summary = {
        "activityId": fake_id,
        "startTimeLocal": parsed.session.start_time.isoformat()
        if parsed.session.start_time
        else None,
        "isIndoor": parsed.session.is_indoor,
        "distance": parsed.session.total_distance_m,
        "duration": parsed.session.total_elapsed_s,
        "elevationGain": parsed.session.total_ascent_m,
        "averageHR": parsed.session.avg_hr,
        "maxHR": parsed.session.max_hr,
    }

    session = get_sync_session()
    try:
        existing = session.get(Activity, fake_id)
        if existing:
            log.info("ingest_fit.already_exists", activity_id=fake_id)
            return

        import datetime as dt

        start_time = parsed.session.start_time or dt.datetime.now(dt.UTC)
        activity = Activity(
            id=fake_id,
            start_time=start_time,
            sport=parsed.session.sport,
            sub_sport=parsed.session.sub_sport,
            is_indoor=parsed.session.is_indoor,
            distance_m=parsed.session.total_distance_m,
            duration_s=parsed.session.total_elapsed_s,
            elev_gain_m=parsed.session.total_ascent_m,
            avg_hr=parsed.session.avg_hr,
            max_hr=parsed.session.max_hr,
            fit_path=str(fit_path),
            bike_type=classify(summary, parsed),
        )
        session.add(activity)

        for lap in parsed.laps:
            session.add(
                Lap(
                    activity_id=fake_id,
                    lap_index=lap.lap_index,
                    distance_m=lap.distance_m,
                    duration_s=lap.duration_s,
                    avg_hr=lap.avg_hr,
                    avg_speed=lap.avg_speed,
                    elev_gain_m=lap.elev_gain_m,
                )
            )

        m_data = compute_metrics(parsed, lthr=cfg.lthr)
        m_data.pop("tss_proxy", None)
        session.add(Metrics(activity_id=fake_id, **m_data))

        session.commit()
        log.info("ingest_fit.done", activity_id=fake_id, fit_path=str(fit_path))
    finally:
        session.close()
