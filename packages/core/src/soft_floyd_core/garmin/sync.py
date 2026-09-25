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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import anyio
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    # Deferred to avoid a module-level import cycle: garmin.login imports
    # get_or_create_sync_state from this module. login()/submit_mfa()
    # below import garmin.login locally, at call time, instead.
    from soft_floyd_core.garmin.login import PendingLogin

from soft_floyd_core.account_scope import account_id, enter_account, leave_account
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


@dataclass(frozen=True)
class LoginStartResult:
    """Returned by SyncRunner.login()/submit_mfa() — exec-plan 0004's
    browser login handshake. "mfa_required" means the caller must follow
    up with submit_mfa(code); "connected" means the login already
    finished (with or without MFA)."""

    state: str  # "connected" | "mfa_required"


class LoginAlreadyInProgress(Exception):
    """Raised by SyncRunner.login() if a prior login is still pending an
    MFA code — this single-rider app only ever has one Garmin login in
    flight at a time."""


class NoPendingLoginError(Exception):
    """Raised by SyncRunner.submit_mfa() if no login is currently waiting
    on an MFA code (never started, already finished, or already timed
    out)."""


def _wait_for_first_event(
    events: list[threading.Event], timeout: float, poll_interval: float = 0.1
) -> None:
    """Blocks (on a worker thread — always call via anyio.to_thread.run_sync)
    until any one of `events` is set, or `timeout` elapses. threading has
    no native "wait for first of several events" primitive, so this polls
    — the same shape as SyncRunner._sleep_or_stop's poll loop below.
    """
    elapsed = 0.0
    while elapsed < timeout:
        if any(e.is_set() for e in events):
            return
        time.sleep(poll_interval)
        elapsed += poll_interval


def get_or_create_sync_state(session: Session) -> GarminSyncState:
    """The single-row (id=1) durable sync state. Shared with garmin.login,
    which needs the same row for the login cooldown."""
    owner = account_id(session)
    state = session.scalar(select(GarminSyncState).where(GarminSyncState.account_id == owner))
    if state is None:
        state = GarminSyncState(account_id=owner)
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
                new_ids.append(activity.garmin_id)
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
        account_id: int,
        client_factory: Callable[..., GarminClient] = GarminClient,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._account_id = account_id
        self._client_factory = client_factory
        self._client: GarminClient | None = None
        self._lock = asyncio.Lock()
        self._stop_event = threading.Event()
        self._notified_reauth = False
        # exec-plan 0004's browser login handshake — see login()/submit_mfa().
        self._pending_login: PendingLogin | None = None

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

    def logout(self) -> None:
        """Removes the cached Garmin token via this runner's own
        GarminClient — never construct a second GarminClient to do this,
        or the in-memory object sync_once()/login() keep reusing would
        still believe it's logged in after a browser-initiated disconnect
        (garminconnect.Garmin caches its session state in the object,
        independent of the token file on disk)."""
        self._get_client().logout()

    async def login(self, email: str, password: str) -> LoginStartResult:
        """Start a Garmin login from the browser (exec-plan 0004). Takes
        the same `self._lock` sync_once() does, for as long as the login
        is in flight — including across the two-request MFA handshake —
        so a background poll cycle can never race a login attempt.

        Returns "connected" if no MFA was needed (or it somehow finished
        before we finished waiting), or "mfa_required" if the caller must
        follow up with submit_mfa(). Re-raises whatever perform_login
        raised (GarminRateLimited, ReauthRequired, GarminApiError) if the
        login failed outright, before any MFA prompt.
        """
        # Local import — see the TYPE_CHECKING note above the class for why.
        from soft_floyd_core.garmin.login import (
            MFA_WAIT_TIMEOUT_S,
            PendingLogin,
            run_login_in_background,
        )

        if self._pending_login is not None and not self._pending_login.done.is_set():
            raise LoginAlreadyInProgress("A Garmin login is already in progress.")

        await self._lock.acquire()
        pending = PendingLogin()
        self._pending_login = pending
        run_login_in_background(
            self._session_factory,
            self._settings,
            self._get_client(),
            email,
            password,
            pending,
            self._account_id,
        )

        await anyio.to_thread.run_sync(
            _wait_for_first_event, [pending.mfa_requested, pending.done], MFA_WAIT_TIMEOUT_S
        )

        if pending.done.is_set():
            if self._pending_login is pending:
                self._pending_login = None
            self._lock.release()
            if pending.error is not None:
                raise pending.error
            return LoginStartResult(state="connected")

        # MFA required and the rider hasn't answered yet. Hand off the
        # lock/pending cleanup to a background watcher so it's released
        # even if the browser tab is closed and submit_mfa() never comes
        # — bounded by the worker thread's own MFA timeout.
        asyncio.create_task(self._release_login_when_done(pending))
        return LoginStartResult(state="mfa_required")

    async def _release_login_when_done(self, pending: PendingLogin) -> None:
        await anyio.to_thread.run_sync(pending.done.wait)
        if self._pending_login is pending:
            self._pending_login = None
        self._lock.release()

    async def submit_mfa(self, code: str) -> LoginStartResult:
        """Second half of login() — provides the MFA code the worker
        thread's login callback is blocked on. Does not touch the lock
        itself; _release_login_when_done (already running, scheduled by
        login()) owns that, so there is exactly one release path.
        """
        from soft_floyd_core.garmin.login import MFA_WAIT_TIMEOUT_S

        pending = self._pending_login
        if pending is None or not pending.mfa_requested.is_set() or pending.done.is_set():
            raise NoPendingLoginError("No Garmin login is currently waiting for an MFA code.")

        pending.mfa_code = code
        pending.mfa_submitted.set()

        finished = await anyio.to_thread.run_sync(pending.done.wait, MFA_WAIT_TIMEOUT_S + 10)
        if not finished:
            raise GarminApiError("Garmin login timed out after the MFA code was submitted.")
        if pending.error is not None:
            raise pending.error
        return LoginStartResult(state="connected")

    async def _sleep_or_stop(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0 and not self._stop_event.is_set():
            step = min(remaining, 5.0)
            await asyncio.sleep(step)
            remaining -= step

    async def run_forever(self) -> None:
        if not self._settings.garmin_poll_enabled:
            return

        token = enter_account(self._account_id)
        try:
            await self._run_forever_scoped()
        finally:
            leave_account(token)

    async def _run_forever_scoped(self) -> None:

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
