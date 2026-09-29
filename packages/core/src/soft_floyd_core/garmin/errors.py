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

from soft_floyd_core.log import get_logger

_log = get_logger(__name__)

# What a rider may see. The technical text (HTTP status, library message)
# stays in `str(exc)` for logs and the CLI; see `GarminApiError.user_message`.
USER_UNAVAILABLE = "Garmin Connect isn't responding right now. Please try again in a few minutes."
USER_REFUSED = "Garmin didn't accept this request. Please try again in a few minutes."
USER_GENERIC = "Something went wrong talking to Garmin Connect. Please try again in a few minutes."
USER_RATE_LIMITED = "Garmin is limiting requests right now. Please try again later."
USER_REAUTH = "Your Garmin connection has expired. Reconnect Garmin in Settings."
USER_NOT_FOUND = "Garmin couldn't find that activity."
USER_NOT_SCHEDULED = (
    "The workout reached Garmin Connect but couldn't be added to your calendar. "
    "Please try sending it again in a few minutes."
)


class GarminApiError(Exception):
    """`str(exc)` is the technical message (HTTP status, upstream text): for
    logs, the CLI and MCP clients. `user_message` is the plain-language
    version safe to show a rider in the web app; it defaults to the message
    for errors we wrote ourselves for riders (login cooldowns, MFA, ...)."""

    def __init__(
        self, message: str, *, user_message: str | None = None, status: int | None = None
    ) -> None:
        super().__init__(message)
        self.user_message = user_message or message
        self.status = status


class ReauthRequired(GarminApiError):
    pass


class GarminNotFound(GarminApiError):
    pass


class GarminRateLimited(GarminApiError):
    def __init__(
        self,
        message: str,
        retry_after_s: int | None = None,
        *,
        user_message: str | None = None,
    ) -> None:
        super().__init__(message, user_message=user_message, status=429)
        self.retry_after_s = retry_after_s


class GarminUnavailable(GarminApiError):
    """Garmin (or the Cloudflare edge in front of it) answered with a 5xx, or
    could not be reached. Usually transient and not our request's fault."""


class WorkoutNotScheduled(GarminApiError):
    """The workout was created or updated on Garmin, but scheduling it on the
    calendar failed. Carries the Garmin workout id so a retry updates that
    workout instead of creating a duplicate."""

    def __init__(self, message: str, *, workout_id: str, status: int | None = None) -> None:
        super().__init__(message, user_message=USER_NOT_SCHEDULED, status=status)
        self.workout_id = workout_id


# Cloudflare's "the origin refused / dropped / didn't answer the connection"
# codes. For these the request never reached Garmin's servers, so even a
# non-idempotent POST is safe to send again.
CLOUDFLARE_ORIGIN_UNREACHABLE = frozenset({521, 522, 523})


_STATUS_RE = re.compile(r"(?:API Error|Error|HTTP)\s*(\d{3})|\b(4\d\d|5\d\d)\b")

# garminconnect re-wraps a structurally bad/expired token file into
# GarminConnectConnectionError instead of an auth error (e.g. Client.load()'s
# "Token path not loading cleanly: ..." and Client.loads()'s "Token
# extraction loads() structurally failed" / "Missing tokens from dict
# load"). Those carry no HTTP status at all, so without this check they'd
# fall through status-sniffing to a generic GarminApiError and the poller
# would back off forever instead of asking for a fresh `garmin-login`.
_STALE_TOKEN_RE = re.compile(
    r"Token path not loading cleanly|loads\(\) structurally failed|Missing tokens"
)


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


def garmin_status(exc: object) -> int | None:
    """The HTTP status behind a garminconnect exception, if it has one."""
    return _exception_status_code(exc)


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
        _log_failure(action, exc, None)
        raise ReauthRequired(f"{action}: {reauth_message}", user_message=USER_REAUTH) from exc
    if type_name == "GarminConnectTooManyRequestsError":
        retry_after_s = _exception_retry_after_s(exc)
        _log_failure(action, exc, 429)
        raise GarminRateLimited(
            f"{action}: Garmin is rate limiting requests. Try again later.",
            retry_after_s=retry_after_s,
            user_message=USER_RATE_LIMITED,
        ) from exc
    if type_name == "GarminConnectNotFoundError":
        _log_failure(action, exc, 404)
        raise GarminNotFound(
            f"{action}: Garmin reported this activity as not found.",
            user_message=USER_NOT_FOUND,
            status=404,
        ) from exc
    if type_name == "GarminConnectConnectionError" and _STALE_TOKEN_RE.search(str(exc)):
        _log_failure(action, exc, None)
        raise ReauthRequired(f"{action}: {reauth_message}", user_message=USER_REAUTH) from exc

    status = _exception_status_code(exc)
    _log_failure(action, exc, status)
    if status == 401:
        raise ReauthRequired(
            f"{action}: {reauth_message}", user_message=USER_REAUTH, status=401
        ) from exc
    if status == 429:
        retry_after_s = _exception_retry_after_s(exc)
        raise GarminRateLimited(
            f"{action}: Garmin is rate limiting requests. Try again later.",
            retry_after_s=retry_after_s,
            user_message=USER_RATE_LIMITED,
        ) from exc
    if status == 404:
        raise GarminNotFound(
            f"{action}: Garmin reported this activity as not found.",
            user_message=USER_NOT_FOUND,
            status=404,
        ) from exc
    if status is not None and status >= 500:
        raise GarminUnavailable(
            f"{action}: Garmin API returned HTTP {status}: {exc}",
            user_message=USER_UNAVAILABLE,
            status=status,
        ) from exc
    if status is not None:
        raise GarminApiError(
            f"{action}: Garmin API returned HTTP {status}: {exc}",
            user_message=USER_REFUSED,
            status=status,
        ) from exc
    raise GarminApiError(
        f"{action}: Garmin API request failed: {exc}", user_message=USER_GENERIC
    ) from exc


def _log_failure(action: str, exc: BaseException, status: int | None) -> None:
    """The real error, for whoever debugs it: the rider only sees
    `user_message`. `str(exc)` holds garminconnect's own text (status and any
    detail Garmin returned), never a token or a password."""
    _log.warning(
        "garmin_request_failed",
        action=action,
        status=status,
        error_type=type(exc).__name__,
        error=str(exc),
    )
