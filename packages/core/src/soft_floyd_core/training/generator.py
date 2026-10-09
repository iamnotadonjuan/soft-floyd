"""Builds the LLM prompt for one training session and turns the model's
draft into a sanitized, ready-to-store Workout. Same budget-check ->
call -> record_usage shape as coach/service.py's run_turn, but one
non-streamed structured call instead of a tool loop — a workout is a
single well-formed document, not a conversation.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.orm import Session

from soft_floyd_core.bikes.service import BikeOut
from soft_floyd_core.llm.client import IncompleteResponseError, LLMClient
from soft_floyd_core.llm.schema import to_strict_schema
from soft_floyd_core.llm.usage import ensure_within_budget, record_usage
from soft_floyd_core.metrics.service import TrainingLoadOut
from soft_floyd_core.profile.service import ProfileOut
from soft_floyd_core.rag.service import Embedder, PassageOut, RideContextOut, get_training_context
from soft_floyd_core.training.sanitize import sanitize_workout
from soft_floyd_core.training.schemas import (
    GeneratedSession,
    SessionIntent,
    SessionRequest,
    Workout,
)

_MAX_COMPLETION_TOKENS = 4000

SYSTEM_PROMPT = """\
You are a cycling coach's session planner. You are given:
- the rider's own idea for their next ride, in their words (<rider_request>)
- a deterministic read on what this session should emphasize, with the
  reasons the rider will see (<plan_intent>)
- the rider's profile and equipment
- optionally, their current training load (<training_load>): fitness,
  fatigue and form. It is context for your rationale, already reflected in
  <plan_intent>; you may mention it in plain words but never invent load
  figures of your own
- optionally, cited training-book passages to ground your choices
- optionally, a verified digest of recent rides and rider-provided outdoor
  area, terrain and approximate starting altitude

Build ONE structured workout that blends the two: respect the rider's
idea (their route, their available time, their stated feel) while
leaning toward <plan_intent>'s emphasis. If the two conflict — e.g. the
rider asked for a hard session but the intent says recovery — favor the
plan's intent, keep the rider's idea's *shape* (same setting, same rough
location or effort style) but soften intensity, and say so plainly in
`adjustments`.

Rules:
- Choose each step's effort from the rider's request, plan intent, trusted
  training load and verified recent rides. Recovery, steady work and hard
  intervals should have different targets when their intended effort
  differs. Recent averages are context, not a new FTP or threshold test.
- Never state a specific watt or HR number in the draft. For a power-capable
  bike with saved FTP, normally choose each effort step's own percent-of-FTP
  low/high range. Choose an HR zone instead when the rider explicitly asks
  to train by HR. For a power target, provide `fallback_hr_zone` when HR
  with LTHR is available and a matching HR effort makes sense. Without
  usable power, choose an HR zone 1-5 when available. Use cadence rpm only
  for a cadence-specific drill with a cadence sensor; it is not an effort
  replacement. Never create a speed target from terrain or route. Set
  kind=none for steps that should have no device alert.
- Every step gets a plain-language `cue` describing its effort even if it
  also has a numeric target; it must still work if that target is dropped.
