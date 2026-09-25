"""Builds the LLM prompt for one training session and turns the model's
draft into a sanitized, ready-to-store Workout. Same budget-check ->
call -> record_usage shape as coach/service.py's run_turn, but one
non-streamed structured call instead of a tool loop — a workout is a
single well-formed document, not a conversation.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from soft_floyd_core.bikes.service import BikeOut
from soft_floyd_core.llm.client import LLMClient
from soft_floyd_core.llm.schema import to_strict_schema
from soft_floyd_core.llm.usage import ensure_within_budget, record_usage
from soft_floyd_core.profile.service import ProfileOut
from soft_floyd_core.rag.service import Embedder, PassageOut, get_training_context
from soft_floyd_core.training.sanitize import sanitize_workout
from soft_floyd_core.training.schemas import (
    GeneratedSession,
    SessionIntent,
    SessionRequest,
    Workout,
)

_MAX_COMPLETION_TOKENS = 1500

SYSTEM_PROMPT = """\
You are a cycling coach's session planner. You are given:
- the rider's own idea for their next ride, in their words (<rider_request>)
- a deterministic read on what this session should emphasize, with the
  reasons the rider will see (<plan_intent>)
- the rider's profile and equipment
- optionally, cited training-book passages to ground your choices

Build ONE structured workout that blends the two: respect the rider's
idea (their route, their available time, their stated feel) while
leaning toward <plan_intent>'s emphasis. If the two conflict — e.g. the
rider asked for a hard session but the intent says recovery — favor the
plan's intent, keep the rider's idea's *shape* (same setting, same rough
location or effort style) but soften intensity, and say so plainly in
`adjustments`.

Rules:
- Never state a specific watt number, HR number, or bpm — targets are
  expressed abstractly: percent of FTP (a low/high range), an HR zone
  1-5, or a cadence range in rpm. The app resolves each against the
  rider's actual sensors and may drop a target entirely if the sensor
  isn't there. Every step also gets a plain-language `cue` (e.g. "hard,
  seated effort") so it still reads well if its target ends up dropped.
- An outdoor step that should end at a landmark ("until the top of the
  climb") uses end.kind = "lap_button", not a guessed time or distance.
- Keep the total workout close to the rider's available minutes.
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


def _prompt(
    request: SessionRequest,
    intent: SessionIntent,
    profile: ProfileOut,
    bike: BikeOut | None,
    passages: list[PassageOut],
) -> str:
    book_lines = "\n".join(f"- {p.title} p.{p.page_start}: {p.text[:300]}" for p in passages)
    return "\n".join(
        [
            "<rider_request>",
            f"Planned date: {request.planned_date} ({request.planned_date.strftime('%A')})",
            f"Available minutes: {request.available_minutes}",
            f"Setting: {request.setting}",
            f"Discipline: {request.discipline}",
            f"How they feel: {request.feel}",
            f"Their idea: {request.route_idea or '(none given — plan is free to choose)'}",
            "</rider_request>",
            "<plan_intent>",
            f"Emphasis: {intent.emphasis}",
            *[f"- {r}" for r in intent.reasons],
            "</plan_intent>",
            f"Goal: {profile.goal_text or 'not set'}.",
            f"Capability tier: {profile.capability_tier}.",
            _bike_line(bike),
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
) -> GeneratorResult:
    ensure_within_budget(session, budget_usd)

    query = request.route_idea.strip() or f"{intent.emphasis} {request.discipline} training"
    passages: list[PassageOut] = []
    try:
        context = await get_training_context(session, query, embedder)
        passages = context.passages
    except ValueError:
        pass  # no OpenAI key for book search — plan without citations

    schema = to_strict_schema(GeneratedSession)
    raw, usage = await llm.chat_structured(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _prompt(request, intent, profile, bike, passages)},
        ],
        "training_session",
        schema,
        max_completion_tokens=_MAX_COMPLETION_TOKENS,
        temperature=0.4,
    )
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
