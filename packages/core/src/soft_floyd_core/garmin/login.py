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

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from soft_floyd_core.config import Settings
from soft_floyd_core.garmin.client import GarminClient
from soft_floyd_core.garmin.errors import GarminRateLimited
from soft_floyd_core.garmin.sync import get_or_create_sync_state


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