- An outdoor step that should end at a landmark ("until the top of the
  climb") uses end.kind = "lap_button", not a guessed time or distance.
- Keep the total workout close to the rider's available minutes.
- Use the supplied terrain to choose a feasible workout shape. A place name
  does not prove there is a hill or a route. Starting altitude is approximate;
  use it as qualitative context, never claim a precise physiological effect.
- `rationale` is 2-4 sentences in a coach's voice: reflect plan_intent's
  reasons in your own words. Never state a metric the rider hasn't been
  shown, and never claim a sensor reading you don't have.
- `adjustments` is null unless you changed something material about what
  the rider asked for; if set, name the change and why in one sentence.
"""


@dataclass(frozen=True)
class GeneratorResult:
    workout: Workout
    rationale: str
    adjustments: str | None
    passages: list[PassageOut]


class RestDraft(BaseModel):
    rationale: str


@dataclass(frozen=True)
class RestResult:
    rationale: str
    passages: list[PassageOut]


def _bike_line(bike: BikeOut | None) -> str:
    if bike is None:
        return "No matching bike in the garage — assume no bike-mounted sensors."
    sensors = (
        ", ".join(
            name
            for name, present in (
                ("power meter", bike.has_power_meter),
                ("cadence sensor", bike.has_cadence_sensor),
                ("speed sensor", bike.has_speed_sensor),
            )
            if present
        )
        or "no bike-mounted sensors"
    )
    return f"Bike: {bike.nickname or bike.kind} ({bike.kind}), {sensors}."


def _target_capabilities_line(profile: ProfileOut, bike: BikeOut | None) -> str:
    available = []
    if bike and bike.has_power_meter and profile.ftp_watts:
        available.append(f"power using saved FTP {profile.ftp_watts} W")
    if profile.has_hr_monitor and profile.lthr:
        available.append(f"HR using saved LTHR {profile.lthr} bpm")
    if bike and bike.has_cadence_sensor:
        available.append("cadence for cadence drills")
    return (
        "Workout targets available on this bike: "
        + ", ".join(available or ["plain-language effort cues only"])
        + "."
    )


def _load_lines(load: TrainingLoadOut | None) -> list[str]:
    # Below "ok" confidence the numbers are too shaky to hand the model.
    if load is None or load.confidence != "ok":
        return []
    return [
        "<training_load>",
        f"Fitness {load.ctl:.0f}, fatigue {load.atl:.0f}, form {load.tsb:+.0f} ({load.form}); "
        f"fitness changed {load.ramp_rate_7d:+.1f} over the last 7 days.",
        *[f"- {n}" for n in load.notes],
        "</training_load>",
    ]


def _ride_lines(rides: list[RideContextOut]) -> list[str]:
    if not rides:
        return ["<recent_rides>", "No synced rides available.", "</recent_rides>"]
    lines = ["<recent_rides>"]
    for ride in rides:
        metrics = [
            f"{ride.duration_s / 60:.0f} min",
            f"{ride.distance_m / 1000:.1f} km",
            f"{ride.elev_gain_m:.0f} m climbing",
        ]
        if ride.avg_hr is not None:
            metrics.append(f"recorded average HR {ride.avg_hr} bpm")
        if ride.avg_power_w is not None:
            metrics.append(f"recorded average power {ride.avg_power_w} W")
        if ride.avg_cadence is not None:
            metrics.append(f"recorded average cadence {ride.avg_cadence} rpm")
        lines.append(f"- {ride.start_time[:10]}: {', '.join(metrics)}.")
        if ride.data_note:
            lines.append(f"  {ride.data_note}")
    return [*lines, "</recent_rides>"]


def _prompt(
    request: SessionRequest,
    intent: SessionIntent,
    profile: ProfileOut,
    bike: BikeOut | None,
    passages: list[PassageOut],
    load: TrainingLoadOut | None = None,
    rides: list[RideContextOut] | None = None,
) -> str:
    book_lines = "\n".join(f"- {p.title} p.{p.page_start}: {p.text[:300]}" for p in passages)
    altitude = (
        f"{request.starting_altitude_m} m"
        if request.starting_altitude_m is not None
        else "(not provided)"
    )
    return "\n".join(
        [
            "<rider_request>",
            f"Planned date: {request.planned_date} ({request.planned_date.strftime('%A')})",
            f"Available minutes: {request.available_minutes}",
            f"Setting: {request.setting}",
            f"Discipline: {request.discipline}",
            f"How they feel: {request.feel}",
            f"Their idea: {request.route_idea or '(none given — plan is free to choose)'}",
            f"Training area: {request.training_area or '(not provided)'}",
            f"Terrain: {request.terrain or '(not provided)'}",
            f"Approximate starting altitude: {altitude}",
            "</rider_request>",
            "<plan_intent>",
            f"Emphasis: {intent.emphasis}",
            *[f"- {r}" for r in intent.reasons],
            "</plan_intent>",
            *_load_lines(load),
            *(_ride_lines(rides) if rides is not None else []),
            f"Goal: {profile.goal_text or 'not set'}.",
            f"Capability tier: {profile.capability_tier}.",
            _bike_line(bike),
            _target_capabilities_line(profile, bike),
            *(["Book passages (you may reflect these loosely):", book_lines] if passages else []),
        ]
    )


async def generate_session(
    session: Session,
    llm: LLMClient,
    embedder: Embedder | None,
    *,
    request: SessionRequest,
    intent: SessionIntent,
    profile: ProfileOut,
    bike: BikeOut | None,
    budget_usd: float,
    load: TrainingLoadOut | None = None,
    rides: list[RideContextOut] | None = None,
) -> GeneratorResult:
    ensure_within_budget(session, budget_usd)

    query = request.route_idea.strip() or (
        f"{intent.emphasis} {request.terrain or ''} {request.discipline} training"
    )
    passages: list[PassageOut] = []
    try:
        context = await get_training_context(session, query, embedder)
        passages = context.passages
    except ValueError:
        pass  # no OpenAI key for book search — plan without citations

    schema = to_strict_schema(GeneratedSession)
    try:
        raw, usage = await llm.chat_structured(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _prompt(request, intent, profile, bike, passages, load, rides),
                },
            ],
            "training_session",
            schema,
            max_completion_tokens=_MAX_COMPLETION_TOKENS,
        )
    except IncompleteResponseError as exc:
        if exc.usage:
            record_usage(session, exc.usage)
        raise
    record_usage(session, usage)

    generated = GeneratedSession.model_validate(raw)
    workout = sanitize_workout(
        generated.workout,
        profile=profile,
        bike=bike,
        discipline=request.discipline,
        available_minutes=request.available_minutes,
    )
    return GeneratorResult(
        workout=workout,
        rationale=generated.rationale,
        adjustments=generated.adjustments,
        passages=passages,
    )


async def generate_rest_explanation(
    session: Session,
    llm: LLMClient,
    embedder: Embedder | None,
    *,
    request: SessionRequest,
    intent: SessionIntent,
    profile: ProfileOut,
    rides: list[RideContextOut],
    load: TrainingLoadOut | None,
    budget_usd: float,
) -> RestResult:
    ensure_within_budget(session, budget_usd)
    passages: list[PassageOut] = []
    try:
        context = await get_training_context(
            session, "cycling rest recovery after training load", embedder
        )
        passages = context.passages
    except ValueError:
        pass

    try:
        raw, usage = await llm.chat_structured(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a cycling coach. The app has already decided that a rest day is "
                        "appropriate. Explain that choice in 2-4 plain sentences using only the "
                        "verified ride facts and trusted load shown. Mention uncertainty when "
                        "history is short or a ride lacks sensor data. You may use a relevant "
                        "supplied book "
                        "passage, but do not invent a citation, physiological measurement, route, "
                        "or medical claim. Do not prescribe a workout."
                    ),
                },
                {
                    "role": "user",
                    "content": _prompt(request, intent, profile, None, passages, load, rides),
                },
            ],
            "rest_recommendation",
            to_strict_schema(RestDraft),
            max_completion_tokens=1200,
        )
    except IncompleteResponseError as exc:
        if exc.usage:
            record_usage(session, exc.usage)
        raise
    record_usage(session, usage)
    return RestResult(rationale=RestDraft.model_validate(raw).rationale, passages=passages)
