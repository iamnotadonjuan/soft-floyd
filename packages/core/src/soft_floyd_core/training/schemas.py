"""Shapes shared across the training package: the rider's request, the
deterministic intent that request is weighed against, and the workout
itself — both the LLM's draft (abstract %FTP/HR-zone targets) and the
sanitized, storable form (concrete watts/bpm/rpm, or a plain-language
cue when no sensor backs a number). See `sanitize.py` for draft -> final.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from soft_floyd_core.models import Discipline

SessionSetting = Literal["indoor", "outdoor"]
Feel = Literal["fresh", "normal", "tired"]
SessionStatus = Literal["planned", "done", "skipped"]
WorkoutDevice = Literal["garmin", "wahoo", "zwift", "other"]
Emphasis = Literal["recovery", "endurance", "tempo", "threshold", "vo2", "climbing"]
StepKind = Literal["warmup", "interval", "recovery", "cooldown"]
EndKind = Literal["time", "distance", "lap_button"]


class SessionRequest(BaseModel):
    """What the rider asked for. Persisted verbatim on TrainingSession.request."""

    planned_date: dt.date
    available_minutes: int = Field(gt=0, le=600)
    setting: SessionSetting
    discipline: Discipline
    bike_id: int | None = None
    route_idea: str = ""
    feel: Feel = "normal"


class SessionIntent(BaseModel):
    """The deterministic (non-LLM) read on what this session should do —
    training/intent.py's output. Persisted on TrainingSession.intent so a
    later "why did it recommend this" is answerable without recomputing
    it against training data that may have since changed.
    """

    emphasis: Emphasis
    reasons: list[str]
    off_schedule: bool  # planned_date isn't one of the rider's available_days


class StepEnd(BaseModel):
    kind: EndKind
    seconds: float | None = None  # kind == "time"
    meters: float | None = None  # kind == "distance"


class StepTarget(BaseModel):
    """A concrete, sensor-backed target. Only ever produced by
    sanitize.py — never taken as-is from the LLM."""

    kind: Literal["power", "hr", "cadence"]
    low: float
    high: float


class WorkoutStep(BaseModel):
    kind: StepKind
    name: str
    cue: str  # plain-language description, always present — the fallback
    # when no sensor backs a numeric target, and useful context even when
    # one does ("Zone 3, seated climbing effort").
    end: StepEnd
    target: StepTarget | None = None


class RepeatBlock(BaseModel):
    kind: Literal["repeat"] = "repeat"
    count: int = Field(ge=2, le=30)
    steps: list[WorkoutStep]


WorkoutItem = WorkoutStep | RepeatBlock


class Workout(BaseModel):
    name: str
    est_minutes: int
    steps: list[WorkoutItem]

    def flattened_steps(self) -> list[WorkoutStep]:
        """Every WorkoutStep in ride order, with repeats expanded — what
        export.py's device formats need; a repeated block is not a device
        concept for ZWO/MRC, only for the Garmin JSON and FIT builders,
        which handle RepeatBlock themselves."""
        out: list[WorkoutStep] = []
        for item in self.steps:
            if isinstance(item, RepeatBlock):
                out.extend(item.steps * item.count)
            else:
                out.append(item)
        return out

    def has_power_targets(self) -> bool:
        return any(s.target is not None and s.target.kind == "power" for s in self.flattened_steps())


# Assumed outdoor speed (m/s) for turning a distance-ended step into a
# rough seconds estimate — only for duration bookkeeping (the duration
# clamp, an estimated-duration display), never shown to the rider as a
# real pace or exported as one.
_ASSUMED_MPS = {"road": 7.8, "gravel": 6.4, "mtb": 5.0}
# A rider-controlled ("until the top of the climb") step's assumed length
# for the same bookkeeping purpose.
_LAP_BUTTON_SECONDS = 240.0


def estimate_step_seconds(step: WorkoutStep, discipline: str) -> float:
    if step.end.kind == "time" and step.end.seconds is not None:
        return step.end.seconds
    if step.end.kind == "distance" and step.end.meters is not None:
        return step.end.meters / _ASSUMED_MPS.get(discipline, 6.5)
    return _LAP_BUTTON_SECONDS


# --- LLM draft shapes (pre-sanitize; never persisted or exported as-is) ---


class DraftTarget(BaseModel):
    kind: Literal["power_pct_ftp", "hr_zone", "cadence_rpm", "none"]
    low: float | None = None  # % FTP low, or cadence rpm low
    high: float | None = None  # % FTP high, or cadence rpm high
    hr_zone: int | None = None  # 1-5, used when kind == "hr_zone"


class DraftStep(BaseModel):
    kind: StepKind
    name: str
    cue: str
    end: StepEnd
    target: DraftTarget


class DraftRepeatBlock(BaseModel):
    kind: Literal["repeat"] = "repeat"
    count: int
    steps: list[DraftStep]


DraftWorkoutItem = DraftStep | DraftRepeatBlock


class DraftWorkout(BaseModel):
    name: str
    est_minutes: int
    steps: list[DraftWorkoutItem]


class SessionSourceOut(BaseModel):
    """A book citation used while generating a session — same shape as
    coach.tools.SourceOut, duplicated rather than imported so training/
    never depends on coach/ (see AGENTS.md's core/adapter layering)."""

    book_id: int
    title: str
    author: str | None
    page_start: int
    page_end: int


class GeneratedSession(BaseModel):
    """The LLM's whole structured response — a draft workout plus the
    rider-facing explanation of the trade-off between their idea and the
    plan's intent."""

    workout: DraftWorkout
    rationale: str
    adjustments: str | None = None
