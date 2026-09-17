"""Parses the real fixture files. sample_road.fit carries power+cadence
(a full-sensor rider); sample_mtb.fit and sample_indoor.fit deliberately
don't (a no-power-meter rider) — see tests/make_fixtures.py.
"""

from __future__ import annotations

from soft_floyd_core.activities.fit_parser import parse_fit


def test_road_fixture_has_power_and_cadence(road_fit_path):
    parsed = parse_fit(road_fit_path)
    assert parsed.session.sub_sport == "road"
    assert len(parsed.records) == 100
    assert any(r.power_w is not None for r in parsed.records)
    assert any(r.cadence is not None for r in parsed.records)
    assert parsed.session.avg_power_w == 195
    assert parsed.session.avg_cadence == 89
    assert parsed.laps[0].avg_power_w == 195


def test_mtb_fixture_has_no_power_or_cadence(mtb_fit_path):
    parsed = parse_fit(mtb_fit_path)
    assert parsed.session.sub_sport == "mountain"
    assert all(r.power_w is None for r in parsed.records)
    assert all(r.cadence is None for r in parsed.records)
    assert any(r.hr is not None for r in parsed.records)
    assert any(r.lat is not None for r in parsed.records)


def test_indoor_fixture_has_no_gps(indoor_fit_path):
    parsed = parse_fit(indoor_fit_path)
    assert parsed.session.is_indoor is True
    assert all(r.lat is None for r in parsed.records)
    assert any(r.hr is not None for r in parsed.records)


def test_lat_lon_are_plausible_degrees(road_fit_path):
    parsed = parse_fit(road_fit_path)
    for rec in parsed.records:
        assert -90 <= rec.lat <= 90
        assert -180 <= rec.lon <= 180
