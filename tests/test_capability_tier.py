"""Unit tests for the sensor capability model — the rule that keeps the
coach from talking about a signal the rider can't measure. See
docs/design-docs/sensor-capability-model.md.
"""

from soft_floyd_core.models import RiderProfile
from soft_floyd_core.profile.service import available_metrics, capability_tier


def _profile(**overrides) -> RiderProfile:
    defaults = dict(
        has_power_meter=False,
        has_hr_monitor=False,
        has_cadence_sensor=False,
        has_speed_sensor=False,
    )
    defaults.update(overrides)
    return RiderProfile(**defaults)


def test_power_meter_wins_the_tier():
    profile = _profile(has_power_meter=True, has_hr_monitor=True)
    assert capability_tier(profile) == "power"


def test_ftp_alone_without_the_flag_does_not_grant_power_tier():
    """A stale ftp_watts value must never substitute for the hardware flag."""
    profile = _profile(has_power_meter=False, has_hr_monitor=True, ftp_watts=240)
    assert capability_tier(profile) == "hr"
    assert "ftp" not in available_metrics(capability_tier(profile))


def test_hr_monitor_only():
    profile = _profile(has_hr_monitor=True)
    tier = capability_tier(profile)
    assert tier == "hr"
    metrics = available_metrics(tier)
    assert "hr_zones" in metrics
    assert "ftp" not in metrics


def test_cadence_only_falls_back_from_hr_metrics():
    profile = _profile(has_cadence_sensor=True)
    tier = capability_tier(profile)
    assert tier == "cadence"
    assert "hr_zones" not in available_metrics(tier)


def test_speed_only_also_yields_cadence_tier():
    profile = _profile(has_speed_sensor=True)
    assert capability_tier(profile) == "cadence"


def test_no_sensors_is_basic_tier():
    profile = _profile()
    tier = capability_tier(profile)
    assert tier == "basic"
    assert available_metrics(tier) == ["duration", "distance", "elevation_gain", "avg_speed"]


def test_power_tier_still_includes_hr_metrics():
    """Gaining a sensor only ever adds metrics, never removes HR ones."""
    profile = _profile(has_power_meter=True, has_hr_monitor=True)
    metrics = available_metrics(capability_tier(profile))
    assert "ftp" in metrics
    assert "hr_zones" in metrics
