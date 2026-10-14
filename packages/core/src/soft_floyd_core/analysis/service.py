"""On-demand AI summary of one ride — exec-plan 0023.

Same budget-check -> call -> record_usage shape as training/generator.py.
The numbers come from `analysis/metrics.py` (sensor-gated, deterministic);
the model only writes the narrative from them. The result is stored per ride
so reopening it costs nothing, and `regenerate` replaces it.
"""

from __future__ import annotations

import datetime as dt
import re
import statistics
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.activities.service import available_metrics_for_activity
from soft_floyd_core.analysis.metrics import RideMetricsOut, RideRecords, compute_ride_metrics
from soft_floyd_core.llm.client import IncompleteResponseError, LLMClient
from soft_floyd_core.llm.schema import to_strict_schema
from soft_floyd_core.llm.usage import ensure_within_budget, record_usage
from soft_floyd_core.metrics.service import get_training_load
from soft_floyd_core.metrics.zones import resolve_lthr
from soft_floyd_core.models import Activity, Lap, Record, RideAnalysis
from soft_floyd_core.profile.service import get_profile
from soft_floyd_core.rag.service import ride_context

Language = Literal["en", "es"]
_LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}
_MAX_COMPLETION_TOKENS = 1500
_COMPARISON_RIDES = 8

# Any "<number> W" / "<number> watts" in text for a ride with no verified power.
_WATT_FIGURE = re.compile(r"\d\s*(?:w|watts?|vatios?)\b", re.IGNORECASE)

SYSTEM_PROMPT = """\
You are Soft Floyd, a personal cycling coach, reviewing ONE finished ride for
the rider. You are given deterministic facts about the ride (<ride_facts>),
how it compares with the rider's recent rides of the same type
(<recent_comparison>), the rider's goal, and optionally their training load.

Write a short, honest, encouraging review in the requested language:
- `headline`: one sentence capturing what this ride was.
- `went_well`: 2-3 specific things the data supports.
- `to_improve`: 1-3 specific, actionable things, tied to the rider's goal
  where it fits. Say so plainly if there is little to improve.
- `next_time`: one concrete thing to try on the next similar ride.
- `data_caveat`: null unless data was missing or thin in a way that limits
  the review (say what is missing); one sentence.

DATA HONESTY — non-negotiable:
- Use only numbers that appear in the facts. Never compute, estimate or
  invent a new figure, and never infer power from speed or heart rate.
- If <ride_facts> has no power, do not mention watts, NP, FTP, TSS or
  intensity factor at all. If it has no heart rate, do not mention HR.
- Treat comparisons and trends with caution when the history is short.
- HR drift and lap variation are context, not verdicts: a hilly or
  interval ride is expected to vary.
- You are not a doctor; do not make medical claims.
"""


class RideAnalysisDraft(BaseModel):
    headline: str = Field(max_length=300)
    went_well: list[str] = Field(max_length=4)
    to_improve: list[str] = Field(max_length=4)
    next_time: str = Field(max_length=400)
    data_caveat: str | None


class RideAnalysisOut(BaseModel):
    activity_id: int
    language: str | None
    analysis: RideAnalysisDraft | None
    generated_at: dt.datetime | None
    metrics: RideMetricsOut


class ActivityNotFoundError(Exception):
    pass


class AnalysisRejectedError(Exception):
    """The model broke the sensor rule (e.g. watts on a ride with no power)."""


def make_analysis_llm(api_key: str | None) -> LLMClient | None:
    """Monkeypatch seam for adapter tests; a missing key becomes None."""
    return LLMClient(api_key) if api_key else None


def _records(session: Session, activity: Activity) -> RideRecords | None:
    if not activity.records_stored:
        return None
    rows = session.execute(
        select(Record.t_offset_s, Record.power_w, Record.hr)
        .where(Record.activity_id == activity.id)
        .order_by(Record.t_offset_s)
    ).all()
    if not rows:
        return None
    return RideRecords([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows])


def _metrics(session: Session, activity: Activity) -> RideMetricsOut:
    profile = get_profile(session)
    laps = session.scalars(
        select(Lap).where(Lap.activity_id == activity.id).order_by(Lap.lap_index)
    ).all()
    return compute_ride_metrics(
        activity,
        laps,
        _records(session, activity),
        allowed=available_metrics_for_activity(session, activity),
        ftp_watts=profile.ftp_watts or None,
        lthr=resolve_lthr(profile.lthr, profile.max_hr),
    )


def _get_activity(session: Session, activity_id: int) -> Activity:
    activity = session.get(Activity, activity_id)
    if activity is None:
        raise ActivityNotFoundError(activity_id)
    return activity


def get_ride_analysis(session: Session, activity_id: int) -> RideAnalysisOut:
    """The stored analysis (if any) beside freshly computed metrics."""
    activity = _get_activity(session, activity_id)
    row = session.scalar(select(RideAnalysis).where(RideAnalysis.activity_id == activity_id))
    return RideAnalysisOut(
        activity_id=activity_id,
        language=row.language if row else None,
        analysis=RideAnalysisDraft.model_validate(row.draft) if row else None,
        generated_at=row.updated_at if row else None,
        metrics=_metrics(session, activity),
    )


