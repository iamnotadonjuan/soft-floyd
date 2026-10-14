"""AI ride summary (exec-plan 0023): sensor gating, persistence, budget and
account isolation, through the REST adapter with a fake LLM."""

from __future__ import annotations

from soft_floyd_core.analysis import service as analysis_service
from soft_floyd_core.analysis.metrics import RideRecords, compute_ride_metrics
from soft_floyd_core.llm.client import CHAT_MODEL, IncompleteResponseError, Usage
from soft_floyd_core.models import Activity, Bike, LLMUsageRecord, RiderProfile

from tests.test_activities_api import _seed_activity


class FakeAnalysisLLM:
    def __init__(self, draft: dict | None = None, *, incomplete: bool = False):
        self.draft = draft or _draft()
        self.incomplete = incomplete
        self.calls: list[list[dict]] = []

    async def chat_structured(
        self, messages, schema_name, schema, *, max_completion_tokens, reasoning_effort="medium"
    ):
        self.calls.append(messages)
        usage = Usage(CHAT_MODEL, 900, 0, 300)
        if self.incomplete:
            raise IncompleteResponseError(usage)
        return self.draft, usage


def _draft(**overrides) -> dict:
    return {
        "headline": "A steady endurance ride.",
        "went_well": ["Even effort across the ride."],
        "to_improve": ["Start a little easier."],
        "next_time": "Keep the first 20 minutes in zone 2.",
        "data_caveat": None,
        **overrides,
    }


def _shared_factory(*, power_meter: bool):
    from soft_floyd_server.runtime import get_session_factory

    factory = get_session_factory()
    with factory() as db:
        db.add(RiderProfile(id=1, goal_text="Ride more", has_hr_monitor=True, ftp_watts=200))
        db.add(Bike(nickname="Road", kind="road", is_primary=True, has_power_meter=power_meter))
        db.commit()
    return factory


def _install(monkeypatch, llm):
    monkeypatch.setattr(analysis_service, "make_analysis_llm", lambda _key: llm)
    monkeypatch.setenv("SOFT_FLOYD_OPENAI_API_KEY", "test-key")


def test_get_before_generating_has_metrics_but_no_analysis(client, mtb_fit_path):
    _shared_factory(power_meter=False)
    _seed_activity(1, mtb_fit_path, duration=3600, distance=30000, averageHR=150)
    body = client.get("/api/activities/1/analysis").json()
    assert body["analysis"] is None
    assert body["metrics"]["avg_hr"] == 150
    assert "power" not in body["metrics"]["sensors_present"]


def test_unknown_ride_is_404(client):
    assert client.get("/api/activities/999/analysis").status_code == 404
    assert client.post("/api/activities/999/analysis", json={}).status_code == 404


def test_requires_an_api_key(client, mtb_fit_path, monkeypatch):
    _shared_factory(power_meter=False)
    _seed_activity(1, mtb_fit_path)
    monkeypatch.setattr(analysis_service, "make_analysis_llm", lambda _key: None)
    response = client.post("/api/activities/1/analysis", json={})
    assert response.status_code == 400
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_ride_without_power_has_no_power_fields_or_prompt_watts(client, mtb_fit_path, monkeypatch):
    _shared_factory(power_meter=True)  # profile says power, but this ride has none
    _seed_activity(1, mtb_fit_path)
    llm = FakeAnalysisLLM()
    _install(monkeypatch, llm)

    response = client.post("/api/activities/1/analysis", json={"language": "es"})
    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    for field in ("avg_power_w", "normalized_power_w", "intensity_factor", "tss"):
        assert metrics[field] is None

    system, user = llm.calls[0]
    assert "Reply in Spanish" in user["content"]
    assert " W" not in user["content"].replace("Ride load", "")
    assert "No power data on this ride." in user["content"]


def test_power_ride_exposes_power_metrics(client, road_fit_path, monkeypatch):
    _shared_factory(power_meter=True)
    _seed_activity(1, road_fit_path, duration=9000, distance=62400, averageHR=150)
    llm = FakeAnalysisLLM()
    _install(monkeypatch, llm)
    metrics = client.post("/api/activities/1/analysis", json={}).json()["metrics"]
    assert "power" in metrics["sensors_present"]
    assert metrics["avg_power_w"] is not None
    assert "Average power" in llm.calls[0][1]["content"]


def test_watts_in_the_output_are_rejected_when_the_ride_has_no_power(
    client, mtb_fit_path, monkeypatch
):
    _shared_factory(power_meter=False)
    _seed_activity(1, mtb_fit_path)
    _install(monkeypatch, FakeAnalysisLLM(_draft(headline="You held 250 W all day.")))
    assert client.post("/api/activities/1/analysis", json={}).status_code == 502
    assert client.get("/api/activities/1/analysis").json()["analysis"] is None


def test_analysis_is_stored_and_reused_until_regenerated(client, mtb_fit_path, monkeypatch):
    factory = _shared_factory(power_meter=False)
    _seed_activity(1, mtb_fit_path)
    llm = FakeAnalysisLLM()
    _install(monkeypatch, llm)

    first = client.post("/api/activities/1/analysis", json={}).json()
    assert first["analysis"]["headline"] == "A steady endurance ride."
    assert len(llm.calls) == 1

    again = client.post("/api/activities/1/analysis", json={}).json()
    assert again["analysis"] == first["analysis"]
    assert len(llm.calls) == 1  # served from the stored row

    assert client.get("/api/activities/1/analysis").json()["analysis"] == first["analysis"]

    llm.draft = _draft(headline="Regenerated.")
    regenerated = client.post("/api/activities/1/analysis", json={"regenerate": True}).json()
    assert regenerated["analysis"]["headline"] == "Regenerated."
    assert len(llm.calls) == 2

    with factory() as db:
        assert db.query(LLMUsageRecord).count() == 2  # one per real call, none for the reuse


