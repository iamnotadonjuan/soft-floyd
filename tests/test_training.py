"""Training sessions (exec-plan 0010): the sensor-honesty gate
(sanitize.py), the deterministic intent (intent.py), device export
(export.py), and the generator/service orchestration with a fake LLM.
"""

from __future__ import annotations

import datetime as dt
import struct

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
from soft_floyd_core.metrics.service import TrainingLoadOut
from soft_floyd_core.models import (
    Activity,
    Base,
    Bike,
    Book,
    BookPassage,
    LLMUsageRecord,
    RiderProfile,
)
from soft_floyd_core.profile.service import ProfileOut
from soft_floyd_core.training import export as export_mod
from soft_floyd_core.training import service as training_service
from soft_floyd_core.training.intent import recommend_intent, recommend_rest
from soft_floyd_core.training.sanitize import sanitize_workout
from soft_floyd_core.training.schemas import (
    DraftRepeatBlock,
    DraftStep,
    DraftTarget,
    DraftWorkout,
    SessionChanges,
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


def _load(tsb, *, ramp=0.0, confidence="ok", basis_counts=None):
    return TrainingLoadOut(
        as_of=TODAY,
        ctl=50.0,
        atl=50.0 - tsb,
        tsb=tsb,
        form="neutral",
        ramp_rate_7d=ramp,
        days_of_history=60,
        confidence=confidence,
        basis_counts=basis_counts or {"hr_zones": 10},
        series=[],
        notes=[],
    )


def _intent_with(load, **profile):
    return recommend_intent(_request(), _profile(**profile), _summary(), [], today=TODAY, load=load)


def test_very_tired_form_means_recovery_and_quotes_the_numbers():
    intent = _intent_with(_load(-35.0))
    assert intent.emphasis == "recovery"
    assert any("form -35" in r and "fatigue 85" in r for r in intent.reasons)


def test_steep_ramp_means_recovery_even_when_form_is_fine():
    assert _intent_with(_load(-5.0, ramp=9.5)).emphasis == "recovery"


def test_very_tired_form_outranks_the_tempo_a_close_event_would_ask_for():
    profile = {"target_event_date": TODAY + dt.timedelta(days=10)}
    assert _intent_with(_load(-40.0), **profile).emphasis == "recovery"


def test_tired_form_keeps_it_aerobic():
    intent = _intent_with(_load(-20.0), self_rated_level="competitive")
    assert intent.emphasis == "endurance"


def test_fresh_and_slipping_fitness_asks_for_intensity_by_rider_level():
    assert _intent_with(_load(10.0, ramp=-2.0), self_rated_level="competitive").emphasis == (
        "threshold"
    )
    assert _intent_with(_load(10.0, ramp=-2.0), self_rated_level="recreational").emphasis == (
        "tempo"
    )
    # Fresh but still building: no load rule fires, the old chain decides.
    assert _intent_with(_load(10.0, ramp=3.0), self_rated_level="beginner").emphasis == (
        "endurance"
    )


def test_load_is_ignored_until_there_is_enough_history():
    for confidence in ("low", "partial"):
        assert _intent_with(_load(-45.0, confidence=confidence)).emphasis == "endurance"


def test_mostly_estimated_load_is_flagged_in_the_reason():
    intent = _intent_with(_load(-35.0, basis_counts={"duration": 8, "hr_zones": 2}))
    assert any("partly estimated" in r for r in intent.reasons)


def test_feel_and_taper_rules_still_outrank_load():
    intent = recommend_intent(
        _request(feel="tired"), _profile(), _summary(), [], today=TODAY, load=_load(15.0, ramp=-3)
    )
    assert intent.emphasis == "recovery"
    assert any("tired" in r for r in intent.reasons)


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


def test_rest_needs_a_near_date_and_real_recent_signal():
    assert recommend_rest(_request(feel="tired"), [_ride(0, 6000)], today=TODAY, load=None)
    assert not recommend_rest(
        _request(feel="tired", planned_date=TODAY + dt.timedelta(days=4)),
        [_ride(0, 6000)],
        today=TODAY,
        load=None,
    )
    assert not recommend_rest(_request(feel="tired"), [_ride(0, 1200)], today=TODAY, load=None)
    very_tired = _load(-35).model_copy(update={"form": "very tired"})
    assert recommend_rest(_request(), [], today=TODAY, load=very_tired)
    assert not recommend_rest(
        _request(),
        [],
        today=TODAY,
        load=very_tired.model_copy(update={"confidence": "partial"}),
    )


def test_outdoor_context_is_optional_and_cleared_indoor():
    outdoor = _request(training_area="  Bogotá north  ", terrain="hilly", starting_altitude_m=2600)
    assert outdoor.training_area == "Bogotá north"
    assert SessionRequest.model_validate(outdoor.model_dump()).terrain == "hilly"
    indoor = outdoor.model_copy(update={"setting": "indoor"})
    indoor = SessionRequest.model_validate(indoor.model_dump())
    assert (indoor.training_area, indoor.terrain, indoor.starting_altitude_m) == ("", None, None)
    changes = SessionChanges.model_validate({"terrain": None, "starting_altitude_m": None})
    assert changes.sent() == {"terrain": None, "starting_altitude_m": None}


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


async def test_suggestion_rest_is_unsaved_and_hides_unverified_power(db_session):
    _seed(db_session)
    db_session.add(
        Activity(
            garmin_id=101,
            start_time=NOW,
            bike_type="road",
            duration_s=6000,
            distance_m=50000,
            elev_gain_m=500,
            avg_power_w=240,
            has_power_data=True,
            fit_status="ok",
        )
    )
    db_session.commit()
    llm = FakeStructuredLLM({"rationale": "Take a rest day after that long ride."})
    result = await training_service.suggest_session(
        db_session, llm, None, _request(feel="tired"), budget_usd=10.0, now=NOW
    )
    assert result.kind == "rest" and result.session is None
    assert result.rides[0].avg_power_w is None
    assert len(training_service.list_sessions(db_session)) == 0
    assert "recent_rides" in llm.calls[0][1]["content"]


async def test_suggestion_workout_saves_and_uses_outdoor_context(db_session):
    _seed(db_session)
    llm = FakeStructuredLLM(
        _generated_response({"kind": "none", "low": None, "high": None, "hr_zone": None})
    )
    request = _request(
        route_idea="", training_area="Bogotá north", terrain="flat", starting_altitude_m=2600
    )
    result = await training_service.suggest_session(
        db_session, llm, None, request, budget_usd=10.0, now=NOW
    )
    assert result.kind == "session" and result.session is not None
    assert result.session.request.terrain == "flat"
    assert result.rides == []
    assert "Training area: Bogotá north" in llm.calls[0][1]["content"]
    assert len(training_service.list_sessions(db_session)) == 1


async def test_suggestion_uses_imported_book_passage_and_records_both_paid_calls(db_session):
    _seed(db_session)
    book = Book(sha256="a" * 64, title="Training guide", source_name="guide.pdf")
    db_session.add(book)
    db_session.flush()
    db_session.add(
        BookPassage(
            book_id=book.id,
            ordinal=0,
            page_start=12,
            page_end=12,
            text="Easy recovery after a hard training block.",
            embedding=struct.pack("<2f", 1, 0),
        )
    )
    db_session.commit()
    llm = FakeStructuredLLM(
        _generated_response({"kind": "none", "low": None, "high": None, "hr_zone": None})
    )
    result = await training_service.suggest_session(
        db_session, llm, llm, _request(route_idea=""), budget_usd=10.0, now=NOW
    )
    assert result.kind == "session"
    assert [(s.title, s.page_start) for s in result.sources] == [("Training guide", 12)]
    assert "Training guide p.12" in llm.calls[0][1]["content"]
    assert db_session.query(LLMUsageRecord).count() == 2


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


# --- generator prompt: training-load snapshot ---


def test_prompt_includes_load_only_when_it_can_be_trusted():
    from soft_floyd_core.training.generator import _prompt
    from soft_floyd_core.training.schemas import SessionIntent

    intent = SessionIntent(emphasis="endurance", reasons=["steady"], off_schedule=False)
    args = (_request(), intent, _profile(), None, [])

    trusted = _prompt(*args, load=_load(-13.0, ramp=4.0))
    assert "<training_load>" in trusted
    assert "form -13" in trusted and "+4.0 over the last 7 days" in trusted

    assert "<training_load>" not in _prompt(*args, load=_load(-13.0, confidence="partial"))
    assert "<training_load>" not in _prompt(*args)


# --- editing a planned session (exec-plan 0013) ---

_NO_TARGET = {"kind": "none", "low": None, "high": None, "hr_zone": None}
SATURDAY = dt.date(2026, 9, 26)  # in the seeded available_days
TUESDAY = dt.date(2026, 9, 29)  # not in them


async def _planned(db_session, llm=None, **request_overrides):
    _seed(db_session)
    llm = llm or FakeStructuredLLM(_generated_response(_NO_TARGET))
    fields = {
        "planned_date": SATURDAY,
        "available_minutes": 60,
        "setting": "outdoor",
        "discipline": "road",
    }
    request = SessionRequest(**{**fields, **request_overrides})
    created = await training_service.plan_session(
        db_session, llm, None, request, budget_usd=10.0, now=NOW
    )
    return created, llm


def test_session_changes_tells_a_null_bike_from_an_unsent_one():
    assert SessionChanges().sent() == {}
    assert SessionChanges(bike_id=None).sent() == {"bike_id": None}
    assert SessionChanges.model_validate({"available_minutes": None, "feel": "tired"}).sent() == {
        "feel": "tired"
    }


async def test_moving_only_the_date_keeps_the_workout_and_makes_no_ai_call(db_session):
    created, llm = await _planned(db_session)
    await training_service.send_to_garmin(db_session, created.id, FakeSyncRunner())
    assert len(llm.calls) == 1

    moved = await training_service.update_session(
        db_session,
        llm,
        None,
        created.id,
        SessionChanges(planned_date=TUESDAY),
        budget_usd=10.0,
        now=NOW,
    )

    assert len(llm.calls) == 1
    assert moved.planned_date == TUESDAY
    assert moved.request.planned_date == TUESDAY
    assert moved.workout == created.workout
    assert moved.rationale == created.rationale
    assert moved.intent.off_schedule is True  # Tuesday isn't a usual riding day
    assert moved.garmin_workout_id == "12345"  # same Garmin workout, re-sent later
    assert moved.sent_to_garmin_at is None  # the Garmin calendar still has the old date

    back = await training_service.update_session(
        db_session,
        llm,
        None,
        created.id,
        SessionChanges(planned_date=SATURDAY),
        budget_usd=10.0,
        now=NOW,
    )
    assert back.intent.off_schedule is False


async def test_changing_the_minutes_rebuilds_the_workout(db_session):
    created, llm = await _planned(db_session)
    await training_service.send_to_garmin(db_session, created.id, FakeSyncRunner())
    llm.response = {**llm.response, "rationale": "Shorter, as asked."}

    out = await training_service.update_session(
        db_session,
        llm,
        None,
        created.id,
        SessionChanges(available_minutes=30),
        budget_usd=10.0,
        now=NOW,
    )

    assert len(llm.calls) == 2
    assert out.request.available_minutes == 30
    assert out.rationale == "Shorter, as asked."
    assert out.garmin_workout_id is None and out.sent_to_garmin_at is None
    assert "30" in llm.calls[1][1]["content"]  # the edited minutes reached the prompt


async def test_changing_the_discipline_repicks_the_bike(db_session):
    created, llm = await _planned(db_session)
    db_session.add(Bike(nickname="Gravel", kind="gravel"))
    db_session.commit()
    gravel_id = db_session.query(Bike).filter_by(kind="gravel").one().id
    assert created.bike_id != gravel_id

    out = await training_service.update_session(
        db_session,
        llm,
        None,
        created.id,
        SessionChanges(discipline="gravel"),
        budget_usd=10.0,
        now=NOW,
    )

    assert out.discipline == "gravel"
    assert out.bike_id == gravel_id
    assert out.request.bike_id == gravel_id


async def test_an_explicit_bike_is_honoured(db_session):
    created, llm = await _planned(db_session)
    db_session.add(Bike(nickname="Gravel", kind="gravel"))
    db_session.commit()
    gravel_id = db_session.query(Bike).filter_by(kind="gravel").one().id

    out = await training_service.update_session(
        db_session,
        llm,
        None,
        created.id,
        SessionChanges(bike_id=gravel_id),
        budget_usd=10.0,
        now=NOW,
    )

    assert out.bike_id == gravel_id
    assert out.discipline == "road"  # only the bike changed


async def test_an_edit_that_changes_nothing_makes_no_ai_call(db_session):
    created, llm = await _planned(db_session)

    same = await training_service.update_session(
        db_session,
        llm,
        None,
        created.id,
        SessionChanges(available_minutes=60, setting="outdoor"),
        budget_usd=10.0,
        now=NOW,
    )

    assert len(llm.calls) == 1
    assert same.request == created.request
    assert same.workout == created.workout


@pytest.mark.parametrize("status", ["done", "skipped"])
async def test_only_planned_sessions_can_be_edited(db_session, status):
    created, llm = await _planned(db_session)
    training_service.update_status(db_session, created.id, status)

    with pytest.raises(training_service.SessionNotEditableError):
        await training_service.update_session(
            db_session,
            llm,
            None,
            created.id,
            SessionChanges(available_minutes=30),
            budget_usd=10.0,
            now=NOW,
        )
    assert len(llm.calls) == 1


async def test_a_rebuild_over_budget_leaves_the_session_untouched(db_session):
    from soft_floyd_core.llm.usage import BudgetExceededError

    created, llm = await _planned(db_session)

    with pytest.raises(BudgetExceededError):
        await training_service.update_session(
            db_session,
            llm,
            None,
            created.id,
            SessionChanges(available_minutes=30),
            budget_usd=0.0,
            now=NOW,
        )

    unchanged = training_service.get_session(db_session, created.id)
    assert unchanged.request.available_minutes == 60
    assert unchanged.workout == created.workout
    assert len(llm.calls) == 1


async def test_a_rebuild_needs_an_llm_but_a_move_does_not(db_session):
    created, llm = await _planned(db_session)

    moved = await training_service.update_session(
        db_session,
        None,
        None,
        created.id,
        SessionChanges(planned_date=TUESDAY),
        budget_usd=10.0,
        now=NOW,
    )
    assert moved.planned_date == TUESDAY

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await training_service.update_session(
            db_session,
            None,
            None,
            created.id,
            SessionChanges(available_minutes=30),
            budget_usd=10.0,
            now=NOW,
        )


async def test_editing_an_unknown_session_raises(db_session):
    _seed(db_session)
    with pytest.raises(training_service.SessionNotFoundError):
        await training_service.update_session(
            db_session,
            None,
            None,
            999,
            SessionChanges(planned_date=TUESDAY),
            budget_usd=10.0,
            now=NOW,
        )


async def test_a_failed_calendar_step_keeps_the_garmin_workout_id_for_the_retry(db_session):
    from soft_floyd_core.garmin.errors import GarminUnavailable, WorkoutNotScheduled

    created, _ = await _planned(db_session)

    class SchedulingFails(FakeSyncRunner):
        async def send_workout(self, payload, planned_date, existing_workout_id=None):
            self.calls.append((payload, planned_date, existing_workout_id))
            raise WorkoutNotScheduled("scheduling failed", workout_id="999", status=503)

    with pytest.raises(WorkoutNotScheduled):
        await training_service.send_to_garmin(db_session, created.id, SchedulingFails())

    kept = training_service.get_session(db_session, created.id)
    assert kept.garmin_workout_id == "999"
    assert kept.sent_to_garmin_at is None  # not on the calendar yet

    runner = FakeSyncRunner()
    await training_service.send_to_garmin(db_session, created.id, runner)
    assert runner.calls[0][2] == "999"  # the retry updates that workout, no duplicate

    class UploadFails(FakeSyncRunner):
        async def send_workout(self, payload, planned_date, existing_workout_id=None):
            raise GarminUnavailable("upload failed", status=521)

    other = await training_service.plan_session(
        db_session,
        FakeStructuredLLM(_generated_response(_NO_TARGET)),
        None,
        SessionRequest(
            planned_date=SATURDAY, available_minutes=60, setting="outdoor", discipline="road"
        ),
        budget_usd=10.0,
        now=NOW,
    )
    with pytest.raises(GarminUnavailable):
        await training_service.send_to_garmin(db_session, other.id, UploadFails())
    assert training_service.get_session(db_session, other.id).garmin_workout_id is None
