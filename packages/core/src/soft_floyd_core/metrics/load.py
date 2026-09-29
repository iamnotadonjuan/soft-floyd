"""Per-ride training load on a TSS-like scale (an hour at threshold is
about 100), tagged with the basis it was measured from — exec-plan 0012.

Pure functions over plain numbers, so they test without a database. The
caller (`metrics/service.py`) owns the sensor gate: `power_verified` and
`hr_verified` mean "this ride's own FIT data has that stream and the
capability rules allow using it" (docs/design-docs/sensor-capability-model.md).
A stream that isn't verified is never read, whatever the anchors say, and
a ride that verifies nothing is scored from duration and labelled as an
estimate — never as measured load.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from soft_floyd_core.metrics.zones import make_zones, time_in_zones

Basis = Literal["power_np", "power_avg", "hr_zones", "hr_avg", "duration"]

_NP_WINDOW_S = 30
# Load per hour of time in each HR zone (Coggan's hrTSS table, with his
# Z5a/b/c collapsed into Z5, so very hard efforts are undercounted a bit).
_HR_ZONE_LOAD_PER_HOUR = {1: 20.0, 2: 40.0, 3: 60.0, 4: 80.0, 5: 100.0}
# A flat endurance-pace guess for rides with nothing verified — the same
# as the Z2 weight above.
DURATION_LOAD_PER_HOUR = 40.0
# HR strap dropouts: below this share of the ride covered by HR samples,
# zone times would understate the ride, so fall back to the average.
_MIN_HR_COVERAGE = 0.5


@dataclass(frozen=True)
class RideLoadInput:
    duration_s: float
    power_verified: bool = False
    hr_verified: bool = False
    avg_power_w: float | None = None
    avg_hr: float | None = None
    # Stored per-second records, when the ride has them (else all None).
    t_offset_s: Sequence[float] | None = None
    power_w: Sequence[int | None] | None = None
    hr: Sequence[int | None] | None = None


@dataclass(frozen=True)
class RideLoad:
    load: float
    basis: Basis


def normalized_power(t_offset_s: Sequence[float], power_w: Sequence[int | None]) -> float | None:
    """Coggan NP: 30 s rolling mean of power, raised to the 4th power,
    averaged, 4th-rooted. Samples are put on a 1 Hz grid holding the last
    valid value (Garmin's smart recording is irregular); samples with no
    power are skipped. None when there is under 30 s of data to average."""
    grid: list[float] = []
    last: float | None = None
    samples = [(t, p) for t, p in zip(t_offset_s, power_w, strict=False) if p is not None]
    if not samples:
        return None
    end = int(samples[-1][0])
    j = 0
    for second in range(int(samples[0][0]), end + 1):
        while j < len(samples) and samples[j][0] <= second:
            last = float(samples[j][1])
            j += 1
        if last is not None:
            grid.append(last)
    if len(grid) < _NP_WINDOW_S:
        return None
    prefix = [0.0]
    for value in grid:
        prefix.append(prefix[-1] + value)
    rolling = [
        (prefix[i + 1] - prefix[i + 1 - _NP_WINDOW_S]) / _NP_WINDOW_S
        for i in range(_NP_WINDOW_S - 1, len(grid))
    ]
    return (sum(v**4 for v in rolling) / len(rolling)) ** 0.25


def tss(duration_s: float, np_w: float, ftp_watts: float) -> float:
    """(duration · NP · IF) / (FTP · 3600) · 100, with IF = NP / FTP."""
    intensity = np_w / ftp_watts
    return duration_s * np_w * intensity / (ftp_watts * 3600.0) * 100.0


def ride_load(ride: RideLoadInput, *, ftp_watts: int | None, lthr: int | None) -> RideLoad:
    """Best available basis first: power_np, power_avg, hr_zones, hr_avg,
    then duration. `lthr` should already be resolved (see `resolve_lthr`)."""
    if ride.duration_s <= 0:
        return RideLoad(0.0, "duration")

    if ride.power_verified and ftp_watts:
        if ride.t_offset_s is not None and ride.power_w is not None:
            np_w = normalized_power(ride.t_offset_s, ride.power_w)
            if np_w is not None:
                return RideLoad(tss(ride.duration_s, np_w, ftp_watts), "power_np")
        if ride.avg_power_w:
            return RideLoad(tss(ride.duration_s, ride.avg_power_w, ftp_watts), "power_avg")

    if ride.hr_verified and lthr:
        if ride.t_offset_s is not None and ride.hr is not None:
            seconds = time_in_zones(ride.t_offset_s, ride.hr, make_zones(lthr))
            if sum(seconds.values()) >= _MIN_HR_COVERAGE * ride.duration_s:
                load = sum(_HR_ZONE_LOAD_PER_HOUR[z] * s / 3600.0 for z, s in seconds.items())
                return RideLoad(load, "hr_zones")
        if ride.avg_hr:
            intensity = ride.avg_hr / lthr
            return RideLoad(ride.duration_s / 3600.0 * intensity**2 * 100.0, "hr_avg")

    return RideLoad(ride.duration_s / 3600.0 * DURATION_LOAD_PER_HOUR, "duration")
