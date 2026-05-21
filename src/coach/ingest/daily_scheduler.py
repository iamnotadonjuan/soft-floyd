"""APScheduler cron: fires the daily readiness summary at 15:00 local time (Phase 4)."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from coach.log import log

if TYPE_CHECKING:
    from coach.config import Config


def start_daily_scheduler(cfg: Config) -> AsyncIOScheduler:
    """Register and start the 3pm daily-summary job. Returns the scheduler instance."""
    scheduler = AsyncIOScheduler()

    async def _run() -> None:
        from coach.agent.daily import generate_daily_summary
        from coach.store.session import get_sync_session

        if not cfg.openai_api_key:
            log.warning("daily_scheduler.skipped", reason="openai_api_key not configured")
            return

        today = datetime.date.today()
        session = get_sync_session()
        try:
            await generate_daily_summary(session, cfg, today)
            log.info("daily_scheduler.summary_done", date=str(today))
        except Exception as exc:
            log.error("daily_scheduler.failed", date=str(today), error=str(exc))
        finally:
            session.close()

    scheduler.add_job(_run, CronTrigger(hour=15, minute=0))
    scheduler.start()
    log.info("daily_scheduler.started", trigger="15:00 local time")
    return scheduler
