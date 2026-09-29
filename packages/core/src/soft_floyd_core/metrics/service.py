"""Fitness / fatigue / form from the rider's own rides — exec-plan 0012.

Both `mcp_server.py` and `http_api.py` (and the coach tool) call
`get_training_load` directly. Each ride is scored by `metrics/load.py`
from the best stream that *ride's own* FIT data verified, using the same
per-ride gate as `get_training_summary` (`available_metrics_for_activity`);
then daily loads feed two exponentially-weighted averages:

- CTL, "fitness": 42-day time constant
- ATL, "fatigue": 7-day time constant
- TSB, "form": CTL - ATL

Nothing is stored — it is recomputed from `activity` (and `record`, for NP
and time-in-zone) on demand. See exec-plan 0012 for when that stops being
good enough.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.activities.service import available_metrics_for_activity
from soft_floyd_core.metrics.load import Basis, RideLoadInput, ride_load
from soft_floyd_core.metrics.zones import resolve_lthr
from soft_floyd_core.models import Activity, Record
from soft_floyd_core.profile.service import get_profile

CTL_DAYS = 42
ATL_DAYS = 7
# How far back rides are read. CTL starts from zero at the first ride in
# this window, so `days_of_history` (capped by this) tells consumers how
# far to trust it.
LOOKBACK_DAYS = 180
MIN_HISTORY_DAYS = 21  # below this, `confidence` is "low"
FULL_HISTORY_DAYS = 42  # from this, "ok"
# TSB cut-offs for the plain-language form label.
FRESH_TSB = 5.0
TIRED_TSB = -10.0
VERY_TIRED_TSB = -30.0
# Share of the last CTL_DAYS of load that is duration-only before we say so.
ESTIMATED_SHARE_NOTE = 0.5

Confidence = Literal["low", "partial", "ok"]
Form = Literal["fresh", "neutral", "tired", "very tired"]


class DayLoadOut(BaseModel):
    date: dt.date
    load: float
    ctl: float
    atl: float
    tsb: float


class TrainingLoadOut(BaseModel):
    as_of: dt.date
    ctl: float
    atl: float
    tsb: float
    form: Form
    ramp_rate_7d: float  # CTL today minus CTL a week ago
    days_of_history: int
    confidence: Confidence
    basis_counts: dict[str, int]  # rides per basis in the lookback window
    series: list[DayLoadOut]  # oldest first, ending today
    notes: list[str]


def form_label(tsb: float) -> Form:
    if tsb >= FRESH_TSB:
        return "fresh"
    if tsb >= TIRED_TSB:
        return "neutral"
    if tsb >= VERY_TIRED_TSB:
        return "tired"
    return "very tired"


def _confidence(days_of_history: int) -> Confidence:
    if days_of_history >= FULL_HISTORY_DAYS:
        return "ok"
    if days_of_history >= MIN_HISTORY_DAYS:
        return "partial"
    return "low"


def _ewma(previous: float, load: float, days: int) -> float:
    alpha = 1.0 - math.exp(-1.0 / days)
    return previous + (load - previous) * alpha


def _records(
    session: Session, ride: Activity
) -> tuple[list[float], list[int | None], list[int | None]] | None:
    if not ride.records_stored:
        return None
    rows = session.execute(
        select(Record.t_offset_s, Record.power_w, Record.hr)
        .where(Record.activity_id == ride.id)
        .order_by(Record.t_offset_s)
    ).all()
    if not rows:
        return None
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]


def get_training_load(
    session: Session, days: int = 56, now: dt.datetime | None = None
) -> TrainingLoadOut:
    """Load for the last `days` days (clamped to 7..LOOKBACK_DAYS), ending
    today. CTL/ATL are computed over the whole lookback window so the
    returned days aren't cold starts."""
    days = max(7, min(days, LOOKBACK_DAYS))
    today = (now or dt.datetime.now(dt.UTC)).date()
    window_start = today - dt.timedelta(days=LOOKBACK_DAYS - 1)

    profile = get_profile(session)
    ftp = profile.ftp_watts or None
    lthr = resolve_lthr(profile.lthr, profile.max_hr)

    rides = session.scalars(
        select(Activity)
        .where(Activity.start_time >= dt.datetime.combine(window_start, dt.time()))
        .order_by(Activity.start_time)
    ).all()

    daily: dict[dt.date, float] = {}
    load_by_basis: dict[dt.date, dict[Basis, float]] = {}
    basis_counts: Counter[str] = Counter()
    power_without_ftp = 0
    hr_without_lthr = 0
    for ride in rides:
        allowed = available_metrics_for_activity(session, ride)
        power_verified = bool(ride.has_power_data and "training_stress_score" in allowed)
        hr_verified = bool(ride.has_hr_data and "hr_zones" in allowed)
        power_without_ftp += power_verified and not ftp
        hr_without_lthr += hr_verified and not lthr

        records = _records(session, ride) if (power_verified or hr_verified) else None
        result = ride_load(
            RideLoadInput(
                duration_s=ride.duration_s,
                power_verified=power_verified,
                hr_verified=hr_verified,
                avg_power_w=ride.avg_power_w,
                avg_hr=ride.avg_hr,
                t_offset_s=records[0] if records else None,
                power_w=records[1] if records else None,
                hr=records[2] if records else None,
            ),
            ftp_watts=ftp,
            lthr=lthr,
        )
        day = ride.start_time.date()
        daily[day] = daily.get(day, 0.0) + result.load
        by_basis = load_by_basis.setdefault(day, {})
        by_basis[result.basis] = by_basis.get(result.basis, 0.0) + result.load
        basis_counts[result.basis] += 1

    first_ride_day = min(daily) if daily else today
    days_of_history = (today - first_ride_day).days + 1 if daily else 0

    start = min(first_ride_day, today - dt.timedelta(days=days - 1))
    ctl = atl = 0.0
    series: list[DayLoadOut] = []
    day = start
    while day <= today:
        load = daily.get(day, 0.0)
        ctl = _ewma(ctl, load, CTL_DAYS)
        atl = _ewma(atl, load, ATL_DAYS)
        series.append(
            DayLoadOut(
                date=day,
                load=round(load, 1),
                ctl=round(ctl, 1),
                atl=round(atl, 1),
                tsb=round(ctl - atl, 1),
            )
        )
        day += dt.timedelta(days=1)

    ramp_base = series[-8].ctl if len(series) >= 8 else 0.0
    latest = series[-1]
    notes = _notes(
        load_by_basis,
        today=today,
        days_of_history=days_of_history,
        power_without_ftp=power_without_ftp,
        hr_without_lthr=hr_without_lthr,
    )
    return TrainingLoadOut(
        as_of=today,
        ctl=latest.ctl,
        atl=latest.atl,
        tsb=latest.tsb,
        form=form_label(latest.tsb),
        ramp_rate_7d=round(latest.ctl - ramp_base, 1),
        days_of_history=days_of_history,
        confidence=_confidence(days_of_history),
        basis_counts=dict(basis_counts),
        series=series[-days:],
        notes=notes,
    )


