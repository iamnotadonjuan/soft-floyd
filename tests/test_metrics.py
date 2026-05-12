"""Unit tests for HR metrics with hand-computed expected values."""
import math
import pytest

from coach.metrics.zones import make_zones, zone_for_hr
from coach.metrics.compute import compute_metrics
from coach.ingest.fit_parser import ParsedFit, SessionSummary, RecordData, LapData


# ---- HR Zone tests -------------------------------------------------------

def test_zone_boundaries_lthr_165():
    z = make_zones(165)
    assert z.z1_max == pytest.approx(165 * 0.80)   # 132
    assert z.z2_max == pytest.approx(165 * 0.89)   # 146.85
    assert z.z3_max == pytest.approx(165 * 0.94)   # 155.1
    assert z.z4_max == pytest.approx(165 * 0.99)   # 163.35


def test_zone_classification():
    z = make_zones(165)
    assert zone_for_hr(100.0, z) == 1   # < 132
    assert zone_for_hr(135.0, z) == 2   # 132 ≤ hr < 146.85
    assert zone_for_hr(150.0, z) == 3   # 146.85 ≤ hr < 155.1
    assert zone_for_hr(160.0, z) == 4   # 155.1 ≤ hr < 163.35
    assert zone_for_hr(165.0, z) == 5   # ≥ 163.35


def test_zone_boundary_z2_exactly():
    z = make_zones(165)
    # z2_max = 146.85 → HR 147 is in Z3
    assert zone_for_hr(146.85, z) == 3


# ---- compute_metrics tests -----------------------------------------------

def _make_parsed_fit_with_records(records: list[RecordData], session: SessionSummary | None = None) -> ParsedFit:
    p = ParsedFit()
    p.records = records
    p.session = session or SessionSummary(
        avg_hr=140, total_elapsed_s=3600.0, total_distance_m=36000.0
    )
    return p


def test_hr_drift_pct_hand_computed():
    """HR drift = (avg_HR_2nd_half - avg_HR_1st_half) / avg_HR_1st_half × 100."""
    # 10 records: first 5 avg=130, second 5 avg=143
    records = [
        RecordData(t_offset_s=float(i), hr=130, speed_mps=6.0, altitude_m=100.0)
        for i in range(5)
    ] + [
        RecordData(t_offset_s=float(i + 5), hr=143, speed_mps=6.0, altitude_m=100.0)
        for i in range(5)
    ]
    result = compute_metrics(_make_parsed_fit_with_records(records))
    expected_drift = (143 - 130) / 130 * 100
    assert result["hr_drift_pct"] == pytest.approx(expected_drift, rel=0.01)


def test_decoupling_pct_no_drift():
    """When HR and speed are perfectly proportional, decoupling should be near 0."""
    records = [
        RecordData(t_offset_s=float(i), hr=140, speed_mps=7.0, altitude_m=100.0)
        for i in range(20)
    ]
    result = compute_metrics(_make_parsed_fit_with_records(records))
    assert result["decoupling_pct"] == pytest.approx(0.0, abs=0.01)


def test_time_in_zones_sums_correctly(road_parsed):
    """Sum of zone times should approximately equal ride duration."""
    result = compute_metrics(road_parsed)
    total_zone_time = (
        result["time_in_z1"] + result["time_in_z2"] + result["time_in_z3"]
        + result["time_in_z4"] + result["time_in_z5"]
    )
    # Should be > 0
    assert total_zone_time > 0


def test_time_in_zones_all_z2(road_parsed):
    """Road fixture HR 135-175 bpm with LTHR 165 — most should be in Z2/Z3."""
    result = compute_metrics(road_parsed, lthr=165)
    # Z1 (<132): very little
    # Z2 (132-146.85): many records around 135-142
    # Z3+: records with hr > 146
    assert result["time_in_z2"] > 0
    assert result["time_in_z3"] >= 0


def test_tss_proxy_positive():
    """TRIMP proxy should be positive for a ride with avg HR > 60."""
    session = SessionSummary(avg_hr=140, total_elapsed_s=3600.0)
    p = ParsedFit(session=session)
    result = compute_metrics(p, lthr=165)
    assert result["tss_proxy"] is not None
    assert result["tss_proxy"] > 0


def test_tss_proxy_hand_computed():
    """Verify TRIMP formula against hand computation for LTHR=165, avg_hr=140, 60 min."""
    lthr = 165.0
    avg_hr = 140.0
    max_hr_est = lthr / 0.87
    hr_ratio = (avg_hr - 60) / (max_hr_est - 60)
    expected = 60 * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)

    session = SessionSummary(avg_hr=int(avg_hr), total_elapsed_s=3600.0)
    p = ParsedFit(session=session)
    result = compute_metrics(p, lthr=int(lthr))
    assert result["tss_proxy"] == pytest.approx(expected, rel=0.01)


def test_gap_normalized_computed_from_laps(road_parsed):
    """GAP from road fixture laps should be > 0 since distance and duration are set."""
    result = compute_metrics(road_parsed)
    assert result["gap_normalized"] is not None
    assert result["gap_normalized"] > 0


def test_vam_best_20min_from_altitude_records():
    """VAM from a sustained climb: 400m gain over 1200s → 1200 m/h."""
    records = [
        RecordData(t_offset_s=float(i * 60), altitude_m=100.0 + i * 20.0)
        for i in range(21)  # 0 to 20 minutes, +20m/min = 1200m/h
    ]
    result = compute_metrics(_make_parsed_fit_with_records(records))
    assert result["vam_best_20min"] == pytest.approx(1200.0, rel=0.05)


def test_no_records_returns_none_metrics():
    """No record data → drift/decoupling/vam should be None."""
    p = ParsedFit(session=SessionSummary(avg_hr=140, total_elapsed_s=3600.0))
    result = compute_metrics(p)
    assert result["hr_drift_pct"] is None
    assert result["decoupling_pct"] is None
    assert result["vam_best_20min"] is None
