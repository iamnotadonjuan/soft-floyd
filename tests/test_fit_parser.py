"""FIT parser golden tests using real fixture files."""


def test_road_session_fields(road_parsed):
    s = road_parsed.session
    assert s.sport == "cycling"
    assert s.sub_sport == "road"
    assert s.is_indoor is False
    assert s.avg_hr == 142
    assert s.max_hr == 178
    assert abs(s.total_distance_m - 62400.0) < 1.0
    assert abs(s.total_elapsed_s - 9000.0) < 1.0
    assert abs(s.total_ascent_m - 850.0) < 1.0


def test_road_lap_count(road_parsed):
    assert len(road_parsed.laps) == 2


def test_road_lap_fields(road_parsed):
    lap = road_parsed.laps[0]
    assert lap.lap_index == 0
    assert abs(lap.distance_m - 31200.0) < 1.0
    assert abs(lap.duration_s - 4500.0) < 1.0
    assert lap.avg_hr == 142
    assert abs(lap.elev_gain_m - 425.0) < 1.0


def test_road_record_count(road_parsed):
    assert len(road_parsed.records) == 100


def test_road_records_have_gps(road_parsed):
    records_with_gps = [r for r in road_parsed.records if r.lat is not None]
    assert len(records_with_gps) == 100


def test_road_records_have_hr(road_parsed):
    records_with_hr = [r for r in road_parsed.records if r.hr is not None]
    assert len(records_with_hr) == 100


def test_mtb_session(mtb_parsed):
    s = mtb_parsed.session
    assert s.sport == "cycling"
    assert s.sub_sport == "mountain"
    assert s.is_indoor is False
    assert s.avg_hr == 158


def test_mtb_lap_count(mtb_parsed):
    assert len(mtb_parsed.laps) == 1


def test_mtb_record_count(mtb_parsed):
    assert len(mtb_parsed.records) == 40


def test_indoor_session(indoor_parsed):
    s = indoor_parsed.session
    assert s.sport == "cycling"
    assert s.is_indoor is True
    assert s.avg_hr == 148


def test_indoor_lap_count(indoor_parsed):
    assert len(indoor_parsed.laps) == 3


def test_indoor_no_gps(indoor_parsed):
    records_with_gps = [r for r in indoor_parsed.records if r.lat is not None]
    assert len(records_with_gps) == 0


def test_fit_path_preserved(road_parsed, road_fit_path):
    assert road_parsed.fit_path == road_fit_path
