"""Generate minimal but valid FIT test fixtures.

Run once: uv run python tests/make_fixtures.py

Field numbers below are the real FIT SDK "record" (global mesg 20) profile,
verified against the installed fitdecode's own profile data
(`fitdecode.profile.MESSAGE_TYPES[20].fields`) rather than assumed —
v0's generator had these swapped (it wrote intended-altitude data to field
6, which fitdecode actually names "speed"; intended-speed data to field 7,
which fitdecode names "power"), so `frame.get_value("altitude")` always
returned None and `frame.get_value("speed")` returned garbage. Fixed here:
  2 = altitude (uint16, scale 5, offset 500)
  3 = heart_rate (uint8)
  4 = cadence (uint8)
  6 = speed (uint16, scale 1000 -> mm/s)
  7 = power (uint16, watts, no scale)
"""

from __future__ import annotations

import datetime
import struct
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
FIT_UTC_REFERENCE = 631065600  # seconds between FIT epoch (1989-12-31) and Unix epoch


def _fit_timestamp(dt: datetime.datetime) -> int:
    return int(dt.timestamp()) - FIT_UTC_REFERENCE


def _crc16(data: bytes) -> int:
    table = [
        0x0000,
        0xCC01,
        0xD801,
        0x1400,
        0xF001,
        0x3C00,
        0x2800,
        0xE401,
        0xA001,
        0x6C00,
        0x7800,
        0xB401,
        0x5000,
        0x9C01,
        0x8801,
        0x4400,
    ]
    crc = 0
    for byte in data:
        tmp = table[crc & 0x0F]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ table[byte & 0x0F]
        tmp = table[crc & 0x0F]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ table[(byte >> 4) & 0x0F]
    return crc


def _pack_header(data_size: int) -> bytes:
    hdr = struct.pack("<BBHI4s", 14, 16, 2154, data_size, b".FIT")
    return hdr + struct.pack("<H", _crc16(hdr))


