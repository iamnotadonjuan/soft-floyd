"""Thin wrapper around `garminconnect.Garmin`.

Verified against the installed `garminconnect==0.3.15` (not assumed):
`Garmin(email, password, prompt_mfa=...)`, `login(tokenstore: str | None)`,
`get_activities(start, limit, activitytype)`, and
`download_activity(activity_id, dl_fmt=ActivityDownloadFormat.ORIGINAL)`
(confirmed to return **zip bytes** for ORIGINAL — v0's unzip helper is
still needed).

Token storage: the library manages its own cache at the directory passed
to `login()` (writes `garmin_tokens.json` there, refreshes it in place).
We deliberately do NOT wrap this in Fernet/Keychain encryption as v0 did
— see docs/SECURITY.md for why: the library only re-persists a refreshed
token if it can find the cache at a real path, so an encrypted wrapper
would silently break auto-refresh and force a full SSO login (against a
Cloudflare-protected endpoint) on every process restart. Point it at an
app-controlled directory (`settings.garmin_token_dir`) and rely on the
library's own 0600/0700 permissions instead.

`client_factory` is the whole test seam: tests pass a hand-written fake
so no test ever constructs a real `Garmin` (which would try `curl_cffi`
network I/O) or imports `garminconnect` at all.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile, is_zipfile

from garminconnect import Garmin

from soft_floyd_core.garmin.errors import GarminApiError, ReauthRequired, map_garmin_exception


def _fit_payload(payload: bytes) -> bytes:
    """Garmin's ORIGINAL download format is a zip; unwrap the .fit inside it."""
    if not is_zipfile(BytesIO(payload)):
        return payload

    with ZipFile(BytesIO(payload)) as archive:
        fit_names = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".fit") and not name.endswith("/")
        ]
        if not fit_names:
            raise GarminApiError("Garmin activity download did not contain a FIT file.")
        return archive.read(fit_names[0])


class GarminClient:
    def __init__(
        self,
        token_dir: Path,
        *,
        client_factory: Callable[..., Any] = Garmin,
    ) -> None:
        self._token_dir = token_dir
        self._client_factory = client_factory
        self._client: Any | None = None

    def has_token(self) -> bool:
        return (self._token_dir / "garmin_tokens.json").exists()

    def login(self, email: str, password: str, mfa_callback: Callable[[], str]) -> None:
        self._token_dir.mkdir(parents=True, exist_ok=True)
        client = self._client_factory(email=email, password=password, prompt_mfa=mfa_callback)
        try:
            client.login(str(self._token_dir))
        except Exception as exc:
            map_garmin_exception(
                exc,
                action="Garmin login failed",
                reauth_message="Garmin rejected the login. Check email/password/MFA code.",
            )
        # garminconnect suppresses failures from its own token dump
        # (`with contextlib.suppress(Exception): self.client.dump(...)`),
        # so `login()` above can return cleanly while writing nothing.
        # Without this check the CLI would report success on an empty
        # token dir, and the next sync would demand another interactive
        # login — repeating that loop is what triggers Garmin's login
        # rate limit. See docs/exec-plans/completed/0003-garmin-auth-repair.md.
        if not self.has_token():
            raise GarminApiError(
                f"Garmin accepted the login but no token was written to "
                f"{self._token_dir} — check directory permissions."
            )
        self._client = client

    def logout(self) -> None:
        """Remove the cached token so the next sync raises ReauthRequired."""
        token_path = self._token_dir / "garmin_tokens.json"
        token_path.unlink(missing_ok=True)
        self._client = None

    def load(self) -> None:
        """Resume from the cached token. Raises ReauthRequired if none exists.

        Constructing/loading the client makes a network call (garminconnect
        defaults to verify_login=True) — never call this from an event loop
        or app lifespan; only from a background worker thread.
        """
        if not self.has_token():
            raise ReauthRequired("No saved Garmin token found. Run `soft-floyd garmin-login`.")

        client = self._client_factory()
        try:
            client.login(str(self._token_dir))
        except Exception as exc:
            map_garmin_exception(exc, action="Garmin token load failed")
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            self.load()
        return self._client

    def list_recent_activities(self, limit: int = 20, start: int = 0) -> list[dict]:
        client = self._ensure_client()
        try:
            data = client.get_activities(start=start, limit=limit, activitytype="cycling")
        except Exception as exc:
            map_garmin_exception(exc, action="Garmin activity list failed")
        return data if isinstance(data, list) else []

    def download_fit(self, activity_id: int, dest_path: Path) -> Path:
        client = self._ensure_client()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = client.download_activity(
                str(activity_id),
                dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL,
            )
        except Exception as exc:
            map_garmin_exception(exc, action=f"Garmin FIT download {activity_id}")

        dest_path.write_bytes(_fit_payload(bytes(payload)))
        return dest_path

    def upload_and_schedule_workout(
        self,
        payload: dict[str, Any],
        planned_date: dt.date,
        existing_workout_id: str | None = None,
    ) -> str:
        """Create (or update) a Garmin Connect workout from a
        training.export.to_garmin_payload() dict, and schedule it on
        planned_date so it syncs to the Edge / paired trainer on its own.
        Passing existing_workout_id updates that workout in place instead
        of creating a duplicate — training/service.py's re-send path.
        """
        client = self._ensure_client()
        try:
            if existing_workout_id is not None:
                client.update_workout(existing_workout_id, payload)
                workout_id = str(existing_workout_id)
            else:
                result = client.upload_workout(payload)
                raw_id = result.get("workoutId") if isinstance(result, dict) else None
                if raw_id is None:
                    raise GarminApiError("Garmin accepted the workout but returned no workoutId.")
                workout_id = str(raw_id)
            client.schedule_workout(workout_id, planned_date.isoformat())
        except GarminApiError:
            raise
        except Exception as exc:
            map_garmin_exception(exc, action="Garmin workout upload")
        return workout_id
