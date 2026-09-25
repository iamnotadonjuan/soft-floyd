"""The one place a numeric workout target is allowed to exist. Turns the
LLM's draft (abstract %FTP / HR-zone / cadence-rpm targets) into the
stored, exportable `Workout` — resolving each target against the
rider's *actual* declared sensors and anchors, or dropping it to a
plain-language cue when they don't back it up. Never trust `sanitize()`'s
input as already honest; the model has no way to enforce this itself.

HR-zone boundaries are the %LTHR table in
docs/design-docs/training-signal-model.md (Z1-Z5); that table only
bounds one side of Z1 and Z5, so this fills in a floor/ceiling wide
enough to give a device workout both ends of a range.
"""

from __future__ import annotations

from soft_floyd_core.bikes.service import BikeOut
from soft_floyd_core.profile.service import ProfileOut
from soft_floyd_core.training.schemas import (
    DraftRepeatBlock,
    DraftStep,
    DraftTarget,
    DraftWorkout,
    RepeatBlock,
    StepTarget,
    Workout,
    WorkoutStep,
    estimate_step_seconds,
)

_ZONE_PCT_OF_LTHR: dict[int, tuple[float, float]] = {
    1: (0.50, 0.79),
    2: (0.80, 0.89),
    3: (0.90, 0.94),
    4: (0.95, 0.99),
    5: (1.00, 1.10),
}
_MIN_STEP_SECONDS = 30.0
_MAX_REPEAT_COUNT = 20


def _resolve_target(draft: DraftTarget, *, bike: BikeOut | None, profile: ProfileOut) -> StepTarget | None:
    if draft.kind == "power_pct_ftp":
        if bike is None or not bike.has_power_meter or not profile.ftp_watts:
            return None
        low_pct = draft.low if draft.low is not None else draft.high
        high_pct = draft.high if draft.high is not None else draft.low
        if low_pct is None or high_pct is None:
            return None
        low_w = round(profile.ftp_watts * low_pct / 100)
        high_w = round(profile.ftp_watts * high_pct / 100)
        return StepTarget(kind="power", low=min(low_w, high_w), high=max(low_w, high_w))

    if draft.kind == "hr_zone":
        if not profile.has_hr_monitor or not profile.lthr or draft.hr_zone not in _ZONE_PCT_OF_LTHR:
            return None
        pct_low, pct_high = _ZONE_PCT_OF_LTHR[draft.hr_zone]
        return StepTarget(
            kind="hr", low=round(profile.lthr * pct_low), high=round(profile.lthr * pct_high)
        )

    if draft.kind == "cadence_rpm":
        if bike is None or not bike.has_cadence_sensor or draft.low is None:
            return None
        high = draft.high if draft.high is not None else draft.low
        return StepTarget(kind="cadence", low=min(draft.low, high), high=max(draft.low, high))

    return None  # "none"


def _sanitize_step(draft: DraftStep, *, bike: BikeOut | None, profile: ProfileOut) -> WorkoutStep:
    return WorkoutStep(
        kind=draft.kind,
        name=draft.name,
        cue=draft.cue,
        end=draft.end,
        target=_resolve_target(draft.target, bike=bike, profile=profile),
    )


def sanitize_workout(
    draft: DraftWorkout,
    *,
    profile: ProfileOut,
    bike: BikeOut | None,
    discipline: str,
    available_minutes: int,
) -> Workout:
    items: list[WorkoutStep | RepeatBlock] = []
    for item in draft.steps:
        if isinstance(item, DraftRepeatBlock):
            count = max(2, min(item.count, _MAX_REPEAT_COUNT))
            items.append(
                RepeatBlock(
                    count=count,
                    steps=[_sanitize_step(s, bike=bike, profile=profile) for s in item.steps],
                )
            )
        else:
            items.append(_sanitize_step(item, bike=bike, profile=profile))

    workout = Workout(name=draft.name, est_minutes=draft.est_minutes, steps=items)
    return _clamp_duration(workout, discipline=discipline, available_minutes=available_minutes)


def _clamp_duration(workout: Workout, *, discipline: str, available_minutes: int) -> Workout:
    """Scales down interval/recovery step durations (never warmup/cooldown,
    never a distance or lap_button end) so the estimated total fits the
    rider's stated available time, within a 10% tolerance. A heuristic,
    not a guarantee — the rider sees est_minutes and can always
    regenerate with more time.
    """
    target_seconds = available_minutes * 60
    total_seconds = sum(estimate_step_seconds(s, discipline) for s in workout.flattened_steps())
    if total_seconds <= target_seconds * 1.1 or total_seconds == 0:
        return workout.model_copy(update={"est_minutes": round(total_seconds / 60)})

    scale = target_seconds / total_seconds

    def _scale_step(step: WorkoutStep) -> WorkoutStep:
        if step.kind in ("interval", "recovery") and step.end.kind == "time" and step.end.seconds:
            scaled = max(_MIN_STEP_SECONDS, step.end.seconds * scale)
            return step.model_copy(update={"end": step.end.model_copy(update={"seconds": scaled})})
        return step

    new_items: list[WorkoutStep | RepeatBlock] = []
    for item in workout.steps:
        if isinstance(item, RepeatBlock):
            new_items.append(item.model_copy(update={"steps": [_scale_step(s) for s in item.steps]}))
        else:
            new_items.append(_scale_step(item))

    scaled_workout = workout.model_copy(update={"steps": new_items})
    new_total = sum(estimate_step_seconds(s, discipline) for s in scaled_workout.flattened_steps())
    return scaled_workout.model_copy(update={"est_minutes": round(new_total / 60)})
