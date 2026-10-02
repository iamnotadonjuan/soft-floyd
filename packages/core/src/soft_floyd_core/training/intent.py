"""What the rider *should* do — computed deterministically from their
training summary, recent rides and profile, never guessed by the LLM.
`generator.py` hands this to the model alongside the rider's own idea;
the model's job is to blend the two, not invent this half.

Deliberately reads only duration/distance/date from recent rides (always
known from Garmin's own activity summary, independent of FIT parse
success) plus `get_training_summary`'s week aggregates, which already
apply the per-ride sensor gate to avg_hr/avg_power_w — this module never
reads a raw Activity's HR/power fields directly. See
docs/design-docs/sensor-capability-model.md.

Once there is enough ride history for `metrics.service.get_training_load`
to be trusted (confidence "ok"), form and ramp rate also steer the
emphasis (exec-plan 0012); before that they are ignored entirely.
"""

from __future__ import annotations

import datetime as dt

from soft_floyd_core.activities.service import ActivitySummaryOut, TrainingSummaryOut
from soft_floyd_core.metrics.service import (
    FRESH_TSB,
    TIRED_TSB,
    VERY_TIRED_TSB,
    TrainingLoadOut,
)
from soft_floyd_core.profile.service import ProfileOut
from soft_floyd_core.training.schemas import Emphasis, SessionIntent, SessionRequest

_WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# A ride this long or longer, within the last day, calls for recovery
# regardless of what the summary says about the week as a whole.
_LONG_RIDE_SECONDS = 90 * 60
# CTL gained in a week beyond which fatigue tends to outrun adaptation; the
# usual coaching rule of thumb is 5-8 points a week for a sustainable build.
_RAMP_CEILING = 8.0


def _weekday_code(day: dt.date) -> str:
    return _WEEKDAY_CODES[day.weekday()]


def is_off_schedule(profile: ProfileOut, day: dt.date) -> bool:
    """True when the rider has usual riding days and `day` isn't one."""
    return bool(profile.available_days) and _weekday_code(day) not in profile.available_days


def recommend_intent(
    request: SessionRequest,
    profile: ProfileOut,
    summary: TrainingSummaryOut,
    recent_rides: list[ActivitySummaryOut],
    *,
    today: dt.date,
    load: TrainingLoadOut | None = None,
) -> SessionIntent:
    reasons: list[str] = []
    off_schedule = is_off_schedule(profile, request.planned_date)
    if off_schedule:
        reasons.append("This day isn't one of your usual riding days — keeping it flexible.")

    this_week = summary.weeks[-1] if summary.weeks else None
    hours_this_week = this_week.duration_h if this_week else 0.0

    last_ride = recent_rides[0] if recent_rides else None
    days_since_last_ride = (today - last_ride.start_time.date()).days if last_ride else None
    last_ride_was_long = last_ride is not None and last_ride.duration_s >= _LONG_RIDE_SECONDS

    days_to_event: int | None = None
    if profile.target_event_date:
        days_to_event = (profile.target_event_date - today).days

    # Load only steers the session once there is enough history to trust it.
    load_ok = load is not None and load.confidence == "ok"
    load_note = _load_note(load) if load_ok and load is not None else ""

    emphasis: Emphasis

    if request.feel == "tired":
        emphasis = "recovery"
        reasons.append("You said you're feeling tired, so this eases off.")
    elif days_since_last_ride is not None and days_since_last_ride <= 1 and last_ride_was_long:
        emphasis = "recovery"
        reasons.append("Your last ride was long and recent — this is a recovery-focused session.")
    elif days_to_event is not None and 0 <= days_to_event <= 3:
        emphasis = "recovery"
        event = f" for {profile.target_event_name}" if profile.target_event_name else ""
        reasons.append(f"Only {days_to_event} day(s) left{event} — easing off to arrive fresh.")
    elif (
        load_ok
        and load is not None
        and (load.tsb < VERY_TIRED_TSB or load.ramp_rate_7d > _RAMP_CEILING)
    ):
        emphasis = "recovery"
        reasons.append(
            f"Your training load is high ({load_note}) — this is a recovery-focused session."
        )
    elif days_to_event is not None and 4 <= days_to_event <= 14:
        emphasis = "tempo"
        event = f" ({profile.target_event_name})" if profile.target_event_name else ""
        reasons.append(f"Your event{event} is close — controlled intensity rather than a deep dig.")
    elif load_ok and load is not None and load.tsb < TIRED_TSB:
        emphasis = "endurance"
        reasons.append(f"You're carrying some fatigue ({load_note}) — keeping this aerobic.")
    elif "climbing" in profile.focus_areas and request.setting == "outdoor":
        emphasis = "climbing"
        reasons.append("Climbing is one of your focus areas, so this leans into hill work.")
    elif load_ok and load is not None and load.tsb >= FRESH_TSB and load.ramp_rate_7d <= 0:
        driven = profile.self_rated_level in ("enthusiast", "competitive")
        emphasis = "threshold" if driven else "tempo"
        reasons.append(
            f"You're fresh and your fitness is slipping ({load_note}) — time for some "
            f"{'threshold' if driven else 'tempo'} work."
        )
    elif profile.weekly_hours > 0 and hours_this_week >= profile.weekly_hours:
        emphasis = "endurance"
        reasons.append("You've already reached your weekly hours target — keeping this lighter.")
    elif days_since_last_ride is not None and days_since_last_ride >= 4:
        emphasis = "endurance"
        reasons.append(
            f"It's been {days_since_last_ride} days since your last ride — "
            "building back up steadily."
        )
    elif profile.self_rated_level in ("enthusiast", "competitive"):
        emphasis = "threshold"
        reasons.append("Building fitness with a threshold-focused session.")
    else:
        emphasis = "endurance"
        reasons.append("A steady endurance session to build your aerobic base.")

    return SessionIntent(emphasis=emphasis, reasons=reasons, off_schedule=off_schedule)


def recommend_rest(
    request: SessionRequest,
    recent_rides: list[ActivitySummaryOut],
    *,
    today: dt.date,
    load: TrainingLoadOut | None,
) -> bool:
    """A short-horizon rest suggestion; older or sparse load cannot trigger it."""
    days_ahead = (request.planned_date - today).days
    if not 0 <= days_ahead <= 2:
        return False
    last_ride = recent_rides[0] if recent_rides else None
    recent_long_ride = (
        last_ride is not None
        and 0 <= (today - last_ride.start_time.date()).days <= 1
        and last_ride.duration_s >= _LONG_RIDE_SECONDS
    )
    return (request.feel == "tired" and recent_long_ride) or (
        load is not None and load.confidence == "ok" and load.form == "very tired"
    )


def _load_note(load: TrainingLoadOut) -> str:
    """The numbers behind a load-driven reason, with an honest caveat when
    most of the rider's rides could only be scored from duration."""
    total = sum(load.basis_counts.values())
    estimated = load.basis_counts.get("duration", 0)
    caveat = ", partly estimated" if total and estimated * 2 >= total else ""
    return f"fitness {load.ctl:.0f}, fatigue {load.atl:.0f}, form {load.tsb:+.0f}{caveat}"
