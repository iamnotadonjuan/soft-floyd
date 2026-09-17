"""detect_sensor_streams — the one function that decides what a ride
actually recorded (docs/design-docs/sensor-capability-model.md rule 1).
"""

from __future__ import annotations

import ast
import inspect

from soft_floyd_core.activities import sensors
from soft_floyd_core.activities.fit_parser import ParsedFit, RecordData
from soft_floyd_core.activities.sensors import detect_sensor_streams


def test_all_zero_power_channel_is_not_power_data():
    """A paired-but-idle sensor slot some head units write as all-zero
    must not be mistaken for a present power meter."""
    parsed = ParsedFit(records=[RecordData(power_w=0), RecordData(power_w=0)])
    assert detect_sensor_streams(parsed).power is False


def test_all_zero_cadence_channel_is_not_cadence_data():
    parsed = ParsedFit(records=[RecordData(cadence=0), RecordData(cadence=0)])
    assert detect_sensor_streams(parsed).cadence is False


def test_one_nonzero_sample_is_enough():
    parsed = ParsedFit(records=[RecordData(power_w=0), RecordData(power_w=180)])
    assert detect_sensor_streams(parsed).power is True


def test_hr_and_speed_follow_the_same_rule():
    parsed = ParsedFit(records=[RecordData(hr=0, speed_mps=0.0), RecordData(hr=142, speed_mps=7.2)])
    streams = detect_sensor_streams(parsed)
    assert streams.hr is True
    assert streams.speed is True


def test_gps_needs_both_lat_and_lon():
    parsed = ParsedFit(records=[RecordData(lat=6.2, lon=None), RecordData(lat=None, lon=-75.5)])
    assert detect_sensor_streams(parsed).gps is False

    parsed_both = ParsedFit(records=[RecordData(lat=6.2, lon=-75.5)])
    assert detect_sensor_streams(parsed_both).gps is True


def test_empty_record_list_is_all_false():
    streams = detect_sensor_streams(ParsedFit(records=[]))
    assert streams == type(streams)(power=False, hr=False, cadence=False, speed=False, gps=False)


def test_sensors_module_never_imports_rider_profile():
    """Static guard for the module docstring's contract: this module must
    never IMPORT RiderProfile/profile.service/Settings — per-activity
    sensor presence must never be influenced by what the rider's profile
    declares. A real import would be a rule-1 violation waiting to happen.

    Checks actual import statements (via ast), not a raw substring scan,
    so mentioning these names in prose (like this docstring) can't trip it.
    """
    tree = ast.parse(inspect.getsource(sensors))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
            imported_names.update(alias.name for alias in node.names)

    banned = {"RiderProfile", "soft_floyd_core.profile", "profile", "Settings"}
    assert not (imported_names & banned), f"forbidden import(s): {imported_names & banned}"
