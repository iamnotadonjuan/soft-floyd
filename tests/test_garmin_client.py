"""GarminClient against a hand-written fake (not MagicMock, so a wrong
call signature fails loudly) — no garminconnect.Garmin is ever
constructed here; see conftest.py's autouse _no_real_garmin fixture.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from garminconnect import GarminConnectTooManyRequestsError
from soft_floyd_core.garmin.client import GarminClient
from soft_floyd_core.garmin.errors import GarminRateLimited, ReauthRequired


class FakeGarmin:
    """Stands in for garminconnect.Garmin. Records how it was called."""

    def __init__(self, email=None, password=None, prompt_mfa=None, **kwargs):
        self.email = email
        self.password = password
        self.prompt_mfa = prompt_mfa
        self.login_calls: list[str] = []
        self.get_activities_calls: list[dict] = []

    def login(self, tokenstore=None):
        self.login_calls.append(tokenstore)
        return ("token", "secret")

    def get_activities(self, start=0, limit=20, activitytype=None):
        self.get_activities_calls.append(
            {"start": start, "limit": limit, "activitytype": activitytype}
        )
        return [{"activityId": 1}]

    def download_activity(self, activity_id, dl_fmt=None):
        return b"not a zip, just raw fit bytes"


class RaisingGarmin(FakeGarmin):
    def get_activities(self, start=0, limit=20, activitytype=None):
        raise GarminConnectTooManyRequestsError("slow down")


def test_login_passes_token_dir_as_tokenstore(tmp_path):
    client = GarminClient(tmp_path, client_factory=FakeGarmin)
    client.login("rider@example.com", "hunter2", lambda: "000000")
    assert client.has_token() is False  # FakeGarmin doesn't actually write a file
    # login() must call Garmin.login with the token dir as a string
    fake = client._client  # noqa: SLF001 (test introspection)
    assert fake.login_calls == [str(tmp_path)]


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
