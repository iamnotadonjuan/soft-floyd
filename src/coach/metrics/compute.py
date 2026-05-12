from __future__ import annotations

import math
from typing import TYPE_CHECKING

from coach.metrics.zones import make_zones, zone_for_hr

if TYPE_CHECKING:
    from coach.ingest.fit_parser import ParsedFit


# Grade-adjusted pace: Strava-style equivalence factor (simplified)
# factor = 1 + 0.033*grade + 0.00266*grade^2  (grade as fraction)
def _gap_factor(grade_fraction: float) -> float:
    g = grade_fraction
    return 1.0 + 0.033 * g + 0.00266 * g * g


def compute_metrics(parsed_fit: ParsedFit, lthr: int = 165) -> dict:
    records = parsed_fit.records
    zones = make_zones(lthr)

    # Time in zones (seconds)
    time_in_z = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
    hr_values: list[float] = []
    speeds: list[float] = []

    for i, rec in enumerate(records):
        dt = 1.0  # assume 1-second recording interval
        if i > 0:
            dt = max(1.0, rec.t_offset_s - records[i - 1].t_offset_s)

        if rec.hr is not None:
            z = zone_for_hr(float(rec.hr), zones)
            time_in_z[z] += dt
            hr_values.append(float(rec.hr))

        if rec.speed_mps is not None:
            speeds.append(rec.speed_mps)

    # HR drift: (avg HR second half - avg HR first half) / avg HR first half * 100
    hr_drift_pct: float | None = None
    if len(hr_values) >= 10:
        mid = len(hr_values) // 2
        first_avg = sum(hr_values[:mid]) / mid
        second_avg = sum(hr_values[mid:]) / (len(hr_values) - mid)
        if first_avg > 0:
            hr_drift_pct = (second_avg - first_avg) / first_avg * 100.0

    # Decoupling: (HR/speed ratio second half - HR/speed ratio first half) / first half * 100
    decoupling_pct: float | None = None
    valid_pairs = [
        (float(r.hr), r.speed_mps)
        for r in records
        if r.hr is not None and r.speed_mps is not None and r.speed_mps > 0
    ]
    if len(valid_pairs) >= 10:
        mid = len(valid_pairs) // 2

        def avg_ratio(pairs: list) -> float:
            return sum(h / s for h, s in pairs) / len(pairs)

        r1 = avg_ratio(valid_pairs[:mid])
        r2 = avg_ratio(valid_pairs[mid:])
        if r1 > 0:
            decoupling_pct = (r2 - r1) / r1 * 100.0

    # GAP: grade-adjusted average speed from lap or records
    gap_normalized: float | None = None
    laps = parsed_fit.laps
    if laps:
        total_gap_dist = 0.0
        total_gap_time = 0.0
        for lap in laps:
            if lap.duration_s > 0 and lap.distance_m > 0:
                grade = lap.elev_gain_m / lap.distance_m
                factor = _gap_factor(grade)
                total_gap_dist += lap.distance_m * factor
                total_gap_time += lap.duration_s
        if total_gap_time > 0:
            gap_normalized = total_gap_dist / total_gap_time  # m/s

    # VAM best 20-min window
    vam_best_20min: float | None = None
    if records:
        window_s = 1200.0  # 20 minutes
        alt_records = [(r.t_offset_s, r.altitude_m) for r in records if r.altitude_m is not None]
        if len(alt_records) >= 2:
            best_vam = 0.0
            for i, (t0, a0) in enumerate(alt_records):
                for j in range(i + 1, len(alt_records)):
                    t1, a1 = alt_records[j]
                    dt = t1 - t0
                    if dt > window_s:
                        break
                    if dt >= 60.0 and a1 > a0:
                        vam = (a1 - a0) / dt * 3600.0  # m/h
                        if vam > best_vam:
                            best_vam = vam
            if best_vam > 0:
                vam_best_20min = best_vam

    # TRIMP (Banister-Morton formula)
    tss_proxy: float | None = None
    session = parsed_fit.session
    if session.avg_hr is not None and session.total_elapsed_s > 0:
        lthr_f = float(lthr)
        max_hr_estimate = lthr_f / 0.87  # rough estimate
        hr_ratio = (float(session.avg_hr) - 60.0) / (max_hr_estimate - 60.0)
        hr_ratio = max(0.0, min(1.0, hr_ratio))
        duration_min = session.total_elapsed_s / 60.0
        tss_proxy = duration_min * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)

    return {
        "decoupling_pct": decoupling_pct,
        "hr_drift_pct": hr_drift_pct,
        "time_in_z1": time_in_z[1],
        "time_in_z2": time_in_z[2],
        "time_in_z3": time_in_z[3],
        "time_in_z4": time_in_z[4],
        "time_in_z5": time_in_z[5],
        "vam_best_20min": vam_best_20min,
        "gap_normalized": gap_normalized,
        "tss_proxy": tss_proxy,
    }
