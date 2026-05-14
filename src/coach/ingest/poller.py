from __future__ import annotations

import asyncio
import datetime

from coach.config import Config
from coach.ingest.garmin_client import GarminClient, ReauthRequired
from coach.ingest.pipeline import ingest_activity
from coach.log import log
from coach.store.models import PollCursor
from coach.store.session import get_sync_session, init_db

_MAX_BACKOFF_S = 3600


def _notify(message: str) -> None:
    try:
        import pync

        pync.notify(message, title="Soft Floyd")
    except Exception:
        log.warning("poller.notify_failed", message=message)


async def _coach_and_notify(cfg: Config, activity_id: int) -> None:
    """Run initial CoachSession analysis and send a desktop notification."""
    from coach.agent.coach import CoachSession
    from coach.store.session import get_sync_session

    session = get_sync_session()
    try:
        coach = CoachSession(session, cfg, activity_id)
        async for _ in coach.initial_analysis():
            pass  # consume the stream; text is persisted to DB
        _notify("Soft Floyd has thoughts on your ride 🚴")
        log.info("poller.coach_analysis_done", activity_id=activity_id)
    except Exception as exc:
        log.warning("poller.coach_failed", activity_id=activity_id, error=str(exc))
    finally:
        session.close()


async def _poll_once(cfg: Config, garmin: GarminClient, consecutive_errors: int) -> int:
    """Run one poll cycle. Returns new consecutive_errors count."""
    session = get_sync_session()
    try:
        cursor = session.get(PollCursor, 1)
        last_id = cursor.last_seen_activity_id if cursor else None

        activities = garmin.list_activities(limit=20)

        if not activities:
            _update_cursor(session, last_id, "ok")
            return 0

        # Find new activities (higher ID than last seen)
        new_acts = []
        for a in activities:
            aid = int(a.get("activityId", 0))
            if last_id is None or aid > last_id:
                new_acts.append(a)

        new_acts.sort(key=lambda a: int(a.get("activityId", 0)))

        for summary in new_acts:
            try:
                ingest_activity(session, cfg, garmin, summary)
                if cfg.anthropic_api_key:
                    await _coach_and_notify(cfg, int(summary["activityId"]))
            except Exception as exc:
                log.error(
                    "poller.activity_failed", activity_id=summary.get("activityId"), error=str(exc)
                )

        if new_acts:
            max_id = max(int(a["activityId"]) for a in new_acts)
            _update_cursor(session, max_id, "ok")
        else:
            _update_cursor(session, last_id, "ok")

        return 0

    except ReauthRequired as exc:
        log.error("poller.reauth_required", error=str(exc))
        _notify("Soft Floyd needs Garmin re-auth. Run `coach login`.")
        _update_cursor(session, None, "reauth_required")
        return consecutive_errors + 1
    except Exception as exc:
        log.error("poller.error", error=str(exc))
        _update_cursor(session, None, "error")
        return consecutive_errors + 1
    finally:
        session.close()


def _update_cursor(session, last_id, status: str) -> None:
    cursor = session.get(PollCursor, 1)
    if cursor is None:
        cursor = PollCursor(id=1)
        session.add(cursor)
    cursor.last_seen_activity_id = last_id
    cursor.last_poll_at = datetime.datetime.now(datetime.UTC)
    cursor.last_poll_status = status
    session.commit()


async def run_poller(cfg: Config) -> None:
    init_db(cfg.db_path)
    garmin = GarminClient(cfg)
    try:
        garmin.load_from_disk()
    except ReauthRequired as exc:
        log.error("poller.startup_reauth", error=str(exc))
        _notify("Soft Floyd needs Garmin re-auth. Run `coach login`.")
        return

    log.info("poller.started", interval_minutes=cfg.poll_interval_minutes)
    consecutive_errors = 0

    while True:
        consecutive_errors = await _poll_once(cfg, garmin, consecutive_errors)

        # Exponential backoff: base interval, double per error, cap at 60 min
        if consecutive_errors > 0:
            backoff_s = min(
                cfg.poll_interval_minutes * 60 * (2**consecutive_errors), _MAX_BACKOFF_S
            )
            log.info(
                "poller.backing_off", backoff_s=backoff_s, consecutive_errors=consecutive_errors
            )
        else:
            backoff_s = cfg.poll_interval_minutes * 60

        await asyncio.sleep(backoff_s)