def _notes(
    load_by_basis: dict[dt.date, dict[Basis, float]],
    *,
    today: dt.date,
    days_of_history: int,
    power_without_ftp: int,
    hr_without_lthr: int,
) -> list[str]:
    notes: list[str] = []
    if days_of_history == 0:
        return ["No rides synced yet, so there is no training load to compute."]
    if days_of_history < FULL_HISTORY_DAYS:
        notes.append(
            f"Only {days_of_history} day(s) of ride history — fitness and form become "
            f"reliable after about {FULL_HISTORY_DAYS} days."
        )
    cutoff = today - dt.timedelta(days=CTL_DAYS - 1)
    recent = [(d, b) for d, b in load_by_basis.items() if d >= cutoff]
    total = sum(v for _, b in recent for v in b.values())
    estimated = sum(b.get("duration", 0.0) for _, b in recent)
    if total > 0 and estimated / total >= ESTIMATED_SHARE_NOTE:
        notes.append(
            f"{round(estimated / total * 100)}% of your recent load is estimated from ride "
            "duration, not measured."
        )
    if power_without_ftp:
        notes.append(
            f"{power_without_ftp} ride(s) have power data but no FTP is set, so they were not "
            "scored from power. Set your FTP for better numbers."
        )
    if hr_without_lthr:
        notes.append(
            f"{hr_without_lthr} ride(s) have heart-rate data but no LTHR or max HR is set, so "
            "they were not scored from heart rate."
        )
    return notes
