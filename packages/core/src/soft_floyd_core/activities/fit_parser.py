"""FIT file parsing via `fitdecode`.

Salvaged from v0 (git tag `v0-legacy:src/coach/ingest/fit_parser.py`) with
power/cadence additions (`RecordData.power_w`, `SessionSummary`/`LapData`
avg/max power+cadence), needed so ingestion can tell whether a power
meter was actually present in a given ride's data — see
docs/design-docs/sensor-capability-model.md rule 1 (per-activity analysis
must check the actual stream, never just the rider's declared profile).
Field numbers verified against the installed fitdecode's own FIT profile
(`fitdecode.profile.MESSAGE_TYPES[18|19|20].fields`), not assumed.

Known limitation carried forward, not fixed here (out of scope for this
plan — see docs/exec-plans/tech-debt-tracker.md): `RecordData.t_offset_s`
is only correct if a `record` message's timestamp can be related to
`session.start_time`, but real FIT files (and these fixtures) write the
`session` message *after* all `record` messages, so `session_start` is
still `None` when records are parsed and `t_offset_s` stays `0.0`. Fine for
this plan (sensor-presence detection doesn't use it); the training-metrics
exec-plan (HR drift/decoupling need real offsets) must fix this — e.g. by
seeding `session_start` from the first record's timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SessionSummary:
    sport: str = ""
    sub_sport: str = ""
    is_indoor: bool = False
    start_time: Any = None
    total_distance_m: float = 0.0
    total_elapsed_s: float = 0.0
    total_ascent_m: float = 0.0
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_power_w: int | None = None
    max_power_w: int | None = None
    avg_cadence: int | None = None


@dataclass
class LapData:
    lap_index: int = 0
    distance_m: float = 0.0
    duration_s: float = 0.0
    avg_hr: int | None = None
    avg_speed_mps: float | None = None
    avg_power_w: int | None = None
    avg_cadence: int | None = None
    elev_gain_m: float = 0.0


@dataclass
class RecordData:
    t_offset_s: float = 0.0
    hr: int | None = None
    speed_mps: float | None = None
    altitude_m: float | None = None
    cadence: int | None = None
    power_w: int | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class ParsedFit:
    session: SessionSummary = field(default_factory=SessionSummary)
    laps: list[LapData] = field(default_factory=list)
    records: list[RecordData] = field(default_factory=list)
    fit_path: Path | None = None


_SEMICIRCLES_TO_DEG = 180.0 / 2**31


def _semi_to_deg(value: int | None) -> float | None:
    if value is None:
        return None
    return value * _SEMICIRCLES_TO_DEG


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_fit(path: Path) -> ParsedFit:
    import fitdecode

    result = ParsedFit(fit_path=path)
    session_start: Any = None
    lap_index = 0

    with fitdecode.FitReader(str(path)) as reader:
        for frame in reader:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue

            name = frame.name

            if name == "session":
                sport_val = frame.get_value("sport", fallback=None)
                sub_val = frame.get_value("sub_sport", fallback=None)

                result.session.sport = str(sport_val) if sport_val is not None else ""
                result.session.sub_sport = str(sub_val) if sub_val is not None else ""

                indoor_keywords = {"indoor_cycling", "virtual_activity", "indoor"}
                result.session.is_indoor = (
                    str(sub_val).lower() in indoor_keywords
                    or str(sport_val).lower() in indoor_keywords
                )

                result.session.start_time = frame.get_value("start_time", fallback=None)
                result.session.total_distance_m = (
                    _to_float(frame.get_value("total_distance", fallback=0)) or 0.0
                )
                result.session.total_elapsed_s = (
                    _to_float(frame.get_value("total_elapsed_time", fallback=0)) or 0.0
                )
                result.session.total_ascent_m = (
                    _to_float(frame.get_value("total_ascent", fallback=0)) or 0.0
                )
                result.session.avg_hr = _to_int(frame.get_value("avg_heart_rate", fallback=None))
                result.session.max_hr = _to_int(frame.get_value("max_heart_rate", fallback=None))
                result.session.avg_power_w = _to_int(frame.get_value("avg_power", fallback=None))
                result.session.max_power_w = _to_int(frame.get_value("max_power", fallback=None))
                result.session.avg_cadence = _to_int(frame.get_value("avg_cadence", fallback=None))
                session_start = result.session.start_time

            elif name == "lap":
                lap = LapData(lap_index=lap_index)
                lap.distance_m = _to_float(frame.get_value("total_distance", fallback=0)) or 0.0
                lap.duration_s = _to_float(frame.get_value("total_elapsed_time", fallback=0)) or 0.0
                lap.avg_hr = _to_int(frame.get_value("avg_heart_rate", fallback=None))
                lap.avg_speed_mps = _to_float(frame.get_value("avg_speed", fallback=None))
                lap.avg_power_w = _to_int(frame.get_value("avg_power", fallback=None))
                lap.avg_cadence = _to_int(frame.get_value("avg_cadence", fallback=None))
                lap.elev_gain_m = _to_float(frame.get_value("total_ascent", fallback=0)) or 0.0
                result.laps.append(lap)
                lap_index += 1

            elif name == "record":
                rec = RecordData()
                ts = frame.get_value("timestamp", fallback=None)
                if ts is not None and session_start is not None:
                    try:
                        delta = (ts - session_start).total_seconds()
                        rec.t_offset_s = max(0.0, delta)
                    except Exception:
                        rec.t_offset_s = 0.0

                rec.hr = _to_int(frame.get_value("heart_rate", fallback=None))
                rec.speed_mps = _to_float(frame.get_value("speed", fallback=None))
                rec.altitude_m = _to_float(frame.get_value("altitude", fallback=None))
                rec.cadence = _to_int(frame.get_value("cadence", fallback=None))
                rec.power_w = _to_int(frame.get_value("power", fallback=None))
                rec.lat = _semi_to_deg(_to_int(frame.get_value("position_lat", fallback=None)))
                rec.lon = _semi_to_deg(_to_int(frame.get_value("position_long", fallback=None)))
                result.records.append(rec)

    return result
