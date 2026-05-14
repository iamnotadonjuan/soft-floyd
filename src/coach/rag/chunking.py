"""Build deterministic text cards for embedding and RAG context."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coach.store.models import Activity, Lap, Metrics, WellnessDaily


def _fmt_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h{m:02d}" if h else f"{m}min"


def _fmt_dist(meters: float) -> str:
    return f"{meters / 1000:.1f} km"


def _zone_pct(metrics: Metrics | None) -> str:
    if metrics is None:
        return "no zone data"
    total = sum(
        v or 0
        for v in [
            metrics.time_in_z1,
            metrics.time_in_z2,
            metrics.time_in_z3,
            metrics.time_in_z4,
            metrics.time_in_z5,
        ]
    )
    if total <= 0:
        return "no zone data"

    def pct(v: float | None) -> int:
        return round((v or 0) / total * 100)

    return (
        f"Z1 {pct(metrics.time_in_z1)}%"
        f" Z2 {pct(metrics.time_in_z2)}%"
        f" Z3 {pct(metrics.time_in_z3)}%"
        f" Z4 {pct(metrics.time_in_z4)}%"
        f" Z5 {pct(metrics.time_in_z5)}%"
    )


def _aerobic_quality(metrics: Metrics | None) -> str:
    if metrics is None:
        return ""
    parts = []
    if metrics.decoupling_pct is not None:
        quality = "good aerobic stability" if metrics.decoupling_pct < 5 else "some aerobic drift"
        parts.append(f"Decoupling {metrics.decoupling_pct:.1f}% ({quality}).")
    if metrics.hr_drift_pct is not None:
        parts.append(f"HR drift {metrics.hr_drift_pct:.1f}%.")
    return " ".join(parts)


def _narrative(activity: Activity, metrics: Metrics | None) -> str:
    bike = activity.bike_type
    if metrics is None:
        return f"{bike} ride — no detailed metrics available."

    total = sum(
        v or 0
        for v in [
            metrics.time_in_z1,
            metrics.time_in_z2,
            metrics.time_in_z3,
            metrics.time_in_z4,
            metrics.time_in_z5,
        ]
    )
    z2_pct = (metrics.time_in_z2 or 0) / total * 100 if total > 0 else 0
    z4z5_pct = (
        ((metrics.time_in_z4 or 0) + (metrics.time_in_z5 or 0)) / total * 100 if total > 0 else 0
    )

    if bike == "indoor":
        if z2_pct >= 60:
            return "Indoor Z2 base session — disciplined aerobic work."
        return f"Indoor session with {z4z5_pct:.0f}% high-intensity time."
    if bike == "mtb":
        return f"MTB ride — naturally variable HR with {z4z5_pct:.0f}% high-intensity."
    # road or other
    if z2_pct >= 65:
        return f"Steady Z2 endurance — {z2_pct:.0f}% aerobic base work."
    if z4z5_pct >= 20:
        return f"High-intensity road effort with {z4z5_pct:.0f}% threshold/VO2max time."
    return "Mixed-intensity road ride."


def build_activity_card(
    activity: Activity,
    laps: list[Lap],
    metrics: Metrics | None,
    wellness: WellnessDaily | None,
) -> str:
    """Return a deterministic ~300-token text card for a single activity."""
    date_str = activity.start_time.strftime("%Y-%m-%d")
    header = (
        f"{date_str} | {activity.bike_type} | "
        f"{_fmt_dist(activity.distance_m)} / {_fmt_duration(activity.duration_s)} / "
        f"{activity.elev_gain_m:.0f} m gain"
    )

    hr_line = ""
    if activity.avg_hr or activity.max_hr:
        avg = activity.avg_hr or "?"
        mx = activity.max_hr or "?"
        hr_line = f"HR avg/max: {avg}/{mx} — {_zone_pct(metrics)}"

    aerobic_line = _aerobic_quality(metrics)

    vam_line = ""
    if metrics and metrics.vam_best_20min:
        vam_line = f"Top climb: VAM {metrics.vam_best_20min:.0f} m/h (best 20-min window)."

    wellness_line = ""
    if wellness:
        parts = []
        if wellness.hrv_overnight is not None:
            parts.append(f"HRV {wellness.hrv_overnight:.0f}")
        if wellness.sleep_score is not None:
            parts.append(f"sleep score {wellness.sleep_score}")
        if wellness.body_battery_low is not None and wellness.body_battery_high is not None:
            parts.append(f"Body Battery {wellness.body_battery_low}→{wellness.body_battery_high}")
        if parts:
            wellness_line = "Wellness that morning: " + ", ".join(parts) + "."

    narrative_line = f"Narrative: {_narrative(activity, metrics)}"

    lines = [header]
    if hr_line:
        lines.append(hr_line)
    if aerobic_line:
        lines.append(aerobic_line)
    if vam_line:
        lines.append(vam_line)
    if wellness_line:
        lines.append(wellness_line)
    lines.append(narrative_line)

    return "\n".join(lines)


def build_wellness_chunk(wellness_rows: list[WellnessDaily], week_start: datetime.date) -> str:
    """Return a weekly wellness summary string."""
    if not wellness_rows:
        return f"Week of {week_start}: no wellness data."

    hrv_vals = [w.hrv_overnight for w in wellness_rows if w.hrv_overnight is not None]
    sleep_vals = [w.sleep_score for w in wellness_rows if w.sleep_score is not None]
    rhr_vals = [w.resting_hr for w in wellness_rows if w.resting_hr is not None]
    acwr_vals = [w.acwr for w in wellness_rows if w.acwr is not None]

    parts = [f"Week of {week_start}:"]
    if hrv_vals:
        parts.append(
            f"HRV avg {sum(hrv_vals) / len(hrv_vals):.0f} (range {min(hrv_vals):.0f}–{max(hrv_vals):.0f})"
        )
    if sleep_vals:
        parts.append(f"sleep score avg {sum(sleep_vals) / len(sleep_vals):.0f}")
    if rhr_vals:
        parts.append(f"RHR avg {sum(rhr_vals) / len(rhr_vals):.0f} bpm")
    if acwr_vals:
        parts.append(f"ACWR {sum(acwr_vals) / len(acwr_vals):.2f}")

    return " | ".join(parts)
