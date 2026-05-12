"""Generate minimal but valid FIT test fixtures.

Run once: uv run python tests/make_fixtures.py
Verifiable with: uv run python -c "from coach.ingest.fit_parser import parse_fit; ..."
"""
from __future__ import annotations

import struct
import datetime
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
FIT_UTC_REFERENCE = 631065600  # seconds between FIT epoch (1989-12-31) and Unix epoch


def _fit_timestamp(dt: datetime.datetime) -> int:
    return int(dt.timestamp()) - FIT_UTC_REFERENCE


def _crc16(data: bytes) -> int:
    table = [
        0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
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


# ---- definition message builder ----------------------------------------
# field_defs: list of (field_def_num, size_bytes, base_type_byte)
#   base types: 0=enum, 1=sint8, 2=uint8, 4=uint16, 6=uint32, 7=string
#               128=enum, 131=sint16, 132=uint16, 133=sint32, 134=uint32

def _def_msg(local_num: int, global_num: int, field_defs: list[tuple[int, int, int]]) -> bytes:
    hdr = 0x40 | (local_num & 0x0F)
    out = struct.pack("<BBBHB", hdr, 0, 0, global_num, len(field_defs))
    for fnum, fsize, ftype in field_defs:
        out += struct.pack("BBB", fnum, fsize, ftype)
    return out


def _data_msg(local_num: int, fmt: str, *values) -> bytes:
    return bytes([local_num & 0x0F]) + struct.pack(fmt, *values)


# ---- FIT builders -------------------------------------------------------
# Global message numbers:
#   18 = session, 19 = lap, 20 = record

SESSION_LOCAL = 0
LAP_LOCAL = 1
RECORD_LOCAL = 2
RECORD_NO_GPS_LOCAL = 3

# Session definition:
# 253=timestamp(uint32), 5=sport(uint8), 6=sub_sport(uint8),
# 7=total_elapsed_time(uint32, ms*1000), 9=total_distance(uint32, cm*100),
# 22=total_ascent(uint16), 16=avg_heart_rate(uint8), 17=max_heart_rate(uint8)
SESSION_DEF = _def_msg(SESSION_LOCAL, 18, [
    (253, 4, 134), (5, 1, 2), (6, 1, 2),
    (7, 4, 134), (9, 4, 134), (22, 2, 132),
    (16, 1, 2), (17, 1, 2),
])
# Struct: I B B I I H B B = 4+1+1+4+4+2+1+1 = 18 bytes


def session_data(dt, sport, sub_sport, elapsed_s, distance_m, ascent_m, avg_hr, max_hr) -> bytes:
    return _data_msg(SESSION_LOCAL, "<BBBIIHBB",
        sport, sub_sport,
        _fit_timestamp(dt),
        int(elapsed_s * 1000),
        int(distance_m * 100),
        int(ascent_m),
        avg_hr, max_hr,
    )


# Wait — the definition fields must appear in the order of field_def_num ascending by how fitdecode
# processes them. Actually the order is the order in the definition message.
# Let me rebuild with correct ordering (timestamp first as 253 is always first in practice).

# I'll restart with a cleaner approach using a simple ordered field list.

class FitBuilder:
    """Minimal FIT file builder. Writes definition messages once, data messages many times."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._defined: set[int] = set()

    # ------------------------------------------------------------------
    # Low-level primitives
    # ------------------------------------------------------------------
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
    # Session  (global_num=18)
    # field order follows definition order below
    # fmt: <IbbIIHBB = 4+1+1+4+4+2+1+1 = 18 bytes
    # ------------------------------------------------------------------
    def session(self, dt, sport, sub_sport, elapsed_s, distance_m, ascent_m, avg_hr, max_hr):
        # fields order matches definition order
        # fmt: <IBBIIIHBB = 4+1+1+4+4+2+1+1 = 18 bytes
        self._def(0, 18, [
            (253, 4, 134),  # timestamp, uint32
            (5, 1, 2),      # sport, uint8
            (6, 1, 2),      # sub_sport, uint8
            (7, 4, 134),    # total_elapsed_time, uint32 (ms×1000)
            (9, 4, 134),    # total_distance, uint32 (m×100)
            (22, 2, 132),   # total_ascent, uint16
            (16, 1, 2),     # avg_heart_rate, uint8
            (17, 1, 2),     # max_heart_rate, uint8
        ])
        # fmt: I(ts) B(sport) B(sub_sport) I(elapsed) I(distance) H(ascent) B(avg_hr) B(max_hr)
        # = 4+1+1+4+4+2+1+1 = 18 bytes
        self._data(0, "<IBBIIHBB",
            _fit_timestamp(dt),
            sport, sub_sport,
            int(elapsed_s * 1000),
            int(distance_m * 100),
            int(ascent_m),
            avg_hr, max_hr,
        )

    # ------------------------------------------------------------------
    # Lap  (global_num=19)
    # fields: timestamp(4) elapsed_time(4) distance(4) ascent(2) avg_hr(1) avg_speed(2)
    # fmt: <IIIHBH = 4+4+4+2+1+2 = 17 bytes
    # ------------------------------------------------------------------
    def lap(self, dt, elapsed_s, distance_m, ascent_m, avg_hr, avg_speed_mps):
        # FIT lap (global 19) field numbers verified from fitdecode profile
        self._def(1, 19, [
            (253, 4, 134),  # timestamp, uint32
            (7, 4, 134),    # total_elapsed_time, uint32 (ms×1000)
            (9, 4, 134),    # total_distance, uint32 (m×100)
            (21, 2, 132),   # total_ascent, uint16 (field 21, NOT 22)
            (15, 1, 2),     # avg_heart_rate, uint8 (field 15, NOT 16)
            (13, 2, 132),   # avg_speed, uint16 (mm/s)
        ])
        # fmt: I(ts) I(elapsed) I(distance) H(ascent) B(avg_hr) H(speed) = 17 bytes
        self._data(1, "<IIIHBH",
            _fit_timestamp(dt),
            int(elapsed_s * 1000),
            int(distance_m * 100),
            int(ascent_m),
            avg_hr,
            int(avg_speed_mps * 1000),
        )

    # ------------------------------------------------------------------
    # Record with GPS  (global_num=20, local=2)
    # fmt: <IiiHHB = 4+4+4+2+2+1 = 17 bytes
    # ------------------------------------------------------------------
    def record_gps(self, dt, hr, speed_mps, altitude_m, lat, lon):
        self._def(2, 20, [
            (253, 4, 134),  # timestamp, uint32
            (0, 4, 133),    # position_lat, sint32 (semicircles)
            (1, 4, 133),    # position_long, sint32 (semicircles)
            (6, 2, 132),    # altitude, uint16 (scale 5, offset 500)
            (7, 2, 132),    # speed, uint16 (mm/s)
            (3, 1, 2),      # heart_rate, uint8
        ])
        lat_semi = int(lat * (2**31 / 180.0))
        lon_semi = int(lon * (2**31 / 180.0))
        self._data(2, "<IiiHHB",
            _fit_timestamp(dt),
            lat_semi, lon_semi,
            int((altitude_m + 500.0) * 5.0),
            int(speed_mps * 1000.0),
            hr,
        )

    # ------------------------------------------------------------------
    # Record without GPS  (global_num=20, local=3)
    # fmt: <IHHB = 4+2+2+1 = 9 bytes
    # ------------------------------------------------------------------
    def record_no_gps(self, dt, hr, speed_mps, altitude_m):
        self._def(3, 20, [
            (253, 4, 134),  # timestamp, uint32
            (6, 2, 132),    # altitude, uint16
            (7, 2, 132),    # speed, uint16 (mm/s)
            (3, 1, 2),      # heart_rate, uint8
        ])
        self._data(3, "<IHHB",
            _fit_timestamp(dt),
            int((altitude_m + 500.0) * 5.0),
            int(speed_mps * 1000.0),
            hr,
        )

    def build(self) -> bytes:
        data = bytes(self._buf)
        header = _pack_header(len(data))  # data_size excludes the 2-byte file CRC
        file_crc = _crc16(header + data)
        return header + data + struct.pack("<H", file_crc)


# ---- Fixture generators -----------------------------------------------

def make_road_fit() -> bytes:
    """~62 km road ride, 2 laps, GPS, avg HR 142, sub_sport=road."""
    b = FitBuilder()
    base = datetime.datetime(2026, 4, 15, 8, 0, 0, tzinfo=datetime.timezone.utc)
    n_records_per_lap = 50
    lap_elapsed_s = 4500.0
    interval_s = lap_elapsed_s / n_records_per_lap

    for lap_i in range(2):
        lap_start = base + datetime.timedelta(hours=lap_i)
        for j in range(n_records_per_lap):
            ts = lap_start + datetime.timedelta(seconds=j * interval_s)
            hr = 135 + j // 5 + lap_i * 5
            alt = 200.0 + lap_i * 400 + j * 3.0
            lat = 6.2 + lap_i * 0.01 + j * 0.001
            lon = -75.5 + lap_i * 0.01 + j * 0.001
            b.record_gps(ts, hr=min(hr, 175), speed_mps=7.2, altitude_m=alt, lat=lat, lon=lon)

        b.lap(lap_start,
            elapsed_s=lap_elapsed_s,
            distance_m=31200.0,
            ascent_m=425.0,
            avg_hr=142,
            avg_speed_mps=6.93,
        )

    b.session(base,
        sport=2, sub_sport=7,  # cycling, road (FIT sub_sport=7 → 'road')
        elapsed_s=9000.0,
        distance_m=62400.0,
        ascent_m=850.0,
        avg_hr=142,
        max_hr=178,
    )
    return b.build()


def make_mtb_fit() -> bytes:
    """25 km MTB ride, 1 lap, GPS, high elev/km, sub_sport=mountain."""
    b = FitBuilder()
    base = datetime.datetime(2026, 4, 10, 9, 0, 0, tzinfo=datetime.timezone.utc)

    for j in range(40):
        ts = base + datetime.timedelta(seconds=j * 60)
        hr = min(150 + j // 4, 185)
        alt = 1500.0 + j * 22.5
        lat = 6.3 + j * 0.0005
        lon = -75.4 + j * 0.0005
        b.record_gps(ts, hr=hr, speed_mps=3.5, altitude_m=alt, lat=lat, lon=lon)

    b.lap(base,
        elapsed_s=2400.0,
        distance_m=8400.0,
        ascent_m=900.0,
        avg_hr=158,
        avg_speed_mps=3.5,
    )
    b.session(base,
        sport=2, sub_sport=8,  # cycling, mountain
        elapsed_s=2400.0,
        distance_m=8400.0,
        ascent_m=900.0,
        avg_hr=158,
        max_hr=185,
    )
    return b.build()


def make_indoor_fit() -> bytes:
    """1-hour indoor cycling, 3 laps, no GPS, sub_sport=virtual_activity→indoor."""
    b = FitBuilder()
    base = datetime.datetime(2026, 4, 12, 7, 0, 0, tzinfo=datetime.timezone.utc)

    for i in range(3):
        lap_start = base + datetime.timedelta(minutes=i * 20)
        for j in range(20):
            ts = lap_start + datetime.timedelta(seconds=j * 60)
            hr = min(130 + j + i * 10, 172)
            b.record_no_gps(ts, hr=hr, speed_mps=8.0, altitude_m=0.0)

        b.lap(lap_start,
            elapsed_s=1200.0,
            distance_m=9600.0,
            ascent_m=0.0,
            avg_hr=140 + i * 10,
            avg_speed_mps=8.0,
        )

    b.session(base,
        sport=2, sub_sport=58,  # cycling, virtual_activity → indoor
        elapsed_s=3600.0,
        distance_m=28800.0,
        ascent_m=0.0,
        avg_hr=148,
        max_hr=172,
    )
    return b.build()


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, fn in [("sample_road", make_road_fit), ("sample_mtb", make_mtb_fit), ("sample_indoor", make_indoor_fit)]:
        path = FIXTURES / f"{name}.fit"
        path.write_bytes(fn())
        print(f"Created {path}")
