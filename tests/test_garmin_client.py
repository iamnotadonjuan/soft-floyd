from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

import pytest
from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

from coach.ingest.garmin_client import (
    GarminApiError,
    GarminRateLimited,
    ReauthRequired,
    _fit_payload,
    _raise_garmin_error,
)


class _Response:
    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        self.status_code = status_code
        self.headers = {}
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after


class _HTTPError:
    def __init__(self, response: _Response) -> None:
        self.response = response


class _GarthError(Exception):
    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        super().__init__(f"{status_code} error")
        self.error = _HTTPError(_Response(status_code, retry_after))


def _garmin_error(status_code: int, retry_after: str | None = None) -> _GarthError:
    return _GarthError(status_code, retry_after)


def test_http_401_maps_to_reauth_required():
    with pytest.raises(ReauthRequired):
        _raise_garmin_error(_garmin_error(401), action="Garmin API GET /x")


def test_http_429_maps_to_rate_limited_with_retry_after():
    with pytest.raises(GarminRateLimited) as exc_info:
        _raise_garmin_error(_garmin_error(429, retry_after="120"), action="Garmin login failed")

    assert exc_info.value.retry_after_s == 120


def test_garminconnect_auth_error_maps_to_reauth_required():
    with pytest.raises(ReauthRequired):
        _raise_garmin_error(GarminConnectAuthenticationError("bad auth"), action="Garmin login")


def test_garminconnect_rate_limit_maps_to_rate_limited():
    with pytest.raises(GarminRateLimited):
        _raise_garmin_error(
            GarminConnectTooManyRequestsError("too many requests"),
            action="Garmin login",
        )


def test_fit_payload_extracts_fit_from_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("activity.fit", b"fit-bytes")

    assert _fit_payload(buf.getvalue()) == b"fit-bytes"


def test_fit_payload_rejects_zip_without_fit():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("readme.txt", b"not fit")

    with pytest.raises(GarminApiError):
        _fit_payload(buf.getvalue())


def test_wellness_rate_limit_propagates():
    from coach.ingest.garmin_client import GarminClient

    class FakeGarmin:
        def get_hrv_data(self, _date_str):
            raise GarminConnectTooManyRequestsError("429")

    client = GarminClient(cfg=object())
    client._client = FakeGarmin()

    with pytest.raises(GarminRateLimited):
        client.get_wellness(datetime(2026, 5, 20, tzinfo=UTC))
