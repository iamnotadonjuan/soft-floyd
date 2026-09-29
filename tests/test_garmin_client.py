"""GarminClient against a hand-written fake (not MagicMock, so a wrong
call signature fails loudly) — no garminconnect.Garmin is ever
constructed here; see conftest.py's autouse _no_real_garmin fixture.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from garminconnect import GarminConnectTooManyRequestsError
from soft_floyd_core.garmin.client import GarminClient
from soft_floyd_core.garmin.errors import GarminApiError, GarminRateLimited, ReauthRequired


class FakeGarmin:
    """Stands in for garminconnect.Garmin. Records how it was called.

    Writes garmin_tokens.json on login(), matching the real library's
    `Garmin.login()` -> `Client.dump()` behavior.
    """

    def __init__(self, email=None, password=None, prompt_mfa=None, **kwargs):
        self.email = email
        self.password = password
        self.prompt_mfa = prompt_mfa
        self.login_calls: list[str] = []
        self.get_activities_calls: list[dict] = []

    def login(self, tokenstore=None):
        self.login_calls.append(tokenstore)
        if tokenstore is not None:
            Path(tokenstore).mkdir(parents=True, exist_ok=True)
            (Path(tokenstore) / "garmin_tokens.json").write_text("{}")
        return ("token", "secret")

    def get_activities(self, start=0, limit=20, activitytype=None):
        self.get_activities_calls.append(
            {"start": start, "limit": limit, "activitytype": activitytype}
        )
        return [{"activityId": 1}]

    def download_activity(self, activity_id, dl_fmt=None):
        return b"not a zip, just raw fit bytes"


class SilentlyFailingDumpGarmin(FakeGarmin):
    """Mirrors garminconnect's `with contextlib.suppress(Exception):
    self.client.dump(...)` — login() returns cleanly but writes nothing.
    """

    def login(self, tokenstore=None):
        self.login_calls.append(tokenstore)
        return ("token", "secret")


class RaisingGarmin(FakeGarmin):
    def get_activities(self, start=0, limit=20, activitytype=None):
        raise GarminConnectTooManyRequestsError("slow down")


def test_login_passes_token_dir_as_tokenstore(tmp_path):
    client = GarminClient(tmp_path, client_factory=FakeGarmin)
    client.login("rider@example.com", "hunter2", lambda: "000000")
    assert client.has_token() is True
    # login() must call Garmin.login with the token dir as a string
    fake = client._client  # noqa: SLF001 (test introspection)
    assert fake.login_calls == [str(tmp_path)]


def test_login_raises_when_library_silently_fails_to_write_token(tmp_path):
    """garminconnect suppresses a failed token dump internally, so a
    `login()` that returns cleanly is not proof a token was written —
    GarminClient must check for itself. See exec-plan 0003."""
    client = GarminClient(tmp_path, client_factory=SilentlyFailingDumpGarmin)
    with pytest.raises(GarminApiError, match="no token was written"):
        client.login("rider@example.com", "hunter2", lambda: "000000")
    assert client.has_token() is False


def test_load_without_token_raises_reauth_required_without_constructing_client(tmp_path):
    client = GarminClient(tmp_path, client_factory=FakeGarmin)
    with pytest.raises(ReauthRequired):
        client.load()


def test_list_recent_activities_coerces_dict_to_empty_list(tmp_path):
    class DictReturningGarmin(FakeGarmin):
        def get_activities(self, start=0, limit=20, activitytype=None):
            self.get_activities_calls.append({"start": start, "limit": limit})
            return {"not": "a list"}

    (tmp_path / "garmin_tokens.json").write_text("{}")
    client = GarminClient(tmp_path, client_factory=DictReturningGarmin)
    result = client.list_recent_activities(limit=5)
    assert result == []


def test_list_recent_activities_passes_cycling_filter(tmp_path):
    (tmp_path / "garmin_tokens.json").write_text("{}")
    client = GarminClient(tmp_path, client_factory=FakeGarmin)
    client.list_recent_activities(limit=5, start=10)
    fake = client._client  # noqa: SLF001
    assert fake.get_activities_calls == [{"start": 10, "limit": 5, "activitytype": "cycling"}]


def test_list_recent_activities_maps_rate_limit_error(tmp_path):
    (tmp_path / "garmin_tokens.json").write_text("{}")
    client = GarminClient(tmp_path, client_factory=RaisingGarmin)
    with pytest.raises(GarminRateLimited):
        client.list_recent_activities()


def test_download_fit_writes_plain_payload_through(tmp_path):
    (tmp_path / "garmin_tokens.json").write_text("{}")
    client = GarminClient(tmp_path, client_factory=FakeGarmin)
    dest = tmp_path / "out" / "123.fit"
    client.download_fit(123, dest)
    assert dest.read_bytes() == b"not a zip, just raw fit bytes"


def test_download_fit_unwraps_zip_payload(tmp_path):
    class ZipGarmin(FakeGarmin):
        def download_activity(self, activity_id, dl_fmt=None):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("123_ACTIVITY.fit", b"the real fit bytes")
            return buf.getvalue()

    (tmp_path / "garmin_tokens.json").write_text("{}")
    client = GarminClient(tmp_path, client_factory=ZipGarmin)
    dest = tmp_path / "123.fit"
    client.download_fit(123, dest)
    assert dest.read_bytes() == b"the real fit bytes"


def test_client_factory_default_is_the_real_garminconnect_class():
    """Guards against the injection seam silently drifting: if someone
    changes the default away from the real Garmin class without updating
    this test, that's a signal the production code path is untested.
    """
    import inspect

    from garminconnect import Garmin

    default = inspect.signature(GarminClient.__init__).parameters["client_factory"].default
    assert default is Garmin


# ---- workout upload: steps, retry, partial success ---------------------------


class WorkoutGarmin(FakeGarmin):
    """Records workout calls; `failures` maps a method name to the exceptions
    it raises, in order, before it starts succeeding."""

    def __init__(self, *args, failures=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.failures = {k: list(v) for k, v in (failures or {}).items()}
        self.calls: list[tuple] = []

    def _maybe_fail(self, name):
        queue = self.failures.get(name)
        if queue:
            raise queue.pop(0)

    def upload_workout(self, payload):
        self.calls.append(("upload", payload))
        self._maybe_fail("upload_workout")
        return {"workoutId": 777}

    def update_workout(self, workout_id, payload):
        self.calls.append(("update", workout_id))
        self._maybe_fail("update_workout")
        return {}

    def schedule_workout(self, workout_id, date_str):
        self.calls.append(("schedule", workout_id, date_str))
        self._maybe_fail("schedule_workout")
        return {}


def _workout_client(tmp_path, **failures):
    holder = {}

    def factory(*args, **kwargs):
        holder["fake"] = WorkoutGarmin(*args, failures=failures, **kwargs)
        return holder["fake"]

    client = GarminClient(tmp_path, client_factory=factory, retry_delay_s=0)
    client._client = factory()  # what load()/login() would have set
    return client, holder["fake"]


def test_upload_creates_then_schedules(tmp_path):
    import datetime as dt

    client, fake = _workout_client(tmp_path)
    workout_id = client.upload_and_schedule_workout({"w": 1}, dt.date(2026, 9, 30))

    assert workout_id == "777"
    assert [c[0] for c in fake.calls] == ["upload", "schedule"]
    assert fake.calls[1] == ("schedule", "777", "2026-09-30")


def test_resend_updates_the_same_workout(tmp_path):
    import datetime as dt

    client, fake = _workout_client(tmp_path)
    workout_id = client.upload_and_schedule_workout({"w": 1}, dt.date(2026, 9, 30), "555")

    assert workout_id == "555"
    assert [c[0] for c in fake.calls] == ["update", "schedule"]


def test_a_cloudflare_origin_error_is_retried_once(tmp_path):
    import datetime as dt

    from garminconnect import GarminConnectConnectionError

    client, fake = _workout_client(
        tmp_path, upload_workout=[GarminConnectConnectionError("API Error 521")]
    )
    assert client.upload_and_schedule_workout({"w": 1}, dt.date(2026, 9, 30)) == "777"
    assert [c[0] for c in fake.calls] == ["upload", "upload", "schedule"]


def test_a_persistent_521_gives_up_after_one_retry_with_the_upload_step_named(tmp_path):
    import datetime as dt

    from garminconnect import GarminConnectConnectionError
    from soft_floyd_core.garmin.errors import USER_UNAVAILABLE, GarminUnavailable

    errors = [GarminConnectConnectionError("API Error 521")] * 2
    client, fake = _workout_client(tmp_path, upload_workout=errors)

    with pytest.raises(GarminUnavailable) as caught:
        client.upload_and_schedule_workout({"w": 1}, dt.date(2026, 9, 30))

    assert [c[0] for c in fake.calls] == ["upload", "upload"]
    assert "Garmin workout upload" in str(caught.value)
    assert "HTTP 521" in str(caught.value)
    assert caught.value.user_message == USER_UNAVAILABLE


@pytest.mark.parametrize("message", ["API Error 500", "API Error 503", "API Error 400"])
def test_other_failures_are_not_retried(tmp_path, message):
    import datetime as dt

    from garminconnect import GarminConnectConnectionError

    client, fake = _workout_client(
        tmp_path, upload_workout=[GarminConnectConnectionError(message)] * 2
    )
    with pytest.raises(GarminApiError):
        client.upload_and_schedule_workout({"w": 1}, dt.date(2026, 9, 30))
    assert [c[0] for c in fake.calls] == ["upload"]


def test_a_scheduling_failure_keeps_the_saved_workouts_id(tmp_path):
    import datetime as dt

    from garminconnect import GarminConnectConnectionError
    from soft_floyd_core.garmin.errors import USER_NOT_SCHEDULED, WorkoutNotScheduled

    client, fake = _workout_client(
        tmp_path, schedule_workout=[GarminConnectConnectionError("API Error 503")]
    )
    with pytest.raises(WorkoutNotScheduled) as caught:
        client.upload_and_schedule_workout({"w": 1}, dt.date(2026, 9, 30))

    assert caught.value.workout_id == "777"
    assert caught.value.status == 503
    assert caught.value.user_message == USER_NOT_SCHEDULED
    assert "Garmin workout scheduling" in str(caught.value)
