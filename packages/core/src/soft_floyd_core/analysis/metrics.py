"""Deterministic, sensor-gated metrics for one ride — exec-plan 0023.

Everything the AI summary may say about numbers comes from here. Each field
is filled only when this ride's own FIT data verified the stream *and* the
rider's capability allowlist permits the metric (`allowed` is
`available_metrics_for_activity`); otherwise it stays None and a note says
why. Nothing is estimated and presented as measured — see
docs/design-docs/sensor-capability-model.md.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from soft_floyd_core.metrics.load import RideLoadInput, normalized_power, ride_load, tss
from soft_floyd_core.metrics.zones import make_zones, time_in_zones
from soft_floyd_core.models import Activity, Lap

# HR drift needs enough ride to compare two halves meaningfully.
_MIN_DRIFT_DURATION_S = 20 * 60
# Fraction of the ride that must carry HR samples before drift is trusted.
_MIN_HR_COVERAGE = 0.5


class RideMetricsOut(BaseModel):
    duration_s: float
    distance_km: float
    elev_gain_m: float
    climb_m_per_km: float | None
    avg_speed_kmh: float | None

    avg_power_w: int | None
    max_power_w: int | None
    normalized_power_w: int | None
    variability_index: float | None
    intensity_factor: float | None
    tss: float | None

    avg_hr: int | None
    max_hr: int | None
    hr_zone_minutes: dict[str, float] | None  # "1".."5" -> minutes
    hr_drift_pct: float | None  # 2nd-half avg HR vs 1st half, in percent

    load: float | None
    load_basis: str | None

    lap_count: int
    lap_variation_pct: float | None  # spread of lap power (else speed) across laps
    lap_variation_basis: str | None

    sensors_present: list[str]
    notes: list[str]


@dataclass(frozen=True)
class RideRecords:
    """Stored per-sample streams for one ride, aligned by index."""

    t_offset_s: Sequence[float]
    power_w: Sequence[int | None]
    hr: Sequence[int | None]


def _cv_pct(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean <= 0:
        return None
    return round(statistics.pstdev(values) / mean * 100, 1)


def _hr_drift_pct(records: RideRecords, duration_s: float) -> float | None:
    if duration_s < _MIN_DRIFT_DURATION_S:
        return None
    samples = [(t, h) for t, h in zip(records.t_offset_s, records.hr, strict=False) if h]
    if len(samples) < _MIN_HR_COVERAGE * duration_s / 5:  # ~1 sample per 5 s at the very least
        return None
    midpoint = records.t_offset_s[-1] / 2 if records.t_offset_s else duration_s / 2
    first = [h for t, h in samples if t < midpoint]
    second = [h for t, h in samples if t >= midpoint]
    if not first or not second:
        return None
    base = statistics.fmean(first)
    if base <= 0:
        return None
    return round((statistics.fmean(second) - base) / base * 100, 1)


def compute_ride_metrics(
    activity: Activity,
    laps: Sequence[Lap],
    records: RideRecords | None,
    *,
    allowed: Sequence[str],
    ftp_watts: int | None,
    lthr: int | None,
) -> RideMetricsOut:
    verified = activity.fit_status == "ok"
    power_ok = bool(verified and activity.has_power_data and "normalized_power" in allowed)
    hr_ok = bool(verified and activity.has_hr_data and "hr_zones" in allowed)
    speed_ok = bool(verified and activity.has_speed_data and "avg_speed" in allowed)
    sensors = [
        name
        for name, present in (
            ("power", power_ok),
            ("hr", hr_ok),
            ("cadence", verified and activity.has_cadence_data),
            ("speed", speed_ok),
            ("gps", verified and activity.has_gps_data),
        )
        if present
    ]
    notes: list[str] = []
    if not verified:
        notes.append("FIT data was unavailable, so only Garmin summary fields are used.")
    else:
        if not power_ok:
            notes.append("No power data on this ride.")
        if not hr_ok:
            notes.append("No heart-rate data on this ride.")

    distance_km = activity.distance_m / 1000
    avg_speed = (
        round(distance_km / (activity.duration_s / 3600), 1)
        if speed_ok and activity.duration_s > 0
        else None
    )

    # Power
    np_w = vi = intensity = stress = None
    if power_ok:
        if records is not None:
            raw_np = normalized_power(records.t_offset_s, records.power_w)
            if raw_np is not None:
                np_w = round(raw_np)
        elif activity.records_stored is False:
            notes.append("Per-second records were not stored, so normalized power is unavailable.")
        if np_w and activity.avg_power_w:
            vi = round(np_w / activity.avg_power_w, 2)
        if ftp_watts and np_w:
            intensity = round(np_w / ftp_watts, 2)
            stress = round(tss(activity.duration_s, np_w, ftp_watts), 0)
        elif not ftp_watts:
            notes.append("FTP is not set, so intensity factor and TSS are unavailable.")

    # Heart rate
    zone_minutes = drift = None
    if hr_ok:
        if lthr and records is not None:
            seconds = time_in_zones(records.t_offset_s, records.hr, make_zones(lthr))
            if sum(seconds.values()) >= _MIN_HR_COVERAGE * activity.duration_s:
                zone_minutes = {str(z): round(s / 60, 1) for z, s in seconds.items()}
        elif not lthr:
            notes.append("No LTHR or max HR is set, so heart-rate zones are unavailable.")
        if "hr_drift" in allowed and records is not None:
            drift = _hr_drift_pct(records, activity.duration_s)

    # Load, using the same basis rules as the training-load model.
    load = ride_load(
        RideLoadInput(
            duration_s=activity.duration_s,
            power_verified=power_ok and "training_stress_score" in allowed,
            hr_verified=hr_ok,
            avg_power_w=activity.avg_power_w,
            avg_hr=activity.avg_hr,
            t_offset_s=records.t_offset_s if records else None,
            power_w=records.power_w if records else None,
            hr=records.hr if records else None,
        ),
        ftp_watts=ftp_watts,
        lthr=lthr,
    )

    # Pacing across laps: power if verified, else speed.
    lap_values: list[float] = []
    lap_basis: str | None = None
    if power_ok:
        lap_values = [float(lap.avg_power_w) for lap in laps if lap.avg_power_w]
        lap_basis = "power"
    elif speed_ok:
        lap_values = [lap.avg_speed_mps for lap in laps if lap.avg_speed_mps]
        lap_basis = "speed"
    lap_variation = _cv_pct(lap_values)

    return RideMetricsOut(
        duration_s=activity.duration_s,
        distance_km=round(distance_km, 1),
        elev_gain_m=round(activity.elev_gain_m),
        climb_m_per_km=round(activity.elev_gain_m / distance_km, 1) if distance_km > 0 else None,
        avg_speed_kmh=avg_speed,
        avg_power_w=activity.avg_power_w if power_ok else None,
        max_power_w=activity.max_power_w if power_ok else None,
        normalized_power_w=np_w,
        variability_index=vi,
        intensity_factor=intensity,
        tss=stress,
        avg_hr=activity.avg_hr if hr_ok else None,
        max_hr=activity.max_hr if hr_ok else None,
        hr_zone_minutes=zone_minutes,
        hr_drift_pct=drift,
        load=round(load.load, 0),
        load_basis=load.basis,
        lap_count=len(laps),
        lap_variation_pct=lap_variation,
        lap_variation_basis=lap_basis if lap_variation is not None else None,
        sensors_present=sensors,
        notes=notes,
    )
