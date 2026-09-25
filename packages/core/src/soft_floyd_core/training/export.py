"""Pure functions turning a sanitized `Workout` into device formats. Every
function here trusts that sanitize.py already dropped any target the
rider's sensors don't back — this module never reaches back into the
profile or a bike to invent one, with one narrow, documented exception:
`to_zwo`/`to_erg` need *some* wattage on every second of an ERG-mode
file, so a step the coach deliberately left target-less (e.g. an easy
warmup) gets a coarse fraction-of-FTP filler. Callers must only offer
these two formats when the rider has a power meter and `ftp_watts` set —
see `service.py::available_export_formats`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from soft_floyd_core.training.schemas import (
    RepeatBlock,
    StepTarget,
    Workout,
    WorkoutStep,
    estimate_step_seconds,
)

ExportFormat = str  # "garmin_json" | "fit" | "zwo" | "erg"

# Filler intensity (fraction of FTP) for a step with no power target, used
# only by to_zwo/to_erg — see module docstring.
_FILLER_PCT_FTP = {"warmup": 0.5, "interval": 0.75, "recovery": 0.55, "cooldown": 0.5}


# --- Garmin Connect workout JSON (garminconnect.workout typed builders) ---


def to_garmin_payload(workout: Workout) -> dict[str, Any]:
    from garminconnect.workout import (
        ConditionType,
        CyclingWorkout,
        ExecutableStep,
        RepeatGroup,
        StepType,
        TargetType,
        WorkoutSegment,
        create_repeat_group,
    )

    _STEP_TYPE = {
        "warmup": (StepType.WARMUP, "warmup", 1),
        "interval": (StepType.INTERVAL, "interval", 3),
        "recovery": (StepType.RECOVERY, "recovery", 4),
        "cooldown": (StepType.COOLDOWN, "cooldown", 2),
    }
    _TARGET_TYPE = {
        "power": (TargetType.POWER_ZONE, "power.zone", 2),
        "hr": (TargetType.HEART_RATE_ZONE, "heart.rate.zone", 4),
        "cadence": (TargetType.CADENCE, "cadence", 3),
    }

    def end_condition(step: WorkoutStep) -> tuple[dict[str, Any], float]:
        if step.end.kind == "time":
            return (
                {
                    "conditionTypeId": ConditionType.TIME,
                    "conditionTypeKey": "time",
                    "displayOrder": 2,
                    "displayable": True,
                },
                float(step.end.seconds or 0),
            )
        if step.end.kind == "distance":
            return (
                {
                    "conditionTypeId": ConditionType.DISTANCE,
                    "conditionTypeKey": "distance",
                    "displayOrder": 3,
                    "displayable": True,
                },
                float(step.end.meters or 0),
            )
        return (
            {
                "conditionTypeId": ConditionType.LAP_BUTTON,
                "conditionTypeKey": "lap.button",
                "displayOrder": 1,
                "displayable": True,
            },
            0.0,
        )

    def target(target: StepTarget | None) -> tuple[dict[str, Any], dict[str, Any]]:
        if target is None:
            return {
                "workoutTargetTypeId": TargetType.NO_TARGET,
                "workoutTargetTypeKey": "no.target",
                "displayOrder": 1,
            }, {}
        type_id, key, order = _TARGET_TYPE[target.kind]
        return (
            {"workoutTargetTypeId": type_id, "workoutTargetTypeKey": key, "displayOrder": order},
            {"targetValueOne": target.low, "targetValueTwo": target.high},
        )

    def build_step(step: WorkoutStep, order: int) -> ExecutableStep:
        step_type_id, step_key, step_order = _STEP_TYPE[step.kind]
        end_cond, end_value = end_condition(step)
        target_type, extra = target(step.target)
        return ExecutableStep(
            stepOrder=order,
            stepType={"stepTypeId": step_type_id, "stepTypeKey": step_key, "displayOrder": step_order},
            endCondition=end_cond,
            endConditionValue=end_value,
            targetType=target_type,
            **extra,
        )

    steps: list[ExecutableStep | RepeatGroup] = []
    order = 1
    for item in workout.steps:
        if isinstance(item, RepeatBlock):
            children = []
            for child in item.steps:
                children.append(build_step(child, order))
                order += 1
            steps.append(create_repeat_group(item.count, children, order))
            order += 1
        else:
            steps.append(build_step(item, order))
            order += 1

    cycling = CyclingWorkout(
        workoutName=workout.name,
        estimatedDurationInSecs=workout.est_minutes * 60,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
                workoutSteps=steps,
            )
        ],
    )
    return cycling.to_dict()


# --- FIT workout file (fit-tool) ---


def to_fit_workout(workout: Workout) -> bytes:
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import (
        FileType,
        Intensity,
        Manufacturer,
        Sport,
        WorkoutStepDuration,
        WorkoutStepTarget,
    )

    _INTENSITY = {
        "warmup": Intensity.WARMUP,
        "interval": Intensity.ACTIVE,
        "recovery": Intensity.RECOVERY,
        "cooldown": Intensity.COOLDOWN,
    }

    file_id = FileIdMessage()
    file_id.type = FileType.WORKOUT
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.time_created = round(dt.datetime.now(dt.UTC).timestamp() * 1000)
    file_id.serial_number = 0x536F4674  # "SoFt" — a stable dev serial, not a real device.

    step_messages: list[WorkoutStepMessage] = []

    def add_step(step: WorkoutStep) -> int:
        msg = WorkoutStepMessage()
        index = len(step_messages)
        msg.message_index = index
        msg.workout_step_name = step.name[:40]
        msg.intensity = _INTENSITY[step.kind]

        if step.end.kind == "time":
            msg.duration_type = WorkoutStepDuration.TIME
            msg.duration_time = float(step.end.seconds or 0)
        elif step.end.kind == "distance":
            msg.duration_type = WorkoutStepDuration.DISTANCE
            msg.duration_distance = float(step.end.meters or 0)
        else:
            msg.duration_type = WorkoutStepDuration.OPEN

        target = step.target
        if target is None:
            msg.target_type = WorkoutStepTarget.OPEN
        elif target.kind == "power":
            msg.target_type = WorkoutStepTarget.POWER
            msg.custom_target_power_low = round(target.low)
            msg.custom_target_power_high = round(target.high)
        elif target.kind == "hr":
            msg.target_type = WorkoutStepTarget.HEART_RATE
            msg.custom_target_heart_rate_low = round(target.low)
            msg.custom_target_heart_rate_high = round(target.high)
        else:  # cadence
            msg.target_type = WorkoutStepTarget.CADENCE
            msg.custom_target_cadence_low = round(target.low)
            msg.custom_target_cadence_high = round(target.high)

        step_messages.append(msg)
        return index

    valid_step_count = 0
    for item in workout.steps:
        if isinstance(item, RepeatBlock):
            first_index: int | None = None
            for child in item.steps:
                idx = add_step(child)
                if first_index is None:
                    first_index = idx
                valid_step_count += 1
            # The repeat meta-step itself doesn't count toward
            # num_valid_steps — see fit_tool.validation's FILE_TYPE rule.
            repeat_msg = WorkoutStepMessage()
            repeat_msg.message_index = len(step_messages)
            repeat_msg.duration_type = WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT
            repeat_msg.duration_step = first_index
            repeat_msg.target_type = WorkoutStepTarget.OPEN
            repeat_msg.target_repeat_steps = item.count
            step_messages.append(repeat_msg)
        else:
            add_step(item)
            valid_step_count += 1

    workout_msg = WorkoutMessage()
    workout_msg.workout_name = workout.name[:40]
    workout_msg.sport = Sport.CYCLING
    workout_msg.num_valid_steps = valid_step_count

    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    builder.add(file_id)
    builder.add(workout_msg)
    builder.add_all(step_messages)
    return builder.build_bytes()


# --- ZWO (Zwift) and ERG (generic ERG-mode trainer software) ---


def _watts_fraction(step: WorkoutStep, ftp_watts: int) -> tuple[float, float]:
    if step.target is not None and step.target.kind == "power":
        return step.target.low / ftp_watts, step.target.high / ftp_watts
    pct = _FILLER_PCT_FTP.get(step.kind, 0.6)
    return pct, pct


def to_zwo(workout: Workout, *, ftp_watts: int) -> str:
    """Zwift/SYSTM workout XML. Power is a fraction of FTP (0.75 = 75%),
    not watts — the format's own convention, so this is the one place a
    concrete FTP-relative fraction gets computed for display, not stored.
    """
    lines = [
        '<workout_file>',
        "  <author>Soft Floyd</author>",
        f"  <name>{_xml_escape(workout.name)}</name>",
        "  <sportType>bike</sportType>",
        "  <workout>",
    ]
    for step in workout.flattened_steps():
        seconds = round(estimate_step_seconds(step, "road"))
        low, high = _watts_fraction(step, ftp_watts)
        if step.kind == "warmup":
            lines.append(f'    <Warmup Duration="{seconds}" PowerLow="{low:.2f}" PowerHigh="{high:.2f}"/>')
        elif step.kind == "cooldown":
            lines.append(f'    <Cooldown Duration="{seconds}" PowerLow="{high:.2f}" PowerHigh="{low:.2f}"/>')
        else:
            power = (low + high) / 2
            lines.append(f'    <SteadyState Duration="{seconds}" Power="{power:.2f}"/>')
    lines += ["  </workout>", "</workout_file>"]
    return "\n".join(lines)


def to_erg(workout: Workout, *, ftp_watts: int) -> str:
    """Absolute-watts ERG course file (TrainerRoad/PerfPRO/Golden Cheetah
    and most smart-trainer ERG-mode software import this)."""
    lines = [
        "[COURSE HEADER]",
        "VERSION = 2",
        "UNITS = ENGLISH",
        f"DESCRIPTION = {workout.name}",
        "FILE NAME = workout.erg",
        "MINUTES WATTS",
        "[END COURSE HEADER]",
        "[COURSE DATA]",
    ]
    t = 0.0
    for step in workout.flattened_steps():
        seconds = estimate_step_seconds(step, "road")
        low_frac, high_frac = _watts_fraction(step, ftp_watts)
        start_w = round(ftp_watts * low_frac)
        end_w = round(ftp_watts * high_frac)
        lines.append(f"{t / 60:.2f}\t{start_w}")
        t += seconds
        lines.append(f"{t / 60:.2f}\t{end_w}")
    lines.append("[END COURSE DATA]")
    return "\n".join(lines)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
