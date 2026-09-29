"""REST adapter tests for training sessions (exec-plan 0010) — thin
wiring only; the real behavior is covered by tests/test_training.py.
Same fixtures and monkeypatch seam as tests/test_coach.py.
"""

from __future__ import annotations

from soft_floyd_core.llm.client import CHAT_MODEL, EMBEDDING_MODEL, Usage
from soft_floyd_core.models import Bike, RiderProfile
from soft_floyd_core.training import service as training_service


class FakeStructuredLLM:
    def __init__(self, response: dict):
        self.response = response

    async def chat_structured(
        self, messages, schema_name, schema, *, max_completion_tokens, temperature=0
    ):
        return self.response, Usage(CHAT_MODEL, 800, 0, 300)

    async def embed(self, text):
        return [1.0, 0.0], Usage(EMBEDDING_MODEL, 10, 0, 0)


def _response() -> dict:
    return {
        "workout": {
            "name": "Easy spin",
            "est_minutes": 45,
            "steps": [
                {
                    "kind": "warmup",
                    "name": "Warm up",
                    "cue": "Easy",
                    "end": {"kind": "time", "seconds": 600, "meters": None},
                    "target": {"kind": "none", "low": None, "high": None, "hr_zone": None},
                },
                {
                    "kind": "cooldown",
                    "name": "Cool down",
                    "cue": "Easy",
                    "end": {"kind": "time", "seconds": 600, "meters": None},
                    "target": {"kind": "none", "low": None, "high": None, "hr_zone": None},
                },
            ],
        },
        "rationale": "A steady spin to keep the legs moving.",
        "adjustments": None,
    }


def _shared_factory(monkeypatch):
    from soft_floyd_server.runtime import get_session_factory

    factory = get_session_factory()
    engine = factory.kw["bind"]
    with factory() as db:
        db.add(RiderProfile(id=1, goal_text="Ride more", has_hr_monitor=True))
        db.add(Bike(nickname="Road", kind="road", is_primary=True))
        db.commit()
    return engine, factory


def test_rest_requires_an_api_key(client, monkeypatch):
    engine, _ = _shared_factory(monkeypatch)
    monkeypatch.setenv("SOFT_FLOYD_OPENAI_API_KEY", "")
    try:
        response = client.post(
            "/api/training/sessions",
            json={
                "planned_date": "2026-09-25",
                "available_minutes": 60,
                "setting": "outdoor",
                "discipline": "road",
            },
        )
        assert response.status_code == 400
        assert "OPENAI_API_KEY" in response.json()["detail"]
    finally:
        engine.dispose()


