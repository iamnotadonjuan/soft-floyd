"""Golden tests for bike-type classifier rules in strict priority order."""

from coach.classify.bike_type import classify
from coach.ingest.fit_parser import ParsedFit, RecordData, SessionSummary


def _parsed(sub_sport="", is_indoor=False, speed_kmh=25.0, elev_per_km=10.0, has_gps=True):
    s = SessionSummary()
    s.sub_sport = sub_sport
    s.is_indoor = is_indoor
    distance_m = 10_000.0
    s.total_distance_m = distance_m
    s.total_elapsed_s = distance_m / (speed_kmh / 3.6)
    s.total_ascent_m = elev_per_km * (distance_m / 1000.0)

    records = []
    if has_gps:
        records = [RecordData(t_offset_s=0.0, lat=6.2, lon=-75.5)]

    p = ParsedFit(session=s)
    p.records = records
    return p


# Rule 1: is_indoor → indoor
def test_rule1_indoor_flag_overrides_all():
    p = _parsed(sub_sport="mountain", is_indoor=True)
    assert classify({}, p) == "indoor"


def test_rule1_indoor_from_summary():
    p = _parsed()
    assert classify({"is_indoor": True}, p) == "indoor"


# Rule 2: MTB sub-sports
def test_rule2_mountain():
    assert classify({}, _parsed(sub_sport="mountain")) == "mtb"


def test_rule2_cyclocross():
    assert classify({}, _parsed(sub_sport="cyclocross")) == "mtb"


def test_rule2_gravel():
    assert classify({}, _parsed(sub_sport="gravel_cycling")) == "mtb"


# Rule 3: road sub-sports
def test_rule3_road():
    assert classify({}, _parsed(sub_sport="road")) == "road"


def test_rule3_virtual_activity_with_gps():
    assert classify({}, _parsed(sub_sport="virtual_activity", has_gps=True)) == "road"


def test_rule3_virtual_activity_no_gps():
    assert classify({}, _parsed(sub_sport="virtual_activity", has_gps=False)) == "indoor"


def test_rule3_virtual_ride_with_gps():
    assert classify({}, _parsed(sub_sport="virtual_ride", has_gps=True)) == "road"


# Rule 4: heuristic
def test_rule4_high_speed_low_elev_is_road():
    # avg_speed > 22 km/h, elev_per_km < 15 → road
    p = _parsed(sub_sport="generic", speed_kmh=28.0, elev_per_km=8.0)
    assert classify({}, p) == "road"


def test_rule4_low_speed_high_elev_is_mtb():
    # avg_speed < 22 OR elev_per_km >= 15 → mtb
    p = _parsed(sub_sport="generic", speed_kmh=15.0, elev_per_km=30.0)
    assert classify({}, p) == "mtb"


def test_rule4_borderline_elev_is_road():
    p = _parsed(sub_sport="generic", speed_kmh=25.0, elev_per_km=14.9)
    assert classify({}, p) == "road"


# Rule 5: ambiguous → other
def test_rule5_zero_speed_is_other():
    p = ParsedFit(session=SessionSummary(total_elapsed_s=0, total_distance_m=0))
    assert classify({}, p) == "other"


# End-to-end: golden fixtures
def test_golden_road_fixture(road_parsed):
    assert classify({}, road_parsed) == "road"


def test_golden_mtb_fixture(mtb_parsed):
    assert classify({}, mtb_parsed) == "mtb"


def test_golden_indoor_fixture(indoor_parsed):
    assert classify({}, indoor_parsed) == "indoor"