class FitBuilder:
    """Minimal FIT file builder. Writes definition messages once, data messages many times."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._defined: set[int] = set()

    def _emit(self, data: bytes) -> None:
        self._buf.extend(data)

    def _def(self, local_num: int, global_num: int, fields: list[tuple[int, int, int]]) -> None:
        """Emit a definition message (only once per local_num)."""
        if local_num in self._defined:
            return
        hdr = 0x40 | (local_num & 0x0F)
        msg = struct.pack("<BBBHB", hdr, 0, 0, global_num, len(fields))
        for fdef, fsize, ftype in fields:
            msg += struct.pack("BBB", fdef, fsize, ftype)
        self._emit(msg)
        self._defined.add(local_num)

    def _data(self, local_num: int, fmt: str, *values) -> None:
        self._emit(bytes([local_num & 0x0F]) + struct.pack(fmt, *values))

    # ------------------------------------------------------------------
    # Session (global_num=18). avg_power/max_power/avg_cadence optional —
    # field numbers 20/21/18 verified against fitdecode's profile.
    # ------------------------------------------------------------------
    def session(
        self,
        dt,
        sport,
        sub_sport,
        elapsed_s,
        distance_m,
        ascent_m,
        avg_hr,
        max_hr,
        avg_power=None,
        max_power=None,
        avg_cadence=None,
    ):
        fields = [
            (253, 4, 134),  # timestamp, uint32
            (5, 1, 2),  # sport, uint8
            (6, 1, 2),  # sub_sport, uint8
            (7, 4, 134),  # total_elapsed_time, uint32 (ms)
            (9, 4, 134),  # total_distance, uint32 (cm)
            (22, 2, 132),  # total_ascent, uint16
            (16, 1, 2),  # avg_heart_rate, uint8
            (17, 1, 2),  # max_heart_rate, uint8
        ]
        fmt = "<IBBIIHBB"
        values = [
            _fit_timestamp(dt),
            sport,
            sub_sport,
            int(elapsed_s * 1000),
            int(distance_m * 100),
            int(ascent_m),
            avg_hr,
            max_hr,
        ]
        if avg_power is not None:
            fields.append((20, 2, 132))
            fmt += "H"
            values.append(avg_power)
        if max_power is not None:
            fields.append((21, 2, 132))
            fmt += "H"
            values.append(max_power)
        if avg_cadence is not None:
            fields.append((18, 1, 2))
            fmt += "B"
            values.append(avg_cadence)
        self._def(0, 18, fields)
        self._data(0, fmt, *values)

    # ------------------------------------------------------------------
    # Lap (global_num=19) — field numbers verified against fitdecode's profile
    # (21=total_ascent, 15=avg_heart_rate, 13=avg_speed, 19=avg_power,
    # 17=avg_cadence on the lap message, distinct from the equivalents on
    # session/record).
    # ------------------------------------------------------------------
    def lap(
        self,
        dt,
        elapsed_s,
        distance_m,
        ascent_m,
        avg_hr,
        avg_speed_mps,
        avg_power=None,
        avg_cadence=None,
    ):
        fields = [
            (253, 4, 134),  # timestamp, uint32
            (7, 4, 134),  # total_elapsed_time, uint32 (ms)
            (9, 4, 134),  # total_distance, uint32 (cm)
            (21, 2, 132),  # total_ascent, uint16
            (15, 1, 2),  # avg_heart_rate, uint8
            (13, 2, 132),  # avg_speed, uint16 (mm/s)
        ]
        fmt = "<IIIHBH"
        values = [
            _fit_timestamp(dt),
            int(elapsed_s * 1000),
            int(distance_m * 100),
            int(ascent_m),
            avg_hr,
            int(avg_speed_mps * 1000),
        ]
        if avg_power is not None:
            fields.append((19, 2, 132))
            fmt += "H"
            values.append(avg_power)
        if avg_cadence is not None:
            fields.append((17, 1, 2))
            fmt += "B"
            values.append(avg_cadence)
        self._def(1, 19, fields)
        self._data(1, fmt, *values)

    # ------------------------------------------------------------------
    # Record (global_num=20). Two variants: with/without GPS + power/cadence.
    # ------------------------------------------------------------------
    def record(
        self,
        dt,
        *,
        hr=None,
        speed_mps=None,
        altitude_m=None,
        cadence=None,
        power=None,
        lat=None,
        lon=None,
    ) -> None:
        fields: list[tuple[int, int, int]] = [(253, 4, 134)]  # timestamp
        fmt = "<I"
        values: list = [_fit_timestamp(dt)]

        if lat is not None and lon is not None:
            fields += [(0, 4, 133), (1, 4, 133)]
            fmt += "ii"
            values += [int(lat * (2**31 / 180.0)), int(lon * (2**31 / 180.0))]
        if altitude_m is not None:
            fields.append((2, 2, 132))
            fmt += "H"
            values.append(int((altitude_m + 500.0) * 5.0))
        if hr is not None:
            fields.append((3, 1, 2))
            fmt += "B"
            values.append(hr)
        if cadence is not None:
            fields.append((4, 1, 2))
            fmt += "B"
            values.append(cadence)
        if speed_mps is not None:
            fields.append((6, 2, 132))
            fmt += "H"
            values.append(int(speed_mps * 1000.0))
        if power is not None:
            fields.append((7, 2, 132))
            fmt += "H"
            values.append(power)

        # local message number keyed by which optional fields are present, so
        # differently-shaped records within one file each get their own
        # definition message (FIT allows up to 16 concurrent local types).
        local_num = 2 + (lat is not None) + 2 * (power is not None) + 4 * (cadence is not None)
        self._def(local_num, 20, fields)
        self._data(local_num, fmt, *values)

    def build(self) -> bytes:
        data = bytes(self._buf)
        header = _pack_header(len(data))
        file_crc = _crc16(header + data)
        return header + data + struct.pack("<H", file_crc)


# ---- Fixture generators -----------------------------------------------


def make_road_fit() -> bytes:
    """~62 km road ride, 2 laps, GPS + HR + cadence + power (full sensor rider)."""
    b = FitBuilder()
    base = datetime.datetime(2026, 4, 15, 8, 0, 0, tzinfo=datetime.UTC)
    n_records_per_lap = 50
    lap_elapsed_s = 4500.0
    interval_s = lap_elapsed_s / n_records_per_lap

    for lap_i in range(2):
        lap_start = base + datetime.timedelta(hours=lap_i)
        for j in range(n_records_per_lap):
            ts = lap_start + datetime.timedelta(seconds=j * interval_s)
            hr = min(135 + j // 5 + lap_i * 5, 175)
            alt = 200.0 + lap_i * 400 + j * 3.0
            lat = 6.2 + lap_i * 0.01 + j * 0.001
            lon = -75.5 + lap_i * 0.01 + j * 0.001
            b.record(
                ts,
                hr=hr,
                speed_mps=7.2,
                altitude_m=alt,
                cadence=88 + (j % 5),
                power=180 + (j % 40),
                lat=lat,
                lon=lon,
            )

        b.lap(
            lap_start,
            elapsed_s=lap_elapsed_s,
            distance_m=31200.0,
            ascent_m=425.0,
            avg_hr=142,
            avg_speed_mps=6.93,
            avg_power=195,
            avg_cadence=89,
        )

    b.session(
        base,
        sport=2,
        sub_sport=7,  # cycling, road
        elapsed_s=9000.0,
        distance_m=62400.0,
        ascent_m=850.0,
        avg_hr=142,
        max_hr=178,
        avg_power=195,
        max_power=420,
        avg_cadence=89,
    )
    return b.build()


def make_mtb_fit() -> bytes:
    """25 km MTB ride, 1 lap, GPS + HR only — no power meter, no cadence sensor."""
    b = FitBuilder()
    base = datetime.datetime(2026, 4, 10, 9, 0, 0, tzinfo=datetime.UTC)

    for j in range(40):
        ts = base + datetime.timedelta(seconds=j * 60)
        hr = min(150 + j // 4, 185)
        alt = 1500.0 + j * 22.5
        lat = 6.3 + j * 0.0005
        lon = -75.4 + j * 0.0005
        b.record(ts, hr=hr, speed_mps=3.5, altitude_m=alt, lat=lat, lon=lon)

    b.lap(
        base,
        elapsed_s=2400.0,
        distance_m=8400.0,
        ascent_m=900.0,
        avg_hr=158,
        avg_speed_mps=3.5,
    )
    b.session(
        base,
        sport=2,
        sub_sport=8,  # cycling, mountain
        elapsed_s=2400.0,
        distance_m=8400.0,
        ascent_m=900.0,
        avg_hr=158,
        max_hr=185,
    )
    return b.build()


def make_indoor_fit() -> bytes:
    """1-hour indoor cycling, 3 laps, HR only — no GPS, no power, no cadence."""
    b = FitBuilder()
    base = datetime.datetime(2026, 4, 12, 7, 0, 0, tzinfo=datetime.UTC)

    for i in range(3):
        lap_start = base + datetime.timedelta(minutes=i * 20)
        for j in range(20):
            ts = lap_start + datetime.timedelta(seconds=j * 60)
            hr = min(130 + j + i * 10, 172)
            b.record(ts, hr=hr, speed_mps=8.0, altitude_m=0.0)

        b.lap(
            lap_start,
            elapsed_s=1200.0,
            distance_m=9600.0,
            ascent_m=0.0,
            avg_hr=140 + i * 10,
            avg_speed_mps=8.0,
        )

    b.session(
        base,
        sport=2,
        sub_sport=58,  # cycling, virtual_activity -> indoor
        elapsed_s=3600.0,
        distance_m=28800.0,
        ascent_m=0.0,
        avg_hr=148,
        max_hr=172,
    )
    return b.build()


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, fn in [
        ("sample_road", make_road_fit),
        ("sample_mtb", make_mtb_fit),
        ("sample_indoor", make_indoor_fit),
    ]:
        path = FIXTURES / f"{name}.fit"
        path.write_bytes(fn())
        print(f"Created {path}")
