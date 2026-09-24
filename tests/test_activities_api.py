"""REST routes for activities and Garmin sync status."""

from __future__ import annotations

from soft_floyd_core.activities.pipeline import ingest_activity
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import session_scope


class _FakeFitSource:
    def __init__(self, fit_bytes: bytes):
        self._fit_bytes = fit_bytes

    def download_fit(self, activity_id, dest_path):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(self._fit_bytes)
        return dest_path


def _seed_activity(activity_id: int, fit_path, **summary_overrides) -> None:
    """Seeds through the same session factory the running app uses —
    ingest_activity, not a raw INSERT, so bike_type/sensor flags are
    real, derived output rather than hand-typed test fixtures.
    """
    from soft_floyd_server.runtime import get_session_factory

    settings = get_settings()
    summary = {
        "activityId": activity_id,
        "startTimeLocal": "2026-04-15T08:00:00",
        "isIndoor": False,
        **summary_overrides,
    }
    with session_scope(get_session_factory()) as session:
        ingest_activity(session, settings, _FakeFitSource(fit_path.read_bytes()), summary)


def test_activities_empty_when_nothing_ingested(client):
    response = client.get("/api/activities")
    assert response.status_code == 200
    assert response.json() == []


def test_list_activities_after_seeding(client, road_fit_path):
    _seed_activity(1, road_fit_path)
    response = client.get("/api/activities")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["bike_type"] == "road"
    assert "power" in body[0]["sensors_present"]


def test_list_activities_filters_by_bike_type(client, road_fit_path, mtb_fit_path):
    _seed_activity(1, road_fit_path)
    _seed_activity(2, mtb_fit_path)

    road_only = client.get("/api/activities", params={"bike_type": "road"}).json()
    assert [a["id"] for a in road_only] == [1]

    mtb_only = client.get("/api/activities", params={"bike_type": "mtb"}).json()
    assert [a["id"] for a in mtb_only] == [2]


def test_activity_history_cursor_uses_time_then_id(client, road_fit_path):
    _seed_activity(1, road_fit_path, startTimeLocal="2026-04-14T08:00:00")
    _seed_activity(2, road_fit_path)
    _seed_activity(3, road_fit_path)
    _seed_activity(4, road_fit_path, startTimeLocal="2026-04-16T08:00:00")

    first = client.get("/api/activities", params={"limit": 2}).json()
    assert [ride["id"] for ride in first] == [4, 3]

    second = client.get(
        "/api/activities",
        params={"limit": 2, "before_start_time": first[-1]["start_time"], "before_id": 3},
    ).json()
    assert [ride["id"] for ride in second] == [2, 1]
    assert (
        client.get(
            "/api/activities",
            params={"limit": 2, "before_start_time": second[-1]["start_time"], "before_id": 1},
        ).json()
        == []
    )
    assert client.get("/api/activities", params={"before_id": 3}).status_code == 422


def test_get_activity_404s_on_unknown_id(client):
    response = client.get("/api/activities/999")
    assert response.status_code == 404


def test_get_activity_detail_has_available_metrics(client, mtb_fit_path):
    _seed_activity(1, mtb_fit_path)
    detail = client.get("/api/activities/1").json()
    assert detail["record_count"] > 0
    assert "hr_zones" in detail["available_metrics"]
    assert "ftp" not in detail["available_metrics"]  # mtb fixture has no power


def test_sync_status_before_any_sync(client):
    status = client.get("/api/sync/garmin/status").json()
    assert status["authenticated"] is False
    assert status["last_status"] == "never"


def test_sync_garmin_returns_reauth_required_without_a_token(client):
    response = client.post("/api/sync/garmin")
    assert response.status_code == 200  # succeeded at reporting, not at syncing
    body = response.json()
    assert body["status"] == "reauth_required"