def test_incomplete_response_still_records_usage(client, mtb_fit_path, monkeypatch):
    factory = _shared_factory(power_meter=False)
    _seed_activity(1, mtb_fit_path)
    _install(monkeypatch, FakeAnalysisLLM(incomplete=True))
    assert client.post("/api/activities/1/analysis", json={}).status_code == 502
    with factory() as db:
        assert db.query(LLMUsageRecord).count() == 1


def test_budget_exhaustion_is_402(client, mtb_fit_path, monkeypatch):
    _shared_factory(power_meter=False)
    _seed_activity(1, mtb_fit_path)
    llm = FakeAnalysisLLM()
    _install(monkeypatch, llm)
    monkeypatch.setenv("SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD", "0")
    response = client.post("/api/activities/1/analysis", json={})
    assert response.status_code == 402
    assert llm.calls == []


def test_another_account_cannot_read_or_analyze_the_ride(client, mtb_fit_path, monkeypatch):
    from soft_floyd_core.auth.service import create_session
    from soft_floyd_core.config import get_settings
    from soft_floyd_core.db import session_scope
    from soft_floyd_core.models import Account
    from soft_floyd_server.runtime import get_session_factory

    _shared_factory(power_meter=False)
    _seed_activity(1, mtb_fit_path)
    llm = FakeAnalysisLLM()
    _install(monkeypatch, llm)
    assert client.post("/api/activities/1/analysis", json={}).status_code == 200

    with session_scope(get_session_factory()) as session:
        account = Account(google_sub="second-user", email="s@example.com", name="Second Rider")
        session.add(account)
        session.flush()
        token = create_session(session, get_settings(), account)
    client.cookies.set("soft_floyd_session", token)

    assert client.get("/api/activities/1/analysis").status_code == 404
    assert client.post("/api/activities/1/analysis", json={}).status_code == 404
    assert len(llm.calls) == 1


def _transient_ride(**overrides) -> Activity:
    values = dict(
        fit_status="ok",
        duration_s=3600.0,
        distance_m=30000.0,
        elev_gain_m=300.0,
        avg_hr=150,
        max_hr=175,
        avg_power_w=200,
        max_power_w=400,
        has_power_data=True,
        has_hr_data=True,
        has_cadence_data=False,
        has_speed_data=True,
        has_gps_data=True,
        records_stored=True,
    )
    values.update(overrides)
    return Activity(**values)


def _synthetic_records() -> RideRecords:
    t = [float(i) for i in range(3600)]
    # Steady 200 W; HR climbs from 140 to 160 across the ride.
    return RideRecords(t, [200] * 3600, [140 + 20 * i // 3600 for i in range(3600)])


_FULL = ["normalized_power", "training_stress_score", "hr_zones", "hr_drift", "avg_speed"]


def test_metrics_compute_np_zones_and_drift_from_verified_streams():
    metrics = compute_ride_metrics(
        _transient_ride(), [], _synthetic_records(), allowed=_FULL, ftp_watts=200, lthr=160
    )
    assert metrics.normalized_power_w == 200
    assert metrics.intensity_factor == 1.0
    assert metrics.tss == 100.0
    assert metrics.variability_index == 1.0
    assert metrics.hr_zone_minutes is not None
    assert round(sum(metrics.hr_zone_minutes.values())) == 60
    assert metrics.hr_drift_pct is not None and metrics.hr_drift_pct > 0
    assert metrics.load_basis == "power_np"


def test_metrics_never_report_power_the_ride_did_not_verify():
    ride = _transient_ride(has_power_data=False, avg_power_w=None, max_power_w=None)
    metrics = compute_ride_metrics(
        ride, [], _synthetic_records(), allowed=_FULL, ftp_watts=200, lthr=160
    )
    assert metrics.normalized_power_w is None
    assert metrics.tss is None
    assert "power" not in metrics.sensors_present
    assert "No power data on this ride." in metrics.notes
    assert metrics.load_basis == "hr_zones"


def test_metrics_respect_the_capability_allowlist_and_failed_fit():
    hr_only = compute_ride_metrics(
        _transient_ride(), [], _synthetic_records(), allowed=["hr_zones"], ftp_watts=200, lthr=160
    )
    assert hr_only.normalized_power_w is None  # profile has no power metrics
    assert hr_only.hr_drift_pct is None  # hr_drift not allowed

    failed = compute_ride_metrics(
        _transient_ride(fit_status="download_failed"),
        [],
        None,
        allowed=["duration"],
        ftp_watts=200,
        lthr=160,
    )
    assert failed.sensors_present == []
    assert failed.avg_hr is None and failed.avg_power_w is None
    assert failed.load_basis == "duration"


def test_metrics_explain_missing_anchors():
    metrics = compute_ride_metrics(
        _transient_ride(), [], _synthetic_records(), allowed=_FULL, ftp_watts=None, lthr=None
    )
    assert metrics.intensity_factor is None and metrics.hr_zone_minutes is None
    assert any("FTP is not set" in n for n in metrics.notes)
    assert any("LTHR" in n for n in metrics.notes)
