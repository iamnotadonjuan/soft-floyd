"""Connected apps: connections/service.py's status mapping, and
SyncRunner's browser login handshake (login/submit_mfa) — exec-plan
0004. The login tests use a hand-written fake client (never a real
GarminClient/garminconnect.Garmin), same convention as
tests/test_garmin_login.py and tests/test_sync_cycle.py.
"""

from __future__ import annotations

import asyncio

import pytest
from soft_floyd_core.config import Settings
from soft_floyd_core.connections.service import list_connections
from soft_floyd_core.db import make_engine, make_session_factory, session_scope
from soft_floyd_core.garmin.errors import GarminRateLimited, ReauthRequired
from soft_floyd_core.garmin.sync import LoginAlreadyInProgress, NoPendingLoginError, SyncRunner
from soft_floyd_core.models import GarminSyncState


def _settings(tmp_path) -> Settings:
    return Settings(
        db_path=tmp_path / "db.sqlite",
        garmin_token_dir=tmp_path / "garmin",
        garmin_poll_enabled=False,
    )


def _session_factory(settings: Settings):
    engine = make_engine(settings.db_path)
    return make_session_factory(engine)


def _touch_token(settings: Settings) -> None:
    token_dir = settings.garmin_token_dir / "1"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "garmin_tokens.json").write_text("{}")


# --- list_connections status mapping ------------------------------------


@pytest.mark.parametrize(
    ("authenticated", "last_status", "expected"),
    [
        (False, "never", "disconnected"),
        (False, "reauth_required", "disconnected"),  # no token at all wins over a stale status
        (True, "never", "connected"),  # fresh login, hasn't synced yet
        (True, "ok", "connected"),
        (True, "reauth_required", "reauth_required"),
        (True, "rate_limited", "rate_limited"),
        (True, "error", "error"),
    ],
)
def test_status_mapping(tmp_path, authenticated, last_status, expected):
    settings = _settings(tmp_path)
    sf = _session_factory(settings)

    with session_scope(sf) as session:
        session.add(GarminSyncState(id=1, last_status=last_status))

    if authenticated:
        _touch_token(settings)

    with session_scope(sf) as session:
        [connection] = list_connections(session, settings)

    assert connection.provider == "garmin"
    assert connection.display_name == "Garmin Connect"
    assert connection.status == expected
    assert connection.supports_login_in_app is True


