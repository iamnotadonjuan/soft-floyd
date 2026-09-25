"""Training sessions (exec-plan 0010): the sensor-honesty gate
(sanitize.py), the deterministic intent (intent.py), device export
(export.py), and the generator/service orchestration with a fake LLM.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fit_tool.fit_file import FitFile
from fit_tool.validation import ConformanceLevel, validate_fit_file
from soft_floyd_core.activities.service import (
    ActivitySummaryOut,
    TrainingSummaryOut,
    WeekSummaryOut,
)
from soft_floyd_core.bikes.service import BikeOut
from soft_floyd_core.llm.client import CHAT_MODEL, EMBEDDING_MODEL, Usage
from soft_floyd_core.models import Base, Bike, RiderProfile
from soft_floyd_core.profile.service import ProfileOut
from soft_floyd_core.training import export as export_mod
from soft_floyd_core.training import service as training_service
from soft_floyd_core.training.intent import recommend_intent
from soft_floyd_core.training.sanitize import sanitize_workout
from soft_floyd_core.training.schemas import (
    DraftRepeatBlock,
    DraftStep,
    DraftTarget,
    DraftWorkout,
    SessionRequest,
    StepEnd,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

NOW = dt.datetime(2026, 9, 24, 8, 0)  # a Thursday
TODAY = NOW.date()


def _profile(**overrides) -> ProfileOut:
    defaults = dict(
        weekly_rides=3,
        weekly_hours=5.0,
        goal_text="Gran fondo",
        target_event_name=None,
        target_event_date=None,
        focus_areas=[],
        years_riding=5.0,
        longest_recent_ride_km=100.0,
        followed_plan_before=True,
        self_rated_level="recreational",
        available_days=["mon", "wed", "sat"],
        weekday_max_minutes=90,
        weekend_max_minutes=180,
        birth_year=1990,
        weight_kg=70.0,
        max_hr=190,
        health_notes=None,
        has_hr_monitor=True,
        ftp_watts=None,
        lthr=None,
        workout_devices=["garmin"],
        has_power_meter=False,
        has_cadence_sensor=False,
        has_speed_sensor=False,
        primary_discipline="road",
        capability_tier="hr",
        available_metrics=[],
    )
    defaults.update(overrides)
    return ProfileOut(**defaults)


def _bike(**overrides) -> BikeOut:
    defaults = dict(
        id=1,
        nickname="Road",
        kind="road",
        is_primary=True,
        has_power_meter=False,
        has_cadence_sensor=False,
        has_speed_sensor=False,
        capability_tier="hr",
    )
    defaults.update(overrides)
    return BikeOut(**defaults)


def _request(**overrides) -> SessionRequest:
    defaults = dict(
        planned_date=TODAY + dt.timedelta(days=1),
        available_minutes=60,
        setting="outdoor",
        discipline="road",
        route_idea="hill repeats at Patios",
        feel="normal",
    )
    defaults.update(overrides)
    return SessionRequest(**defaults)


def _draft_workout(target: DraftTarget, *, kind="interval") -> DraftWorkout:
    return DraftWorkout(
        name="Test session",
        est_minutes=60,
        steps=[
            DraftStep(
                kind="warmup",
                name="Warm up",
                cue="Easy spin",
                end=StepEnd(kind="time", seconds=600),
                target=DraftTarget(kind="none"),
            ),
            DraftStep(
                kind=kind,
                name="Main",
                cue="Work",
                end=StepEnd(kind="time", seconds=600),
                target=target,
            ),
            DraftStep(
                kind="cooldown",
                name="Cool down",
                cue="Easy spin",
                end=StepEnd(kind="time", seconds=300),
                target=DraftTarget(kind="none"),
            ),
        ],
    )


# --- sanitize.py: the sensor-honesty gate ---


def test_power_target_dropped_without_power_meter():
    draft = _draft_workout(DraftTarget(kind="power_pct_ftp", low=90, high=100))
    workout = sanitize_workout(
        draft,
        profile=_profile(ftp_watts=250),
        bike=_bike(has_power_meter=False),
        discipline="road",
        available_minutes=60,
    )
    assert workout.steps[1].target is None
    assert workout.steps[1].cue  # the plain-language cue survives


def test_power_target_dropped_without_ftp_even_with_power_meter():
    draft = _draft_workout(DraftTarget(kind="power_pct_ftp", low=90, high=100))
    workout = sanitize_workout(
        draft,
        profile=_profile(ftp_watts=None),
        bike=_bike(has_power_meter=True),
        discipline="road",
        available_minutes=60,
    )
    assert workout.steps[1].target is None


def test_power_target_resolved_to_watts():
    draft = _draft_workout(DraftTarget(kind="power_pct_ftp", low=90, high=100))
    workout = sanitize_workout(
        draft,
        profile=_profile(ftp_watts=250),
        bike=_bike(has_power_meter=True),
        discipline="road",
        available_minutes=60,
    )
    target = workout.steps[1].target
    assert target is not None and target.kind == "power"
    assert (target.low, target.high) == (225, 250)


def test_hr_zone_requires_lthr_not_just_a_strap():
    draft = _draft_workout(DraftTarget(kind="hr_zone", hr_zone=2))
    workout = sanitize_workout(
        draft,
        profile=_profile(has_hr_monitor=True, lthr=None),
        bike=_bike(),
        discipline="road",
        available_minutes=60,
    )
    assert workout.steps[1].target is None


def test_hr_zone_resolved_from_lthr_table():
    draft = _draft_workout(DraftTarget(kind="hr_zone", hr_zone=3))
    workout = sanitize_workout(
        draft,
        profile=_profile(has_hr_monitor=True, lthr=160),
        bike=_bike(),
        discipline="road",
        available_minutes=60,
    )
    target = workout.steps[1].target
    assert target is not None and target.kind == "hr"
    assert (target.low, target.high) == (round(160 * 0.90), round(160 * 0.94))


def test_cadence_target_needs_a_cadence_sensor():
    draft = _draft_workout(DraftTarget(kind="cadence_rpm", low=90, high=100))
    workout = sanitize_workout(
        draft,
        profile=_profile(),
        bike=_bike(has_cadence_sensor=False),
        discipline="road",
        available_minutes=60,
    )
    assert workout.steps[1].target is None
    workout = sanitize_workout(
        draft,
        profile=_profile(),
        bike=_bike(has_cadence_sensor=True),
        discipline="road",
        available_minutes=60,
    )
    assert workout.steps[1].target is not None and workout.steps[1].target.kind == "cadence"


def test_no_matching_bike_means_no_sensor_targets():
    draft = _draft_workout(DraftTarget(kind="power_pct_ftp", low=90, high=100))
    workout = sanitize_workout(
        draft,
        profile=_profile(ftp_watts=250),
        bike=None,
        discipline="road",
        available_minutes=60,
    )
    assert workout.steps[1].target is None


def test_duration_clamp_shrinks_intervals_not_warmup_or_cooldown():
    draft = DraftWorkout(
        name="Long",
        est_minutes=90,
        steps=[
            DraftStep(
                kind="warmup",
                name="Warm up",
                cue="Easy",
                end=StepEnd(kind="time", seconds=600),
                target=DraftTarget(kind="none"),
            ),
            DraftRepeatBlock(
                count=6,
                steps=[
                    DraftStep(
                        kind="interval",
                        name="Hard",
                        cue="Hard",
                        end=StepEnd(kind="time", seconds=300),
                        target=DraftTarget(kind="none"),
                    ),
                    DraftStep(
                        kind="recovery",
                        name="Easy",
                        cue="Easy",
                        end=StepEnd(kind="time", seconds=180),
                        target=DraftTarget(kind="none"),
                    ),
                ],
            ),
            DraftStep(
                kind="cooldown",
                name="Cool down",
                cue="Easy",
                end=StepEnd(kind="time", seconds=600),
                target=DraftTarget(kind="none"),
            ),
        ],
    )
    workout = sanitize_workout(
        draft, profile=_profile(), bike=_bike(), discipline="road", available_minutes=30
    )
    warmup = workout.steps[0]
    cooldown = workout.steps[2]
    assert warmup.end.seconds == 600  # untouched — never scaled
    assert cooldown.end.seconds == 600  # untouched — never scaled
    repeat = workout.steps[1]
    assert repeat.steps[0].end.seconds < 300  # scaled down
    assert repeat.steps[1].end.seconds < 180  # scaled down
    assert (
        workout.est_minutes < 68
    )  # meaningfully closer to the 30-minute ask than the 68-minute draft


def test_repeat_count_is_clamped():
    draft = DraftWorkout(
        name="Silly",
        est_minutes=10,
        steps=[
            DraftRepeatBlock(
                count=999,
                steps=[
                    DraftStep(
                        kind="interval",
                        name="X",
                        cue="X",
                        end=StepEnd(kind="time", seconds=10),
                        target=DraftTarget(kind="none"),
                    ),
                ],
            )
        ],
    )
    workout = sanitize_workout(
        draft, profile=_profile(), bike=_bike(), discipline="road", available_minutes=60
    )
    assert workout.steps[0].count <= 20


# --- intent.py: deterministic, never LLM-guessed ---


def _summary(hours_this_week: float = 0.0) -> TrainingSummaryOut:
    week = WeekSummaryOut(
        week_start=TODAY - dt.timedelta(days=TODAY.weekday()),
        rides=1,
        distance_km=30.0,
        duration_h=hours_this_week,
        elev_gain_m=200.0,
        avg_hr=None,
        hr_rides=0,
        avg_power_w=None,
        power_rides=0,
    )
    return TrainingSummaryOut(
        weeks=[week],
        total_rides=1,
        total_distance_km=30.0,
        total_duration_h=hours_this_week,
        data_note=None,
    )


def _ride(days_ago: int, duration_s: float) -> ActivitySummaryOut:
    return ActivitySummaryOut(
        id=1,
        start_time=NOW - dt.timedelta(days=days_ago),
        sport="cycling",
        sub_sport="",
        bike_type="road",
        is_indoor=False,
        distance_m=30000.0,
        duration_s=duration_s,
        elev_gain_m=100.0,
        avg_hr=None,
        max_hr=None,
        avg_power_w=None,
        avg_cadence=None,
        sensors_present=[],
        fit_status="ok",
    )


def test_tired_always_means_recovery():
    intent = recommend_intent(_request(feel="tired"), _profile(), _summary(), [], today=TODAY)
    assert intent.emphasis == "recovery"


def test_recent_long_ride_means_recovery():
    intent = recommend_intent(_request(), _profile(), _summary(), [_ride(0, 6000)], today=TODAY)
    assert intent.emphasis == "recovery"


def test_event_in_two_days_means_taper_recovery():
    profile = _profile(target_event_date=TODAY + dt.timedelta(days=2), target_event_name="Fondo")
    intent = recommend_intent(_request(), profile, _summary(), [], today=TODAY)
    assert intent.emphasis == "recovery"
    assert any("Fondo" in r for r in intent.reasons)


def test_event_in_ten_days_means_tempo_not_a_deep_dig():
    profile = _profile(target_event_date=TODAY + dt.timedelta(days=10))
    intent = recommend_intent(_request(), profile, _summary(), [], today=TODAY)
    assert intent.emphasis == "tempo"


def test_climbing_focus_outdoors_means_climbing_emphasis():
    profile = _profile(focus_areas=["climbing"])
    intent = recommend_intent(_request(setting="outdoor"), profile, _summary(), [], today=TODAY)
    assert intent.emphasis == "climbing"


def test_off_schedule_day_is_flagged():
    profile = _profile(available_days=["mon"])
    intent = recommend_intent(
        _request(planned_date=TODAY + dt.timedelta(days=1)), profile, _summary(), [], today=TODAY
    )
    assert intent.off_schedule is True


# --- export.py: device formats ---


def _power_workout():
    draft = _draft_workout(DraftTarget(kind="power_pct_ftp", low=90, high=100))
    return sanitize_workout(
        draft,
        profile=_profile(ftp_watts=250),
        bike=_bike(has_power_meter=True),
        discipline="road",
        available_minutes=60,
    )


def test_garmin_payload_shape():
    payload = export_mod.to_garmin_payload(_power_workout())
    assert payload["workoutName"] == "Test session"
    assert payload["sportType"]["sportTypeId"] == 2
    steps = payload["workoutSegments"][0]["workoutSteps"]
    assert steps[1]["targetType"]["workoutTargetTypeKey"] == "power.zone"
    assert steps[1]["targetValueOne"] == 225


def test_fit_export_round_trips_and_validates(tmp_path):
    fit_bytes = export_mod.to_fit_workout(_power_workout())
    path = tmp_path / "workout.fit"
    path.write_bytes(fit_bytes)
    fit_file = FitFile.from_file(str(path))
    report = validate_fit_file(fit_file, levels={ConformanceLevel.FILE_TYPE})
    assert not report.has_errors, [f.message for f in report.errors]


def test_fit_export_encodes_a_repeat_block_correctly(tmp_path):
    draft = DraftWorkout(
        name="Repeats",
        est_minutes=30,
        steps=[
            DraftStep(
                kind="warmup",
                name="Warm up",
                cue="Easy",
                end=StepEnd(kind="time", seconds=300),
                target=DraftTarget(kind="none"),
            ),
            DraftRepeatBlock(
                count=4,
                steps=[
                    DraftStep(
                        kind="interval",
                        name="Hard",
                        cue="Hard",
                        end=StepEnd(kind="time", seconds=60),
                        target=DraftTarget(kind="power_pct_ftp", low=100, high=110),
                    ),
                    DraftStep(
                        kind="recovery",
                        name="Easy",
                        cue="Easy",
                        end=StepEnd(kind="time", seconds=60),
                        target=DraftTarget(kind="none"),
                    ),
                ],
            ),
        ],
    )
    workout = sanitize_workout(
        draft,
        profile=_profile(ftp_watts=200),
        bike=_bike(has_power_meter=True),
        discipline="road",
        available_minutes=30,
    )
    fit_bytes = export_mod.to_fit_workout(workout)
    path = tmp_path / "repeats.fit"
    path.write_bytes(fit_bytes)
    rows = FitFile.from_file(str(path)).to_rows()
    workout_row = next(row for row in rows if row and row[0] == "Data" and row[2] == "workout")
    # num_valid_steps must exclude the repeat meta-step: warmup + hard + easy = 3.
    assert workout_row[workout_row.index("num_valid_steps") + 1] == 3
    repeat_rows = [row for row in rows if row and "repeat_steps" in row]
    assert repeat_rows, "expected a REPEAT_UNTIL_STEPS_CMPLT meta-step"
    assert repeat_rows[0][repeat_rows[0].index("repeat_steps") + 1] == 4


def test_zwo_and_erg_use_watts_not_fabricated_for_power_riders():
    zwo = export_mod.to_zwo(_power_workout(), ftp_watts=250)
    assert "<workout_file>" in zwo and "SteadyState" in zwo
    erg = export_mod.to_erg(_power_workout(), ftp_watts=250)
    assert "[COURSE DATA]" in erg and "225" in erg


# --- generator.py / service.py orchestration ---


class FakeStructuredLLM:
    def __init__(self, response: dict):
        self.response = response
        self.calls: list[list] = []

    async def chat_structured(
        self, messages, schema_name, schema, *, max_completion_tokens, temperature=0
    ):
        self.calls.append(messages)
        return self.response, Usage(CHAT_MODEL, 800, 0, 300)

    async def embed(self, text):
        return [1.0, 0.0], Usage(EMBEDDING_MODEL, 10, 0, 0)


def _generated_response(target: dict) -> dict:
    return {
        "workout": {
            "name": "Hill repeats",
            "est_minutes": 60,
            "steps": [
                {
                    "kind": "warmup",
                    "name": "Warm up",
                    "cue": "Easy spin",
                    "end": {"kind": "time", "seconds": 600, "meters": None},
                    "target": {"kind": "none", "low": None, "high": None, "hr_zone": None},
                },
                {
                    "kind": "interval",
                    "name": "Climb",
                    "cue": "Hard, seated",
                    "end": {"kind": "time", "seconds": 300, "meters": None},
                    "target": target,
                },
                {
                    "kind": "cooldown",
                    "name": "Cool down",
                    "cue": "Easy spin",
                    "end": {"kind": "time", "seconds": 300, "meters": None},
                    "target": {"kind": "none", "low": None, "high": None, "hr_zone": None},
                },
            ],
        },
        "rationale": "This leans into climbing since that's your focus area.",
        "adjustments": None,
    }


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def _seed(db_session, *, ftp_watts=None, power_bike=False):
    db_session.add(
        RiderProfile(
            id=1,
            goal_text="Gran fondo",
            has_hr_monitor=True,
            lthr=160,
            ftp_watts=ftp_watts,
            available_days=["mon", "wed", "sat"],
            weekday_max_minutes=90,
            weekend_max_minutes=180,
            focus_areas=["climbing"],
        )
    )
    db_session.add(Bike(nickname="Road", kind="road", is_primary=True, has_power_meter=power_bike))
    db_session.commit()


async def test_plan_session_drops_power_target_for_a_no_power_rider(db_session):
    _seed(db_session, ftp_watts=None, power_bike=False)
    llm = FakeStructuredLLM(
        _generated_response({"kind": "power_pct_ftp", "low": 95, "high": 105, "hr_zone": None})
    )
    request = SessionRequest(
        planned_date=TODAY + dt.timedelta(days=1),
        available_minutes=60,
        setting="outdoor",
        discipline="road",
        route_idea="hill repeats",
        feel="normal",
    )

    out = await training_service.plan_session(
        db_session, llm, None, request, budget_usd=10.0, now=NOW
    )

    assert out.workout.steps[1].target is None  # sanitized away — no power meter
    assert out.workout.steps[1].cue == "Hard, seated"  # cue still survives
    assert out.available_export_formats == ["fit"]  # no zwo/erg without power
    assert out.status == "planned"
    assert out.bike_id is not None


async def test_plan_session_keeps_power_target_for_a_power_rider(db_session):
    _seed(db_session, ftp_watts=250, power_bike=True)
    llm = FakeStructuredLLM(
        _generated_response({"kind": "power_pct_ftp", "low": 90, "high": 100, "hr_zone": None})
    )
    request = SessionRequest(
        planned_date=TODAY + dt.timedelta(days=1),
        available_minutes=60,
        setting="outdoor",
        discipline="road",
        route_idea="hill repeats",
        feel="normal",
    )

    out = await training_service.plan_session(
        db_session, llm, None, request, budget_usd=10.0, now=NOW
    )

    assert out.workout.steps[1].target is not None
    assert out.workout.steps[1].target.kind == "power"
    assert set(out.available_export_formats) == {"fit", "zwo", "erg"}


async def test_plan_session_over_budget_raises(db_session):
    from soft_floyd_core.llm.usage import BudgetExceededError

    _seed(db_session)
    llm = FakeStructuredLLM(
        _generated_response({"kind": "none", "low": None, "high": None, "hr_zone": None})
    )
    request = SessionRequest(
        planned_date=TODAY, available_minutes=60, setting="outdoor", discipline="road"
    )

    with pytest.raises(BudgetExceededError):
        await training_service.plan_session(db_session, llm, None, request, budget_usd=0.0, now=NOW)
    assert llm.calls == []  # budget checked before the LLM is ever called


async def test_list_status_and_delete(db_session):
    _seed(db_session)
    llm = FakeStructuredLLM(
        _generated_response({"kind": "none", "low": None, "high": None, "hr_zone": None})
    )
    request = SessionRequest(
        planned_date=TODAY, available_minutes=60, setting="outdoor", discipline="road"
    )
    created = await training_service.plan_session(
        db_session, llm, None, request, budget_usd=10.0, now=NOW
    )

    assert [s.id for s in training_service.list_sessions(db_session)] == [created.id]

    updated = training_service.update_status(db_session, created.id, "done")
    assert updated.status == "done"

    training_service.delete_session(db_session, created.id)
    with pytest.raises(training_service.SessionNotFoundError):
        training_service.get_session(db_session, created.id)


async def test_export_session_rejects_unavailable_format(db_session):
    _seed(db_session, ftp_watts=None, power_bike=False)
    llm = FakeStructuredLLM(
        _generated_response({"kind": "none", "low": None, "high": None, "hr_zone": None})
    )
    request = SessionRequest(
        planned_date=TODAY, available_minutes=60, setting="outdoor", discipline="road"
    )
    created = await training_service.plan_session(
        db_session, llm, None, request, budget_usd=10.0, now=NOW
    )

    with pytest.raises(training_service.ExportNotAvailableError):
        training_service.export_session(db_session, created.id, "zwo")

    content, content_type, filename = training_service.export_session(db_session, created.id, "fit")
    assert filename.endswith(".fit")
    assert content_type == "application/octet-stream"


class FakeSyncRunner:
    def __init__(self):
        self.calls: list[tuple] = []

    async def send_workout(self, payload, planned_date, existing_workout_id=None):
        self.calls.append((payload, planned_date, existing_workout_id))
        return "12345"


async def test_send_to_garmin_stores_the_returned_workout_id(db_session):
    _seed(db_session)
    llm = FakeStructuredLLM(
        _generated_response({"kind": "none", "low": None, "high": None, "hr_zone": None})
    )
    request = SessionRequest(
        planned_date=TODAY, available_minutes=60, setting="outdoor", discipline="road"
    )
    created = await training_service.plan_session(
        db_session, llm, None, request, budget_usd=10.0, now=NOW
    )

    runner = FakeSyncRunner()
    out = await training_service.send_to_garmin(db_session, created.id, runner)

    assert out.garmin_workout_id == "12345"
    assert out.sent_to_garmin_at is not None
    assert runner.calls[0][2] is None  # first send has no existing workout id

    await training_service.send_to_garmin(db_session, created.id, runner)
    assert runner.calls[1][2] == "12345"  # a re-send updates the same Garmin workout
