"""Login cooldown around `GarminClient.login()`.

Garmin's login rate limit is account/IP-wide and lasts on the order of
30 minutes (`GarminConnectTooManyRequestsError("All login strategies
rate limited (429)...")` from the full 5-strategy SSO chain in
`garminconnect`). Retrying immediately after a 429 only re-triggers it.
This module persists a cooldown deadline in `GarminSyncState` (the same
single-row state `garmin.sync` already owns) so a repeated
`soft-floyd garmin-login` is refused locally, with no network call, while
the cooldown is active. See docs/exec-plans/completed/0003-garmin-auth-repair.md.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from soft_floyd_core.config import Settings
from soft_floyd_core.db import session_scope
from soft_floyd_core.garmin.client import GarminClient
from soft_floyd_core.garmin.errors import GarminApiError, GarminRateLimited
from soft_floyd_core.garmin.sync import get_or_create_sync_state

# How long the in-thread MFA callback (below) blocks waiting for a code
# before giving up — the browser login flow (exec-plan 0004) has this
# long to complete the two-step POST /login -> POST /mfa handshake.
MFA_WAIT_TIMEOUT_S = 120


def _utcnow_naive() -> datetime:
    # login_blocked_until is a plain (timezone-naive) DateTime column —
    # SQLite has no timezone-aware storage, so a tz-aware value written in
    # one session comes back naive when a later session reads it. Store
    # and compare naive-but-UTC consistently rather than mixing the two.
    return datetime.now(UTC).replace(tzinfo=None)


def perform_login(
    session: Session,
    settings: Settings,
    client: GarminClient,
    email: str,
    password: str,
    mfa_callback: Callable[[], str],
) -> None:
    """Log in, subject to the local cooldown. Raises GarminRateLimited
    without touching the network if a prior 429 cooldown hasn't elapsed;
    otherwise delegates to `client.login()` and re-raises whatever it
    raises, recording a fresh cooldown on a 429.

    On success, clears the cooldown and resets the sync error counters so
    a poller that was waiting on `reauth_required` resumes immediately.
    """
    state = get_or_create_sync_state(session)
    now = _utcnow_naive()

    if state.login_blocked_until is not None and state.login_blocked_until > now:
        remaining = int((state.login_blocked_until - now).total_seconds())
        raise GarminRateLimited(
            f"Garmin login is on cooldown for {remaining}s after a prior rate "
            f"limit. Wait before trying again.",
            retry_after_s=remaining,
        )

    try:
        client.login(email, password, mfa_callback)
    except GarminRateLimited as exc:
        cooldown_s = exc.retry_after_s or settings.garmin_login_cooldown_minutes * 60
        state.login_blocked_until = now + timedelta(seconds=cooldown_s)
        session.commit()
        raise

    state.login_blocked_until = None
    state.last_status = "never"
    state.last_error = None
    state.consecutive_errors = 0
    session.commit()


def clear_login_block(session: Session) -> None:
    """Called from `garmin-logout` — logging out shouldn't leave a stale
    cooldown blocking the next deliberate login attempt."""
    state = get_or_create_sync_state(session)
    state.login_blocked_until = None
    session.commit()


@dataclass
class PendingLogin:
    """In-process (never persisted) coordination state for one browser
    login attempt — exec-plan 0004. `garmin.sync.SyncRunner` owns the
    async/thread wiring around this; this dataclass is just the shared
    state the worker thread and the event loop both touch.

    mfa_requested fires the instant Garmin's SSO chain actually asks for
    a code — a login that doesn't need MFA never sets it. mfa_submitted
    fires once POST /api/connections/garmin/mfa provides one. done fires
    when the worker thread's call to perform_login returns or raises,
    whichever comes first; `error` holds what it raised, if anything.
    """

    mfa_requested: threading.Event = field(default_factory=threading.Event)
    mfa_code: str | None = None
    mfa_submitted: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    error: Exception | None = None


def _make_mfa_callback(pending: PendingLogin) -> Callable[[], str]:
    """Runs on the worker thread, inside client.login()'s synchronous SSO
    chain — blocks until the rider's MFA code arrives via
    SyncRunner.submit_mfa(), or times out.
    """

    def _callback() -> str:
        pending.mfa_requested.set()
        if not pending.mfa_submitted.wait(timeout=MFA_WAIT_TIMEOUT_S):
            raise GarminApiError(
                "Timed out waiting for the Garmin MFA code. Start the login again."
            )
        assert pending.mfa_code is not None  # mfa_submitted only ever set alongside mfa_code
        return pending.mfa_code

    return _callback


def run_login_in_background(
    session_factory: sessionmaker[Session],
    settings: Settings,
    client: GarminClient,
    email: str,
    password: str,
    pending: PendingLogin,
) -> threading.Thread:
    """Starts perform_login on a daemon thread with its own session
    (never share a Session across threads), wiring its mfa_callback to
    `pending`. Never raises directly — any exception from perform_login
    (including a re-raised GarminRateLimited from the cooldown check) is
    captured on `pending.error` for the caller to inspect once
    `pending.done` is set, matching the "never a raw exception across the
    thread boundary" shape the rest of this module already uses via
    SyncResult.
    """

    def _run() -> None:
        try:
            with session_scope(session_factory) as session:
                perform_login(
                    session, settings, client, email, password, _make_mfa_callback(pending)
                )
        except Exception as exc:  # noqa: BLE001 - surfaced via pending.error, not raised here
            pending.error = exc
        finally:
            pending.done.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
