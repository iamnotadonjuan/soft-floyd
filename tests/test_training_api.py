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
