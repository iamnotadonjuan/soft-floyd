from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from typing import NoReturn
from zipfile import ZipFile, is_zipfile

import keyring
from cryptography.fernet import Fernet
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from coach.config import Config
from coach.log import log


class GarminApiError(Exception):
    pass


class ReauthRequired(GarminApiError):
    pass


class GarminRateLimited(GarminApiError):
    def __init__(self, message: str, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


_STATUS_RE = re.compile(r"\b(4\d\d|5\d\d)\b")


def _exception_response(exc: object) -> object | None:
    response = getattr(exc, "response", None)
    if response is not None:
        return response

    error = getattr(exc, "error", None)
    return getattr(error, "response", None)


def _exception_status_code(exc: object) -> int | None:
    response = _exception_response(exc)
    status = getattr(response, "status_code", None)
    if status is not None:
        return int(status)

    error = getattr(exc, "error", None)
    status = getattr(error, "status_code", None)
    if status is not None:
        return int(status)

    match = _STATUS_RE.search(str(exc))
    return int(match.group(1)) if match else None


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


def _raise_garmin_error(
    exc: object,
    *,
    action: str,
    reauth_message: str = "Garmin session expired. Run `coach login --force`.",
) -> NoReturn:
    status = _exception_status_code(exc)
    if status == 401 or isinstance(exc, GarminConnectAuthenticationError):
        raise ReauthRequired(f"{action}: {reauth_message}") from exc
    if status == 429 or isinstance(exc, GarminConnectTooManyRequestsError):
        retry_after_s = _exception_retry_after_s(exc)
        raise GarminRateLimited(
            f"{action}: Garmin is rate limiting requests. Stop retrying for now and try again later.",
            retry_after_s=retry_after_s,
        ) from exc
    if status is not None:
        raise GarminApiError(f"{action}: Garmin API returned HTTP {status}: {exc}") from exc
    raise GarminApiError(f"{action}: Garmin API request failed: {exc}") from exc


def _fit_payload(payload: bytes) -> bytes:
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
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._client: Garmin | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_or_create_fernet_key(self) -> bytes:
        key = keyring.get_password(self._cfg.keychain_service, self._cfg.keychain_account)
        if key is None:
            key = Fernet.generate_key().decode()
            keyring.set_password(self._cfg.keychain_service, self._cfg.keychain_account, key)
            log.info("garmin_client.fernet_key_created")
        return key.encode() if isinstance(key, str) else key

    def _fernet(self) -> Fernet:
        return Fernet(self._get_or_create_fernet_key())

    def login(self, email: str, password: str, mfa_callback: Callable[[], str]) -> None:
        client = Garmin(email=email, password=password, prompt_mfa=mfa_callback)
        try:
            client.login()
        except Exception as exc:
            _raise_garmin_error(
                exc,
                action="Garmin login failed",
                reauth_message="Garmin rejected the login. Check your email, password, and MFA code.",
            )

        token_json = client.client.dumps()
        encrypted = self._fernet().encrypt(token_json.encode())
        self._cfg.garth_token_path.parent.mkdir(parents=True, exist_ok=True)
        self._cfg.garth_token_path.write_bytes(encrypted)
        self._client = client
        log.info("garmin_client.logged_in")

    def load_from_disk(self) -> None:
        if not self._cfg.garth_token_path.exists():
            raise ReauthRequired("No saved Garmin token found. Run `coach login` first.")

        encrypted = self._cfg.garth_token_path.read_bytes()
        token_json = self._fernet().decrypt(encrypted).decode()

        client = Garmin()
        try:
            client.login(token_json)
        except GarminConnectTooManyRequestsError as exc:
            _raise_garmin_error(exc, action="Garmin token load failed")
        except GarminConnectAuthenticationError as exc:
            _raise_garmin_error(exc, action="Garmin token load failed")
        except Exception as exc:
            if "token" in str(exc).lower():
                raise ReauthRequired(
                    "Saved Garmin token could not be loaded. Run `coach login --force`."
                ) from exc
            _raise_garmin_error(exc, action="Garmin token load failed")

        self._client = client

    def _ensure_client(self) -> Garmin:
        if self._client is None:
            self.load_from_disk()
        return self._client

    def _garmin_get(self, path: str, **kwargs) -> dict | list:
        client = self._ensure_client()
        try:
            return client.connectapi(path, **kwargs)
        except Exception as exc:
            _raise_garmin_error(exc, action=f"Garmin API GET {path}")

    def _call_garmin(self, action: str, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            _raise_garmin_error(exc, action=action)

    # ------------------------------------------------------------------
    # Activity listing
    # ------------------------------------------------------------------

    def list_activities(
        self,
        start_dt: datetime | None = None,
        limit: int = 20,
        start: int = 0,
    ) -> list[dict]:
        params: dict = {"limit": limit, "start": start, "activityType": "cycling"}
        if start_dt is not None:
            params["startDate"] = start_dt.strftime("%Y-%m-%d")

        data = self._garmin_get("/activitylist-service/activities/search/activities", params=params)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # FIT download
    # ------------------------------------------------------------------

    def download_fit(self, activity_id: int, dest_path: Path) -> Path:
        client = self._ensure_client()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = client.download_activity(
                str(activity_id),
                dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL,
            )
        except Exception as exc:
            _raise_garmin_error(exc, action=f"Garmin FIT download {activity_id}")

        dest_path.write_bytes(_fit_payload(bytes(resp)))
        log.info("garmin_client.fit_downloaded", activity_id=activity_id, path=str(dest_path))
        return dest_path

    # ------------------------------------------------------------------
    # Wellness
    # ------------------------------------------------------------------

    def get_wellness(self, date: datetime) -> dict:
        date_str = date.strftime("%Y-%m-%d")
        result: dict = {"date": date_str}

        # HRV
        try:
            hrv_data = (
                self._call_garmin(
                    "Garmin HRV fetch",
                    self._ensure_client().get_hrv_data,
                    date_str,
                )
                or {}
            )
            result["hrv_overnight"] = hrv_data.get("lastNight")
        except (ReauthRequired, GarminRateLimited):
            raise
        except Exception:
            result["hrv_overnight"] = None

        # Sleep
        try:
            sleep_data = self._call_garmin(
                "Garmin sleep fetch",
                self._ensure_client().get_sleep_data,
                date_str,
            )
            result["sleep_score"] = (
                (sleep_data.get("dailySleepDTO") or {}).get("sleepScores", {}).get("overall")
            )
        except (ReauthRequired, GarminRateLimited):
            raise
        except Exception:
            result["sleep_score"] = None

        # Body Battery
        try:
            bb_data = self._call_garmin(
                "Garmin body battery fetch",
                self._ensure_client().get_body_battery,
                date_str,
            )
            if isinstance(bb_data, list) and bb_data:
                day = bb_data[0]
                result["body_battery_low"] = day.get("bodyBatteryValuesDescriptor", {}).get(
                    "bodyBatteryDailyLow"
                )
                result["body_battery_high"] = day.get("bodyBatteryValuesDescriptor", {}).get(
                    "bodyBatteryDailyHigh"
                )
        except (ReauthRequired, GarminRateLimited):
            raise
        except Exception:
            result["body_battery_low"] = None
            result["body_battery_high"] = None

        # RHR
        try:
            rhr_data = self._call_garmin(
                "Garmin resting HR fetch",
                self._ensure_client().get_rhr_day,
                date_str,
            )
            vals = (
                rhr_data.get("allMetrics", {})
                .get("metricsMap", {})
                .get("WELLNESS_RESTING_HEART_RATE", [])
            )
            result["resting_hr"] = vals[0].get("value") if vals else None
        except (ReauthRequired, GarminRateLimited):
            raise
        except Exception:
            result["resting_hr"] = None

        return result