def _comparison_lines(session: Session, activity: Activity) -> list[str]:
    previous = session.scalars(
        select(Activity)
        .where(
            Activity.bike_type == activity.bike_type,
            Activity.start_time < activity.start_time,
            Activity.id != activity.id,
        )
        .order_by(Activity.start_time.desc())
        .limit(_COMPARISON_RIDES)
    ).all()
    if not previous:
        return ["No earlier rides of this type to compare with."]
    contexts = [ride_context(session, ride) for ride in previous]

    def avg(values: list[float]) -> float | None:
        return statistics.fmean(values) if values else None

    lines = [
        f"Average of the previous {len(contexts)} {activity.bike_type} ride(s): "
        f"{statistics.fmean(c.duration_s for c in contexts) / 60:.0f} min, "
        f"{statistics.fmean(c.distance_m for c in contexts) / 1000:.1f} km, "
        f"{statistics.fmean(c.elev_gain_m for c in contexts):.0f} m climbing."
    ]
    hr = avg([c.avg_hr for c in contexts if c.avg_hr is not None])
    power = avg([c.avg_power_w for c in contexts if c.avg_power_w is not None])
    if hr is not None:
        lines.append(f"Their average HR (rides with verified HR): {hr:.0f} bpm.")
    if power is not None:
        lines.append(f"Their average power (rides with verified power): {power:.0f} W.")
    return lines


def _fact_lines(m: RideMetricsOut) -> list[str]:
    lines = [
        f"Duration {m.duration_s / 60:.0f} min, distance {m.distance_km} km, "
        f"climbing {m.elev_gain_m:.0f} m"
        + (f" ({m.climb_m_per_km} m/km)" if m.climb_m_per_km is not None else "")
        + ".",
        f"Verified sensors: {', '.join(m.sensors_present) or 'none'}.",
    ]
    if m.avg_speed_kmh is not None:
        lines.append(f"Average speed {m.avg_speed_kmh} km/h.")
    if m.avg_power_w is not None:
        lines.append(f"Average power {m.avg_power_w} W, max {m.max_power_w} W.")
    if m.normalized_power_w is not None:
        lines.append(f"Normalized power {m.normalized_power_w} W.")
    if m.variability_index is not None:
        lines.append(f"Variability index {m.variability_index}.")
    if m.intensity_factor is not None:
        lines.append(f"Intensity factor {m.intensity_factor}, TSS {m.tss:.0f}.")
    if m.avg_hr is not None:
        lines.append(f"Average HR {m.avg_hr} bpm, max {m.max_hr} bpm.")
    if m.hr_zone_minutes:
        zones = ", ".join(f"Z{z} {mins} min" for z, mins in m.hr_zone_minutes.items())
        lines.append(f"Time in HR zones: {zones}.")
    if m.hr_drift_pct is not None:
        lines.append(f"HR drift (2nd half vs 1st half): {m.hr_drift_pct:+.1f}%.")
    if m.load is not None:
        lines.append(f"Ride load {m.load:.0f} (basis: {m.load_basis}).")
    if m.lap_variation_pct is not None:
        lines.append(
            f"{m.lap_count} laps; {m.lap_variation_basis} varied "
            f"{m.lap_variation_pct}% across laps."
        )
    lines.extend(f"Note: {n}" for n in m.notes)
    return lines


def _prompt(session: Session, activity: Activity, metrics: RideMetricsOut, language: str) -> str:
    profile = get_profile(session)
    load = get_training_load(session)
    lines = [
        f"Reply in {_LANGUAGE_NAMES[language]}.",
        f"Ride date: {activity.start_time.date()}. Setting: "
        f"{'indoor' if activity.is_indoor else 'outdoor'}. Type: {activity.bike_type}.",
        "<ride_facts>",
        *_fact_lines(metrics),
        "</ride_facts>",
        "<recent_comparison>",
        *_comparison_lines(session, activity),
        "</recent_comparison>",
        f"Rider goal: {profile.goal_text or 'not set'}.",
    ]
    if profile.focus_areas:
        lines.append(f"Focus areas: {', '.join(profile.focus_areas)}.")
    if load.confidence == "ok":
        lines.append(
            f"Training load: fitness {load.ctl:.0f}, fatigue {load.atl:.0f}, "
            f"form {load.tsb:+.0f} ({load.form})."
        )
    return "\n".join(lines)


def _text_of(draft: RideAnalysisDraft) -> list[str]:
    return [
        draft.headline,
        *draft.went_well,
        *draft.to_improve,
        draft.next_time,
        draft.data_caveat or "",
    ]


async def analyze_ride(
    session: Session,
    llm: LLMClient,
    activity_id: int,
    *,
    language: Language = "en",
    budget_usd: float,
    regenerate: bool = False,
) -> RideAnalysisOut:
    activity = _get_activity(session, activity_id)
    row = session.scalar(select(RideAnalysis).where(RideAnalysis.activity_id == activity_id))
    if row is not None and not regenerate:
        return get_ride_analysis(session, activity_id)

    ensure_within_budget(session, budget_usd)
    metrics = _metrics(session, activity)
    try:
        raw, usage = await llm.chat_structured(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _prompt(session, activity, metrics, language)},
            ],
            "ride_analysis",
            to_strict_schema(RideAnalysisDraft),
            max_completion_tokens=_MAX_COMPLETION_TOKENS,
        )
    except IncompleteResponseError as exc:
        if exc.usage:
            record_usage(session, exc.usage)
            session.commit()  # the spend is real even though the request errors out
        raise
    record_usage(session, usage)
    session.commit()  # kept even if the guard below rejects the draft

    draft = RideAnalysisDraft.model_validate(raw)
    if "power" not in metrics.sensors_present and any(
        _WATT_FIGURE.search(text) for text in _text_of(draft)
    ):
        raise AnalysisRejectedError("The analysis mentioned power on a ride without power data.")

    if row is None:
        row = RideAnalysis(activity_id=activity_id)
        session.add(row)
    row.language = language
    row.draft = draft.model_dump()
    row.metrics_snapshot = metrics.model_dump()
    row.updated_at = dt.datetime.now(dt.UTC)
    session.flush()
    return get_ride_analysis(session, activity_id)
