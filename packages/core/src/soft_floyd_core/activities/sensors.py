"""Per-activity sensor-presence detection.

This is the one place that enforces
docs/design-docs/sensor-capability-model.md rule 1: whether a metric is
available for a *specific ride* must come from that ride's own parsed FIT
data, never from the rider's declared profile. Accordingly, this module
must never import `RiderProfile`, `soft_floyd_core.profile`, or
`Settings` — there is nothing here it could legitimately read from them.
(Enforced by tests/test_sensor_streams.py's static source-scan guard, not
just this docstring.)

Presence rule: a stream counts as present only if at least one record has
a value that is both non-None and greater than zero (GPS: lat and lon
both non-None — position can legitimately be 0.0 near the equator/prime
meridian, unlike power/cadence/HR). A paired-but-idle sensor (a power
meter that never registers a non-zero watt because a rider free-wheeled
the entire recording) is indistinguishable from "not present" by this
rule — an accepted, documented simplification, not a bug: `any(v is not
None)` alone would misreport an all-zero channel (which some head units
write for an unpaired sensor slot) as present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soft_floyd_core.activities.fit_parser import ParsedFit


@dataclass(frozen=True)
class SensorStreams:
    power: bool
    hr: bool
    cadence: bool
    speed: bool
    gps: bool


def _any_positive(values: list) -> bool:
    return any(v is not None and v > 0 for v in values)


def detect_sensor_streams(parsed: ParsedFit) -> SensorStreams:
    records = parsed.records
    return SensorStreams(
        power=_any_positive([r.power_w for r in records]),
        hr=_any_positive([r.hr for r in records]),
        cadence=_any_positive([r.cadence for r in records]),
        speed=_any_positive([r.speed_mps for r in records]),
        gps=any(r.lat is not None and r.lon is not None for r in records),
    )
