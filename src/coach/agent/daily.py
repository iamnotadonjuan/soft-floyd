"""Daily readiness summary generation for Soft Floyd (Phase 4)."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import openai

from coach.agent.profile import build_profile_summary
from coach.log import log
from coach.store.models import Activity, DailySummary, WellnessDaily
from coach.web.cost import calculate_cost

if TYPE_CHECKING:
    from coach.config import Config

_DAILY_SYSTEM_MD = Path(__file__).parent / "prompts" / "daily_system.md"
_MODEL = "gpt-4.1-mini"
_MAX_TOKENS = 350


def build_daily_context(session, date: datetime.date) -> str:
    """Compose the user message for the daily readiness call."""
    from sqlalchemy import select

    # Wellness row for the target date — use PK lookup (get) to avoid
    # DateTime vs. date comparison mismatch on SQLite.
    wellness_row = session.get(WellnessDaily, date)

    # Last 7 days of activities for load context
    cutoff = datetime.datetime.combine(
        date - datetime.timedelta(days=7),
        datetime.time.min,
        datetime.UTC,
    )
    activities = list(
        session.execute(
            select(Activity)
            .where(Activity.start_time >= cutoff)
            .order_by(Activity.start_time.desc())
            .limit(7)
        ).scalars()
    )

    profile_text = build_profile_summary(session) or "(no rider profile set)"

    lines = [
        f"## Date: {date}",
        f"## Rider Profile\n{profile_text}",
    ]

    if wellness_row:
        lines.append(
            "## Today's Wellness\n"
            f"HRV overnight: {wellness_row.hrv_overnight}, "
            f"Sleep score: {wellness_row.sleep_score}, "
            f"RHR: {wellness_row.resting_hr} bpm, "
            f"Body Battery: {wellness_row.body_battery_low}→{wellness_row.body_battery_high}, "
            f"ACWR: {wellness_row.acwr}"
        )
    else:
        lines.append("## Today's Wellness\n(no data available for today)")

    if activities:
        load_lines = [
            f"- {a.start_time.date()} | {a.bike_type} | "
            f"{round(a.duration_s / 60)}min | "
            f"TSS-proxy={round(a.tss_proxy, 1) if a.tss_proxy else '?'}"
            for a in activities
        ]
        lines.append("## Recent Load (last 7 days)\n" + "\n".join(load_lines))
    else:
        lines.append("## Recent Load (last 7 days)\n(no activities)")

    return "\n\n".join(lines)


async def generate_daily_summary(session, cfg: Config, date: datetime.date) -> DailySummary:
    """Generate (or regenerate) the daily readiness summary for the given date.

    Upserts a DailySummary row and returns it.
    """
    from sqlalchemy import select

    client = openai.AsyncOpenAI(api_key=cfg.openai_api_key)
    system = _DAILY_SYSTEM_MD.read_text(encoding="utf-8")
    user_content = build_daily_context(session, date)

    response = await client.chat.completions.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        stream=False,
    )

    text = (response.choices[0].message.content or "").strip()
    usage = response.usage

    # Extract token counts (same shape as the main coach)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    cache_read = getattr(details, "cached_tokens", 0) or 0
    uncached = prompt_tokens - cache_read
    cost = calculate_cost(uncached, tokens_out, cache_read)

    # Upsert the row for this date
    row = session.execute(
        select(DailySummary).where(DailySummary.date == date)
    ).scalar_one_or_none()
    if row is None:
        row = DailySummary(date=date)
        session.add(row)

    row.text = text
    row.tokens_in = prompt_tokens
    row.tokens_out = tokens_out
    row.cache_read = cache_read
    row.cost_usd = float(cost)
    row.generated_at = datetime.datetime.now(datetime.UTC)
    session.commit()

    log.info("daily_summary.generated", date=str(date), cost_usd=float(cost))
    return row
