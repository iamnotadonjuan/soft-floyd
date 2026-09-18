"""map_garmin_exception with zero HTTP involvement — every case here
constructs an exception directly, never makes a network call. Confirms
respx (an httpx mock) would be pointless here anyway: garminconnect
transports over curl_cffi, not httpx, so mocking at the exception/object
boundary is the only approach robust to that.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)
from soft_floyd_core.garmin.errors import (
    GarminApiError,
    GarminNotFound,
    GarminRateLimited,
    ReauthRequired,
    map_garmin_exception,
)


def _raises(exc: BaseException):
    with pytest.raises(BaseException) as excinfo:
        map_garmin_exception(exc, action="test action")
    return excinfo.value


def test_authentication_error_is_reauth_required():
    result = _raises(GarminConnectAuthenticationError("bad creds"))
    assert isinstance(result, ReauthRequired)
    assert "test action" in str(result)


def test_too_many_requests_is_rate_limited():
    result = _raises(GarminConnectTooManyRequestsError("slow down"))
    assert isinstance(result, GarminRateLimited)
    assert result.retry_after_s is None  # no .response on this exception


def test_not_found_is_garmin_not_found():
    result = _raises(GarminConnectNotFoundError("no such activity"))
    assert isinstance(result, GarminNotFound)


def test_status_401_via_response_attribute_is_reauth_required():
    fake_response = SimpleNamespace(status_code=401, headers={})
    exc = Exception("boom")
    exc.response = fake_response  # type: ignore[attr-defined]
    result = _raises(exc)
    assert isinstance(result, ReauthRequired)


def test_status_429_with_integer_retry_after():
    fake_response = SimpleNamespace(status_code=429, headers={"Retry-After": "120"})
    exc = Exception("rate limited")
    exc.response = fake_response  # type: ignore[attr-defined]
    result = _raises(exc)
    assert isinstance(result, GarminRateLimited)
    assert result.retry_after_s == 120


def test_status_429_with_http_date_retry_after():
    fake_response = SimpleNamespace(
        status_code=429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}
    )
    exc = Exception("rate limited")
    exc.response = fake_response  # type: ignore[attr-defined]
    result = _raises(exc)
    assert isinstance(result, GarminRateLimited)
    assert result.retry_after_s is not None
    assert result.retry_after_s > 0


def test_garminconnect_connection_error_message_shape_is_generic_not_rate_limited():
    """garminconnect formats some errors as "API Error 503 - ...".
    Confirm that's parsed as a generic 5xx, not misfiled as rate-limited.
    """
    result = _raises(GarminConnectConnectionError("API Error 503 - Service Unavailable"))
    assert isinstance(result, GarminApiError)
    assert not isinstance(result, GarminRateLimited)
    assert not isinstance(result, ReauthRequired)


def test_stale_token_load_failure_is_reauth_required():
    """Client.load()'s wrapped message for a corrupt/expired token file —
    a GarminConnectConnectionError with no HTTP status at all. Without
    the message-shape check this falls through to a generic GarminApiError
    and the poller backs off forever instead of asking for a fresh login.
    """
    result = _raises(GarminConnectConnectionError("Token path not loading cleanly: [Errno 2] ..."))
    assert isinstance(result, ReauthRequired)


def test_stale_token_loads_structural_failure_is_reauth_required():
    result = _raises(GarminConnectConnectionError("Token extraction loads() structurally failed"))
    assert isinstance(result, ReauthRequired)


def test_status_404_via_message_regex_is_not_found():
    result = _raises(Exception("Error 404 - activity not found"))
    assert isinstance(result, GarminNotFound)


def test_unrecognizable_exception_is_generic_garmin_api_error():
    result = _raises(ValueError("something else entirely"))
    assert type(result) is GarminApiError


def test_isinstance_by_name_wins_even_with_a_response_attribute():
    """A real GarminConnectAuthenticationError might carry no .response,
    but if it somehow did, the isinstance-by-name check must still win —
    it's checked first precisely because these classes are unreliable
    sources of status codes.
    """
    exc = GarminConnectAuthenticationError("bad creds")
    exc.response = SimpleNamespace(status_code=500, headers={})  # would map to generic if reached
    result = _raises(exc)
    assert isinstance(result, ReauthRequired)
