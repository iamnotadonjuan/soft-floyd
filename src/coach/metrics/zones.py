from __future__ import annotations

from dataclasses import dataclass


@dataclass
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