def test_plan_list_get_and_delete_a_session(client, monkeypatch):
    engine, _ = _shared_factory(monkeypatch)
    monkeypatch.setattr(
        training_service, "make_training_llm", lambda _key: FakeStructuredLLM(_response())
    )
    try:
        created = client.post(
            "/api/training/sessions",
            json={
                "planned_date": "2026-09-25",
                "available_minutes": 60,
                "setting": "outdoor",
                "discipline": "road",
                "route_idea": "easy spin",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["workout"]["name"] == "Easy spin"
        assert body["status"] == "planned"
        assert body["available_export_formats"] == ["fit"]

        listing = client.get("/api/training/sessions").json()
        assert [s["id"] for s in listing] == [body["id"]]

        fetched = client.get(f"/api/training/sessions/{body['id']}").json()
        assert fetched["id"] == body["id"]

        patched = client.patch(f"/api/training/sessions/{body['id']}", json={"status": "done"})
        assert patched.json()["status"] == "done"

        exported = client.get(f"/api/training/sessions/{body['id']}/export?format=fit")
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/octet-stream"

        rejected = client.get(f"/api/training/sessions/{body['id']}/export?format=zwo")
        assert rejected.status_code == 400

        assert client.delete(f"/api/training/sessions/{body['id']}").status_code == 204
        assert client.get(f"/api/training/sessions/{body['id']}").status_code == 404
    finally:
        engine.dispose()


def test_rest_reports_budget_exhaustion(client, monkeypatch):
    from soft_floyd_core.models import LLMUsageRecord

    engine, factory = _shared_factory(monkeypatch)
    monkeypatch.setattr(
        training_service, "make_training_llm", lambda _key: FakeStructuredLLM(_response())
    )
    monkeypatch.setenv("SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD", "0.5")
    with factory() as db:
        db.add(
            LLMUsageRecord(
                model=CHAT_MODEL, prompt_tokens=1, cached_tokens=0, completion_tokens=1, cost_usd=1
            )
        )
        db.commit()
    try:
        response = client.post(
            "/api/training/sessions",
            json={
                "planned_date": "2026-09-25",
                "available_minutes": 60,
                "setting": "outdoor",
                "discipline": "road",
            },
        )
        assert response.status_code == 402
    finally:
        engine.dispose()


def test_patch_edits_a_planned_session(client, monkeypatch):
    engine, _ = _shared_factory(monkeypatch)
    llm = FakeStructuredLLM(_response())
    monkeypatch.setattr(training_service, "make_training_llm", lambda _key: llm)
    try:
        created = client.post(
            "/api/training/sessions",
            json={
                "planned_date": "2026-09-25",
                "available_minutes": 60,
                "setting": "outdoor",
                "discipline": "road",
            },
        ).json()
        url = f"/api/training/sessions/{created['id']}"

        moved = client.patch(url, json={"planned_date": "2026-09-27"})
        assert moved.status_code == 200, moved.text
        assert moved.json()["planned_date"] == "2026-09-27"
        assert moved.json()["workout"] == created["workout"]

        rebuilt = client.patch(url, json={"available_minutes": 30, "setting": "indoor"})
        assert rebuilt.status_code == 200, rebuilt.text
        request = rebuilt.json()["request"]
        assert (request["available_minutes"], request["setting"]) == (30, "indoor")
        assert request["planned_date"] == "2026-09-27"  # earlier edit kept

        # Status-only PATCH still works the way it always did.
        assert client.patch(url, json={"status": "skipped"}).json()["status"] == "skipped"
    finally:
        engine.dispose()


def test_patch_rejects_bad_edits(client, monkeypatch):
    engine, _ = _shared_factory(monkeypatch)
    monkeypatch.setattr(
        training_service, "make_training_llm", lambda _key: FakeStructuredLLM(_response())
    )
    try:
        created = client.post(
            "/api/training/sessions",
            json={
                "planned_date": "2026-09-25",
                "available_minutes": 60,
                "setting": "outdoor",
                "discipline": "road",
            },
        ).json()
        url = f"/api/training/sessions/{created['id']}"

        both = client.patch(url, json={"status": "done", "available_minutes": 30})
        assert both.status_code == 400
        assert client.patch(url, json={}).status_code == 400
        assert client.patch(url, json={"available_minutes": 0}).status_code == 422
        assert client.patch("/api/training/sessions/999", json={"feel": "tired"}).status_code == 404

        client.patch(url, json={"status": "done"})
        assert client.patch(url, json={"available_minutes": 30}).status_code == 409
    finally:
        engine.dispose()


def test_patch_rebuild_needs_a_key_but_a_move_does_not(client, monkeypatch):
    engine, _ = _shared_factory(monkeypatch)
    monkeypatch.setattr(
        training_service, "make_training_llm", lambda _key: FakeStructuredLLM(_response())
    )
    try:
        created = client.post(
            "/api/training/sessions",
            json={
                "planned_date": "2026-09-25",
                "available_minutes": 60,
                "setting": "outdoor",
                "discipline": "road",
            },
        ).json()
        url = f"/api/training/sessions/{created['id']}"
        monkeypatch.setattr(training_service, "make_training_llm", lambda _key: None)  # no key

        assert client.patch(url, json={"planned_date": "2026-09-28"}).status_code == 200
        rebuild = client.patch(url, json={"available_minutes": 30})
        assert rebuild.status_code == 400
        assert "OPENAI_API_KEY" in rebuild.json()["detail"]
    finally:
        engine.dispose()


def test_send_to_garmin_shows_the_rider_a_plain_message_and_logs_the_real_one(client, monkeypatch):
    from soft_floyd_core.garmin.errors import USER_UNAVAILABLE, GarminUnavailable
    from soft_floyd_server import http_api
    from structlog.testing import capture_logs

    engine, _ = _shared_factory(monkeypatch)
    monkeypatch.setattr(
        training_service, "make_training_llm", lambda _key: FakeStructuredLLM(_response())
    )

    class Down:
        async def send_workout(self, payload, planned_date, existing_workout_id=None):
            raise GarminUnavailable(
                "Garmin workout upload: Garmin API returned HTTP 521: API Error 521",
                user_message=USER_UNAVAILABLE,
                status=521,
            )

    monkeypatch.setattr(http_api, "current_sync_runner", lambda: Down())
    try:
        created = client.post(
            "/api/training/sessions",
            json={
                "planned_date": "2026-09-25",
                "available_minutes": 60,
                "setting": "outdoor",
                "discipline": "road",
            },
        ).json()
        with capture_logs() as logs:
            response = client.post(f"/api/training/sessions/{created['id']}/garmin")

        assert response.status_code == 502
        assert response.json()["detail"] == USER_UNAVAILABLE
        assert "521" not in response.text
        event = next(e for e in logs if e["event"] == "send_to_garmin_failed")
        assert event["status"] == 521
        assert event["training_session_id"] == created["id"]
        assert "HTTP 521" in event["error"]
    finally:
        engine.dispose()
