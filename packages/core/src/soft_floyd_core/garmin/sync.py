"""The Garmin sync cycle: one pass over recent activities, and the async
runner that repeats it on a schedule.

`run_sync_cycle` is a **plain synchronous function** — `garminconnect`
and `fitdecode` are both synchronous, and v0 ran this directly inside an
async loop, blocking the shared event loop (and therefore `/mcp` and
`/api`) for the whole cycle. `SyncRunner` is the only async code here; it
calls the cycle via `anyio.to_thread.run_sync` so the server stays
responsive during a sync.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import anyio
from sqlalchemy.orm import Session, sessionmaker

from soft_floyd_core.activities.pipeline import ingest_activity
from soft_floyd_core.config import Settings
from soft_floyd_core.db import session_scope
from soft_floyd_core.garmin.client import GarminClient
from soft_floyd_core.garmin.errors import (
    GarminApiError,
    GarminNotFound,
    GarminRateLimited,
    ReauthRequired,
)
from soft_floyd_core.log import get_logger
from soft_floyd_core.models import GarminSyncState
from soft_floyd_core.notify import notify

log = get_logger(__name__)

# On an empty cursor (never synced before), ingest only the single most
# recent activity rather than silently mini-backfilling everything the
# API returns — historical backfill is a separate, out-of-scope feature.
FIRST_RUN_INGEST_LIMIT = 1

SyncStatus_ = str  # "ok" | "reauth_required" | "rate_limited" | "error"


@dataclass(frozen=True)
class SyncResult:
    new_activity_ids: list[int] = field(default_factory=list)
    skipped: int = 0
    status: SyncStatus_ = "ok"
    message: str | None = None
    retry_after_s: int | None = None


def get_or_create_sync_state(session: Session) -> GarminSyncState:
    """The single-row (id=1) durable sync state. Shared with garmin.login,
    which needs the same row for the login cooldown."""
    state = session.get(GarminSyncState, 1)
    if state is None:
        state = GarminSyncState(id=1)
        session.add(state)
        session.flush()
    return state


def _finish(
    session: Session,
    state: GarminSyncState,
    *,
    status: str,
    message: str | None,
    bump_errors: bool,
    new_ids: list[int] | None = None,
    skipped: int = 0,
    retry_after_s: int | None = None,
) -> SyncResult:
    state.last_sync_at = datetime.now(UTC)
    state.last_status = status
    state.last_error = message
    state.consecutive_errors = state.consecutive_errors + 1 if bump_errors else 0
    session.commit()
    return SyncResult(
        new_activity_ids=new_ids or [],
        skipped=skipped,
        status=status,
        message=message,
        retry_after_s=retry_after_s,
    )


def run_sync_cycle(
    session: Session,
    settings: Settings,
    client: GarminClient,
    *,
    should_stop: Callable[[], bool] = lambda: False,
) -> SyncResult:
    """One pass: list recent activities, ingest anything new, update sync
    state. Never raises — Garmin failures are reported via SyncResult.
    """
    state = get_or_create_sync_state(session)
    last_id = state.last_seen_activity_id

    try:
        activities = client.list_recent_activities(limit=settings.garmin_page_size)
    except ReauthRequired as exc:
        return _finish(
            session, state, status="reauth_required", message=str(exc), bump_errors=False
        )
    except GarminRateLimited as exc:
        return _finish(
            session,
            state,
            status="rate_limited",
            message=str(exc),
            bump_errors=True,
            retry_after_s=exc.retry_after_s,
        )
    except GarminApiError as exc:
        return _finish(session, state, status="error", message=str(exc), bump_errors=True)

    candidates = [a for a in activities if last_id is None or int(a.get("activityId", 0)) > last_id]
    candidates.sort(key=lambda a: int(a.get("activityId", 0)))

    if last_id is None and candidates:
        candidates = candidates[-FIRST_RUN_INGEST_LIMIT:]

    new_ids: list[int] = []
    skipped = 0
    max_seen = last_id

    for summary in candidates:
        if should_stop():
            break
        activity_id = int(summary.get("activityId", 0))
        try:
            activity = ingest_activity(session, settings, client, summary)
            if activity is not None:
                new_ids.append(activity.id)
            max_seen = activity_id if max_seen is None else max(max_seen, activity_id)
        except GarminNotFound:
            log.warning("sync.activity_not_found", activity_id=activity_id)
            skipped += 1
            max_seen = activity_id if max_seen is None else max(max_seen, activity_id)
            continue
        except ReauthRequired as exc:
            state.last_seen_activity_id = max_seen
            return _finish(
                session,
                state,
                status="reauth_required",
                message=str(exc),
                bump_errors=False,
                new_ids=new_ids,
                skipped=skipped,
            )
        except GarminRateLimited as exc:
            state.last_seen_activity_id = max_seen
            return _finish(
                session,
                state,
                status="rate_limited",
                message=str(exc),
                bump_errors=True,
                new_ids=new_ids,
                skipped=skipped,
                retry_after_s=exc.retry_after_s,
            )
        except GarminApiError as exc:
            state.last_seen_activity_id = max_seen
            return _finish(
                session,
                state,
                status="error",
                message=str(exc),
                bump_errors=True,
                new_ids=new_ids,
                skipped=skipped,
            )

    state.last_seen_activity_id = max_seen
    return _finish(
        session,
        state,
        status="ok",
        message=None,
        bump_errors=False,
        new_ids=new_ids,
        skipped=skipped,
    )


def backoff_seconds(settings: Settings, consecutive_errors: int) -> float:
    """Exponential backoff capped at settings.poll_max_backoff_minutes.
    The exponent is clamped so a long outage can't overflow the int math.
    """
    exponent = min(consecutive_errors, 12)
    base = settings.poll_interval_minutes * 60
    return min(base * (2**exponent), settings.poll_max_backoff_minutes * 60)


def rate_limited_delay_seconds(
    settings: Settings, consecutive_errors: int, retry_after_s: int | None
) -> float:
    """A short server-supplied Retry-After must not shrink a backoff
    we've already earned from repeated failures — take whichever is
    longer.
    """
    return max(retry_after_s or 0, backoff_seconds(settings, consecutive_errors))


class SyncRunner:
    """Owns the one GarminClient and the one lock for this process — a
    manual sync (MCP tool / REST route / CLI) and the background poll
    loop share both, so they can never race each other.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        client_factory: Callable[..., GarminClient] = GarminClient,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._client_factory = client_factory
        self._client: GarminClient | None = None
        self._lock = asyncio.Lock()
        self._stop_event = threading.Event()
        self._notified_reauth = False

    def _get_client(self) -> GarminClient:
        # Constructed lazily: GarminClient.load() makes a network call, so
        # it must happen on the worker thread, never at import/lifespan time.
        if self._client is None:
            self._client = self._client_factory(self._settings.garmin_token_dir)
        return self._client

    def _run_cycle_sync(self) -> SyncResult:
        with session_scope(self._session_factory) as session:
            return run_sync_cycle(
                session, self._settings, self._get_client(), should_stop=self._stop_event.is_set
            )

    async def sync_once(self) -> SyncResult:
        async with self._lock:
            return await anyio.to_thread.run_sync(self._run_cycle_sync)

    def request_stop(self) -> None:
        self._stop_event.set()

    async def _sleep_or_stop(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0 and not self._stop_event.is_set():
            step = min(remaining, 5.0)
            await asyncio.sleep(step)
            remaining -= step

    async def run_forever(self) -> None:
        if not self._settings.garmin_poll_enabled:
            return

        consecutive_errors = 0
        while not self._stop_event.is_set():
            result = await self.sync_once()

            if result.status == "ok":
                consecutive_errors = 0
                self._notified_reauth = False
                delay = self._settings.poll_interval_minutes * 60
            elif result.status == "reauth_required":
                # Re-check periodically rather than stopping outright, so a
                # fresh `soft-floyd garmin-login` is picked up without a
                # server restart — but don't hot-loop, and don't let this
                # count toward the error-backoff either.
                if not self._notified_reauth:
                    notify("Soft Floyd needs Garmin re-auth. Run `soft-floyd garmin-login`.")
                    self._notified_reauth = True
                delay = max(self._settings.poll_interval_minutes * 60, 900)
            elif result.status == "rate_limited":
                consecutive_errors += 1
                delay = rate_limited_delay_seconds(
                    self._settings, consecutive_errors, result.retry_after_s
                )
            else:
                consecutive_errors += 1
                delay = backoff_seconds(self._settings, consecutive_errors)

            await self._sleep_or_stop(delay)
