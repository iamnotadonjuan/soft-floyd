"""Tests for rag/chunking.py and rag/retriever.py (no OpenAI calls)."""

from __future__ import annotations

import datetime

from coach.rag.chunking import (
    _fmt_duration,
    _zone_pct,
    build_activity_card,
    build_wellness_chunk,
)
from coach.store.models import Activity, Metrics, WellnessDaily

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_activity(**kwargs) -> Activity:
    defaults = dict(
        id=1,
        start_time=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=datetime.UTC),
        sport="cycling",
        sub_sport="road",
        is_indoor=False,
        bike_type="road",
        distance_m=62_300,
        duration_s=7_680,  # 2h08
        elev_gain_m=845,
        avg_hr=142,
        max_hr=178,
        tss_proxy=95.0,
    )
    defaults.update(kwargs)
    return Activity(**defaults)


def _make_metrics(**kwargs) -> Metrics:
    defaults = dict(
        activity_id=1,
        decoupling_pct=3.2,
        hr_drift_pct=1.8,
        time_in_z1=614,
        time_in_z2=3_917,
        time_in_z3=2_150,
        time_in_z4=922,
        time_in_z5=77,
        vam_best_20min=870,
        gap_normalized=5.2,
    )
    defaults.update(kwargs)
    return Metrics(**defaults)


def _make_wellness(**kwargs) -> WellnessDaily:
    defaults = dict(
        date=datetime.date(2026, 4, 15),
        hrv_overnight=54,
        sleep_score=82,
        body_battery_low=42,
        body_battery_high=89,
        resting_hr=48,
    )
    defaults.update(kwargs)
    return WellnessDaily(**defaults)


# ---------------------------------------------------------------------------
# _fmt_duration
# ---------------------------------------------------------------------------


def test_fmt_duration_hours():
    assert _fmt_duration(7_680) == "2h08"


def test_fmt_duration_minutes_only():
    assert _fmt_duration(2700) == "45min"


# ---------------------------------------------------------------------------
# _zone_pct
# ---------------------------------------------------------------------------


def test_zone_pct_sums_to_100():
    m = _make_metrics()
    result = _zone_pct(m)
    # Extract percentages
    import re

    nums = [int(x) for x in re.findall(r"(\d+)%", result)]
    assert sum(nums) == 100


def test_zone_pct_no_metrics():
    assert _zone_pct(None) == "no zone data"


def test_zone_pct_all_zero():
    m = _make_metrics(time_in_z1=0, time_in_z2=0, time_in_z3=0, time_in_z4=0, time_in_z5=0)
    assert _zone_pct(m) == "no zone data"


# ---------------------------------------------------------------------------
# build_activity_card — determinism and key content
# ---------------------------------------------------------------------------


def test_card_is_deterministic():
    act = _make_activity()
    m = _make_metrics()
    w = _make_wellness()
    c1 = build_activity_card(act, [], m, w)
    c2 = build_activity_card(act, [], m, w)
    assert c1 == c2


def test_card_contains_date():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "2026-04-15" in card


def test_card_contains_bike_type():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "road" in card


def test_card_contains_distance():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "62.3 km" in card


def test_card_contains_duration():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "2h08" in card


def test_card_contains_hr():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "142" in card
    assert "178" in card


def test_card_contains_decoupling():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "Decoupling" in card
    assert "3.2%" in card


def test_card_contains_vam():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "VAM" in card
    assert "870" in card


def test_card_contains_wellness():
    act = _make_activity()
    w = _make_wellness()
    card = build_activity_card(act, [], _make_metrics(), w)
    assert "HRV 54" in card
    assert "sleep score 82" in card
    assert "42→89" in card


def test_card_no_wellness():
    act = _make_activity()
    card = build_activity_card(act, [], _make_metrics(), None)
    assert "Wellness" not in card


def test_card_narrative_z2():
    """High Z2 ride should produce Z2 endurance narrative."""
    m = _make_metrics(
        time_in_z1=100,
        time_in_z2=5000,
        time_in_z3=200,
        time_in_z4=100,
        time_in_z5=0,
    )
    card = build_activity_card(_make_activity(), [], m, None)
    assert "Z2" in card


def test_card_indoor_narrative():
    act = _make_activity(bike_type="indoor", is_indoor=True)
    m = _make_metrics(time_in_z1=100, time_in_z2=3000, time_in_z3=200, time_in_z4=0, time_in_z5=0)
    card = build_activity_card(act, [], m, None)
    assert "Indoor" in card or "indoor" in card


# ---------------------------------------------------------------------------
# build_wellness_chunk
# ---------------------------------------------------------------------------


def test_wellness_chunk_empty():
    result = build_wellness_chunk([], datetime.date(2026, 4, 7))
    assert "2026-04-07" in result
    assert "no wellness data" in result


def test_wellness_chunk_has_week_date():
    w = [_make_wellness()]
    result = build_wellness_chunk(w, datetime.date(2026, 4, 7))
    assert "2026-04-07" in result


def test_wellness_chunk_has_hrv():
    w = [_make_wellness(hrv_overnight=55), _make_wellness(hrv_overnight=57)]
    result = build_wellness_chunk(w, datetime.date(2026, 4, 7))
    assert "HRV" in result
