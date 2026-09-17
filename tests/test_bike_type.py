"""classify()'s five rules, in strict priority order. Ported from v0's
test suite (rules unchanged, salvaged verbatim aside from the module
path) plus a case proving the rule-1 key-mismatch fix
(activities/classify.py reads "isIndoor", matching real Garmin
summaries — v0 read "is_indoor", which no real caller ever passed).
"""

from __future__ import annotations

from soft_floyd_core.activities.classify import classify
from soft_floyd_core.activities.fit_parser import ParsedFit, RecordData, SessionSummary


def _parsed(sub_sport="", is_indoor=False, distance_m=0.0, elev_m=0.0, duration_s=0.0, records=()):
    return ParsedFit(
        session=SessionSummary(
            sub_sport=sub_sport,
            is_indoor=is_indoor,
            total_distance_m=distance_m,
            total_ascent_m=elev_m,
            total_elapsed_s=duration_s,
        ),
        records=list(records),
    )


def test_indoor_flag_from_fit_session_wins_regardless_of_sub_sport():
    parsed = _parsed(sub_sport="road", is_indoor=True)
    assert classify({}, parsed) == "indoor"


def test_isindoor_key_from_real_garmin_summary_is_honored():
    """The bug fix: v0 read summary['is_indoor'] but real Garmin summaries
    use 'isIndoor' — that key never matched, so the summary-side check was
    dead code. Confirm the correct key now works even when the FIT-side
    flag alone wouldn't have caught it.
    """
    parsed = _parsed(sub_sport="road", is_indoor=False)
    assert classify({"isIndoor": True}, parsed) == "indoor"


def test_gravel_cycling_is_mtb():
    parsed = _parsed(sub_sport="gravel_cycling")
    assert classify({}, parsed) == "mtb"


def test_cyclocross_is_mtb():
    parsed = _parsed(sub_sport="cyclocross")
    assert classify({}, parsed) == "mtb"


def test_virtual_ride_with_gps_is_road():
    parsed = _parsed(sub_sport="virtual_ride", records=[RecordData(lat=6.2, lon=-75.5)])
    assert classify({}, parsed) == "road"


def test_virtual_ride_without_gps_is_indoor():
    parsed = _parsed(sub_sport="virtual_ride", records=[RecordData(lat=None, lon=None)])
    assert classify({}, parsed) == "indoor"


def test_plain_road_sub_sport_is_road():
    parsed = _parsed(sub_sport="road")
    assert classify({}, parsed) == "road"


def test_heuristic_fast_flat_is_road():
    # 40 km in 1h = 40 km/h, 100m gain over 40km = 2.5 m/km — road-like
    parsed = _parsed(sub_sport="", distance_m=40_000, elev_m=100, duration_s=3600)
    assert classify({}, parsed) == "road"


def test_heuristic_slow_hilly_is_mtb():
    # 15 km in 1h = 15 km/h, 600m gain over 15km = 40 m/km — mtb-like
    parsed = _parsed(sub_sport="", distance_m=15_000, elev_m=600, duration_s=3600)
    assert classify({}, parsed) == "mtb"


def test_no_signal_falls_through_to_other():
    parsed = _parsed(sub_sport="", distance_m=0, elev_m=0, duration_s=0)
    assert classify({}, parsed) == "other"
