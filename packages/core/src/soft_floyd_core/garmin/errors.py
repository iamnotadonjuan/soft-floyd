r"""Garmin error taxonomy and exception-mapping.

Ported from v0 (`v0-legacy:src/coach/ingest/garmin_client.py`) with three
changes: `map_garmin_exception` is public (directly unit-testable without
a private name), a `GarminNotFound` class handles 404s (a single missing
activity shouldn't abort a whole sync cycle), and the status-sniffing
regex additionally matches `garminconnect`'s own error-message shape
("API Error 503 - ...") before falling back to v0's looser `\b(4\d\d|5\d\d)\b`.

Check order matters: `GarminConnectAuthenticationError` and
`GarminConnectTooManyRequestsError` carry no `.response` at all, so they
must be checked by `isinstance` before status-sniffing (which would find
nothing and fall through to a generic `GarminApiError`).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import NoReturn


class GarminApiError(Exception):
    pass


class ReauthRequired(GarminApiError):
    pass


class GarminNotFound(GarminApiError):
    pass


class GarminRateLimited(GarminApiError):
    def __init__(self, message: str, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


_STATUS_RE = re.compile(r"(?:API Error|Error|HTTP)\s*(\d{3})|\b(4\d\d|5\d\d)\b")


def _exception_response(exc: object) -> object | None:
    response = getattr(exc, "response", None)
    if response is not None:
        return response
    error = getattr(exc, "error", None)
    return getattr(error, "response", None)


def _exception_status_code(exc: object) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return int(status)

    response = _exception_response(exc)
    status = getattr(response, "status_code", None)
    if status is not None:
        return int(status)

    error = getattr(exc, "error", None)
    status = getattr(error, "status_code", None)
    if status is not None:
        return int(status)

    match = _STATUS_RE.search(str(exc))
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def _exception_retry_after_s(exc: object) -> int | None:
    response = _exception_response(exc)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("Retry-After")
    if not retry_after:
        return None

    try:
        return max(0, int(retry_after))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0, int((retry_at - datetime.now(UTC)).total_seconds()))


def map_garmin_exception(
    exc: BaseException,
    *,
    action: str,
    reauth_message: str = "Garmin session expired. Run `soft-floyd garmin-login`.",
) -> NoReturn:
    """Translate a garminconnect exception into our taxonomy and raise it.

    Every Garmin call site funnels its `except Exception` through this —
    see garmin/client.py. `action` prefixes the message so callers (CLI,
    poller logs, MCP tool errors) always say what was being attempted.
    """
    type_name = type(exc).__name__

    # These two carry no `.response` — isinstance (by name, so we don't
    # hard-depend on garminconnect's exact class objects) must win before
    # status-sniffing finds nothing and falls through to generic.
    if type_name == "GarminConnectAuthenticationError":
        raise ReauthRequired(f"{action}: {reauth_message}") from exc
    if type_name == "GarminConnectTooManyRequestsError":
        retry_after_s = _exception_retry_after_s(exc)
        raise GarminRateLimited(
            f"{action}: Garmin is rate limiting requests. Try again later.",
            retry_after_s=retry_after_s,
        ) from exc
    if type_name == "GarminConnectNotFoundError":
        raise GarminNotFound(f"{action}: Garmin reported this activity as not found.") from exc

    status = _exception_status_code(exc)
    if status == 401:
        raise ReauthRequired(f"{action}: {reauth_message}") from exc
    if status == 429:
        retry_after_s = _exception_retry_after_s(exc)
        raise GarminRateLimited(
            f"{action}: Garmin is rate limiting requests. Try again later.",
            retry_after_s=retry_after_s,
        ) from exc
    if status == 404:
        raise GarminNotFound(f"{action}: Garmin reported this activity as not found.") from exc
    if status is not None:
        raise GarminApiError(f"{action}: Garmin API returned HTTP {status}: {exc}") from exc
    raise GarminApiError(f"{action}: Garmin API request failed: {exc}") from exc
