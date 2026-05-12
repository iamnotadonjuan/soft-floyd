from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import keyring
from cryptography.fernet import Fernet

from coach.config import Config
from coach.log import log


class ReauthRequired(Exception):
    pass


class GarminClient:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._client: object | None = None

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
        import garth

        client = garth.Client()
        try:
            client.login(email, password, prompt=mfa_callback)
        except Exception as exc:
            raise ReauthRequired(f"Garmin login failed: {exc}") from exc

        token_json = client.dumps()
        encrypted = self._fernet().encrypt(token_json.encode())
        self._cfg.garth_token_path.parent.mkdir(parents=True, exist_ok=True)
        self._cfg.garth_token_path.write_bytes(encrypted)
        self._client = client
        log.info("garmin_client.logged_in", email=email)

    def load_from_disk(self) -> None:
        if not self._cfg.garth_token_path.exists():
            raise ReauthRequired("No saved Garmin token found. Run `coach login` first.")

        encrypted = self._cfg.garth_token_path.read_bytes()
        token_json = self._fernet().decrypt(encrypted).decode()

        import garth

        client = garth.Client()
        try:
            client.loads(token_json)
        except Exception as exc:
            raise ReauthRequired(f"Token load failed: {exc}") from exc

        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            self.load_from_disk()
        return self._client

    def _garth_get(self, path: str, **kwargs) -> dict:
        import garth

        client = self._ensure_client()
        try:
            return client.connectapi(path, **kwargs)
        except garth.exc.GarthHTTPError as exc:
            if exc.error.status_code == 401:
                raise ReauthRequired("Garmin session expired. Run `coach login`.") from exc
            raise

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

        data = self._garth_get("/activitylist-service/activities/search/activities", params=params)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # FIT download
    # ------------------------------------------------------------------

    def download_fit(self, activity_id: int, dest_path: Path) -> Path:
        import garth

        client = self._ensure_client()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = client.download(f"/download-service/files/activity/{activity_id}")
        except garth.exc.GarthHTTPError as exc:
            if exc.error.status_code == 401:
                raise ReauthRequired("Garmin session expired.") from exc
            raise

        dest_path.write_bytes(resp)
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
            hrv_data = self._garth_get(f"/hrv-service/hrv/{date_str}")
            result["hrv_overnight"] = hrv_data.get("lastNight")
        except Exception:
            result["hrv_overnight"] = None

        # Sleep
        try:
            sleep_data = self._garth_get(f"/wellness-service/wellness/dailySleepData/{date_str}")
            result["sleep_score"] = (
                (sleep_data.get("dailySleepDTO") or {}).get("sleepScores", {}).get("overall")
            )
        except Exception:
            result["sleep_score"] = None

        # Body Battery
        try:
            bb_data = self._garth_get(
                f"/wellness-service/wellness/bodyBattery/reports/daily/{date_str}/{date_str}"
            )
            if isinstance(bb_data, list) and bb_data:
                day = bb_data[0]
                result["body_battery_low"] = day.get("bodyBatteryValuesDescriptor", {}).get(
                    "bodyBatteryDailyLow"
                )
                result["body_battery_high"] = day.get("bodyBatteryValuesDescriptor", {}).get(
                    "bodyBatteryDailyHigh"
                )
        except Exception:
            result["body_battery_low"] = None
            result["body_battery_high"] = None

        # RHR
        try:
            rhr_data = self._garth_get(
                f"/userstats-service/wellness/daily/{date_str}",
                params={"fromDate": date_str, "untilDate": date_str, "metricId": 60},
            )
            vals = (
                rhr_data.get("allMetrics", {})
                .get("metricsMap", {})
                .get("WELLNESS_RESTING_HEART_RATE", [])
            )
            result["resting_hr"] = vals[0].get("value") if vals else None
        except Exception:
            result["resting_hr"] = None

        return result