def test_detail_only_present_while_connected(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(settings)
    _touch_token(settings)

    with session_scope(sf) as session:
        [connected] = list_connections(session, settings)
    assert connected.status == "connected"
    assert connected.detail is not None

    with session_scope(sf) as session:
        state = session.get(GarminSyncState, 1) or GarminSyncState(id=1)
        session.add(state)
        state.last_status = "rate_limited"
        session.commit()

    with session_scope(sf) as session:
        [limited] = list_connections(session, settings)
    assert limited.detail is None


def test_last_error_is_passed_through_verbatim(tmp_path):
    settings = _settings(tmp_path)
    sf = _session_factory(settings)
    _touch_token(settings)

    with session_scope(sf) as session:
        session.add(
            GarminSyncState(id=1, last_status="error", last_error="Garmin API returned 503")
        )

    with session_scope(sf) as session:
        [connection] = list_connections(session, settings)

    assert connection.last_error == "Garmin API returned 503"


# --- SyncRunner.login / submit_mfa --------------------------------------


class FakeGarminClient:
    """Same shape as test_garmin_login.py's fake, extended to optionally
    prompt for MFA and validate the submitted code — matches
    GarminClient's real login(email, password, mfa_callback) signature.
    """

    def __init__(
        self,
        _token_dir,
        *,
        require_mfa: bool = False,
        valid_code: str = "123456",
        raise_on_login: Exception | None = None,
    ) -> None:
        self.require_mfa = require_mfa
        self.valid_code = valid_code
        self.raise_on_login = raise_on_login
        self.logged_out = False

    def login(self, email, password, mfa_callback):
        if self.raise_on_login is not None:
            raise self.raise_on_login
        if self.require_mfa:
            code = mfa_callback()
            if code != self.valid_code:
                raise ReauthRequired("Garmin rejected the MFA code.")

    def logout(self) -> None:
        self.logged_out = True


def _runner(tmp_path, **client_kwargs) -> SyncRunner:
    settings = _settings(tmp_path)
    sf = _session_factory(settings)

    def factory(token_dir):
        return FakeGarminClient(token_dir, **client_kwargs)

    return SyncRunner(sf, settings, account_id=1, client_factory=factory)


async def test_login_without_mfa_connects_immediately_and_releases_the_lock(tmp_path):
    runner = _runner(tmp_path)

    result = await runner.login("rider@example.com", "hunter2")
    assert result.state == "connected"

    # The lock was released — a second login doesn't hang or raise
    # LoginAlreadyInProgress.
    result2 = await runner.login("rider@example.com", "hunter2")
    assert result2.state == "connected"


async def test_login_with_correct_mfa_code_connects(tmp_path):
    runner = _runner(tmp_path, require_mfa=True, valid_code="654321")

    start = await runner.login("rider@example.com", "hunter2")
    assert start.state == "mfa_required"

    finish = await runner.submit_mfa("654321")
    assert finish.state == "connected"


async def test_login_with_wrong_mfa_code_raises_and_still_releases_the_lock(tmp_path):
    runner = _runner(tmp_path, require_mfa=True, valid_code="654321")

    start = await runner.login("rider@example.com", "hunter2")
    assert start.state == "mfa_required"

    with pytest.raises(ReauthRequired):
        await runner.submit_mfa("000000")

    # A fresh attempt is possible right away — nothing left the lock held.
    retry = await runner.login("rider@example.com", "hunter2")
    assert retry.state == "mfa_required"
    await runner.submit_mfa("654321")  # let the daemon thread finish cleanly


async def test_second_login_while_mfa_pending_is_refused(tmp_path):
    runner = _runner(tmp_path, require_mfa=True)

    start = await runner.login("rider@example.com", "hunter2")
    assert start.state == "mfa_required"

    with pytest.raises(LoginAlreadyInProgress):
        await runner.login("rider@example.com", "hunter2")

    await runner.submit_mfa("123456")  # clean up


async def test_submit_mfa_without_a_pending_login_raises(tmp_path):
    runner = _runner(tmp_path)

    with pytest.raises(NoPendingLoginError):
        await runner.submit_mfa("123456")


async def test_login_surfaces_rate_limit_and_the_local_cooldown_on_retry(tmp_path):
    """The 429 -> cooldown behavior is perform_login's (tests/test_garmin_login.py
    covers it directly); this asserts SyncRunner's login() surfaces both
    the original error and the subsequent local refusal unchanged.
    """
    runner = _runner(tmp_path, raise_on_login=GarminRateLimited("slow down", retry_after_s=60))

    with pytest.raises(GarminRateLimited):
        await runner.login("rider@example.com", "hunter2")

    with pytest.raises(GarminRateLimited, match="cooldown"):
        await runner.login("rider@example.com", "hunter2")


async def test_abandoned_mfa_wait_times_out_and_releases_the_lock(tmp_path, monkeypatch):
    """If the browser tab is closed and submit_mfa() never comes, the
    worker thread's own MFA wait must give up and the lock must still be
    released — not wedge every future sync/login for this process.
    """
    monkeypatch.setattr("soft_floyd_core.garmin.login.MFA_WAIT_TIMEOUT_S", 0.2)
    runner = _runner(tmp_path, require_mfa=True)

    start = await runner.login("rider@example.com", "hunter2")
    assert start.state == "mfa_required"

    await asyncio.sleep(0.6)  # let the worker thread's own timeout fire

    retry = await runner.login("rider@example.com", "hunter2")
    assert retry.state == "mfa_required"
    await runner.submit_mfa("123456")  # clean up


def test_logout_uses_the_runners_own_client_not_a_second_one(tmp_path):
    """See SyncRunner.logout()'s docstring — constructing a second
    GarminClient to log out would leave the runner's own in-memory client
    still believing it's authenticated."""
    runner = _runner(tmp_path)
    runner.logout()
    assert runner._client.logged_out is True  # noqa: SLF001 - the property under test
