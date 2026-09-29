"""HR zones off LTHR and time-in-zone, ported from v0's `metrics/zones.py`
and the time-in-zone loop of `metrics/compute.py` (git tag `v0-legacy`).

Boundaries are the %LTHR table in docs/design-docs/training-signal-model.md
(Z1 below 80%, Z2 80-89%, Z3 90-94%, Z4 95-99%, Z5 100%+). Pure functions
over plain numbers: whether HR may be used for a ride at all is decided by
that ride's own `has_hr_data` (see sensor-capability-model.md), not here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# v0 estimated max HR as LTHR / 0.87, so the inverse is the LTHR guess when
# the rider only declared a max HR. A rough anchor, never a measured one.
_LTHR_FRACTION_OF_MAX_HR = 0.87


@dataclass(frozen=True)
class HRZones:
    lthr: int
    z1_max: float  # < 80% LTHR
    z2_max: float  # 80-89%
    z3_max: float  # 90-94%
    z4_max: float  # 95-99%
    # z5: >= 100% LTHR


def make_zones(lthr: int) -> HRZones:
    return HRZones(
        lthr=lthr,
        z1_max=lthr * 0.80,
        z2_max=lthr * 0.89,
        z3_max=lthr * 0.94,
        z4_max=lthr * 0.99,
    )


def zone_for_hr(hr: float, zones: HRZones) -> int:
    if hr < zones.z1_max:
        return 1
    if hr < zones.z2_max:
        return 2
    if hr < zones.z3_max:
        return 3
    if hr < zones.z4_max:
        return 4
    return 5


def lthr_from_max_hr(max_hr: int) -> int:
    return round(max_hr * _LTHR_FRACTION_OF_MAX_HR)


def resolve_lthr(lthr: int | None, max_hr: int | None) -> int | None:
    """The declared LTHR, else a guess from the declared max HR, else None."""
    if lthr:
        return lthr
    return lthr_from_max_hr(max_hr) if max_hr else None


def time_in_zones(
    t_offset_s: Sequence[float], hr: Sequence[int | None], zones: HRZones
) -> dict[int, float]:
    """Seconds in each zone. Each sample counts for the gap since the
    previous one (at least 1 s, v0's assumption for the first sample and
    for repeated timestamps); samples without HR add nothing."""
    seconds = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
    for i, value in enumerate(hr):
        if value is None:
            continue
        dt = 1.0 if i == 0 else max(1.0, t_offset_s[i] - t_offset_s[i - 1])
        seconds[zone_for_hr(float(value), zones)] += dt
    return seconds
