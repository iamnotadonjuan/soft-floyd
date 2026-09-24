"""Unit tests for the sensor capability model — the rule that keeps the
coach from talking about a signal the rider can't measure. See
docs/design-docs/sensor-capability-model.md.

Bike-mounted sensors (power/cadence/speed) live on Bike, not
RiderProfile (exec-plan 0004) — capability_tier() unions the profile's
HR flag with every Bike's sensors, so most fixtures here build a small
garage rather than setting flags directly on the profile.
"""

from soft_floyd_core.models import Bike, RiderProfile
from soft_floyd_core.profile.service import (
    available_metrics,
    capability_tier,
    capability_tier_for_bike,
)


def _profile(has_hr_monitor: bool = False, **overrides) -> RiderProfile:
    return RiderProfile(has_hr_monitor=has_hr_monitor, **overrides)


def _bike(**overrides) -> Bike:
    defaults = dict(has_power_meter=False, has_cadence_sensor=False, has_speed_sensor=False)
    defaults.update(overrides)
    return Bike(**defaults)


def test_power_meter_wins_the_tier():
    profile = _profile(has_hr_monitor=True)
    bikes = [_bike(has_power_meter=True)]
    assert capability_tier(profile, bikes) == "power"


def test_power_meter_on_any_one_bike_is_enough():
    """A garage with a power-meter road bike and a bare MTB still gives
    the profile-level tier power — the union, not the intersection."""
    profile = _profile(has_hr_monitor=True)
    bikes = [_bike(has_power_meter=True), _bike(has_power_meter=False)]
    assert capability_tier(profile, bikes) == "power"


def test_ftp_alone_without_any_power_meter_bike_does_not_grant_power_tier():
    """A stale ftp_watts value must never substitute for a real power-meter
    bike — rule 3."""
    profile = _profile(has_hr_monitor=True, ftp_watts=240)
    bikes = [_bike(has_power_meter=False)]
    tier = capability_tier(profile, bikes)
    assert tier == "hr"
    assert "ftp" not in available_metrics(tier)


def test_hr_monitor_only():
    profile = _profile(has_hr_monitor=True)
    bikes = [_bike()]
    tier = capability_tier(profile, bikes)
    assert tier == "hr"
    metrics = available_metrics(tier)
    assert "hr_zones" in metrics
    assert "ftp" not in metrics


def test_cadence_only_falls_back_from_hr_metrics():
    profile = _profile(has_hr_monitor=False)
    bikes = [_bike(has_cadence_sensor=True)]
    tier = capability_tier(profile, bikes)
    assert tier == "cadence"
    assert "hr_zones" not in available_metrics(tier)


def test_speed_only_also_yields_cadence_tier():
    profile = _profile(has_hr_monitor=False)
    bikes = [_bike(has_speed_sensor=True)]
    assert capability_tier(profile, bikes) == "cadence"


def test_no_sensors_and_no_bikes_is_basic_tier():
    profile = _profile(has_hr_monitor=False)
    tier = capability_tier(profile, [])
    assert tier == "basic"
    assert available_metrics(tier) == ["duration", "distance", "elevation_gain", "avg_speed"]


def test_power_tier_still_includes_hr_metrics():
    """Gaining a sensor only ever adds metrics, never removes HR ones."""
    profile = _profile(has_hr_monitor=True)
    bikes = [_bike(has_power_meter=True)]
    metrics = available_metrics(capability_tier(profile, bikes))
    assert "ftp" in metrics
    assert "hr_zones" in metrics


def test_capability_tier_for_bike_is_per_bike_not_garage_wide():
    """core belief 4 (downgrade visibly): a ride on the bare MTB should be
    read through 'hr', even though the garage overall is tier 'power'
    because of the road bike."""
    profile = _profile(has_hr_monitor=True)
    road = _bike(has_power_meter=True)
    mtb = _bike(has_power_meter=False)

    assert capability_tier_for_bike(road, profile) == "power"
    assert capability_tier_for_bike(mtb, profile) == "hr"


def test_capability_tier_for_bike_includes_rider_hr_regardless_of_bike():
    """The HR strap is worn by the rider, not mounted on a bike — it
    applies to every bike in the garage equally."""
    profile = _profile(has_hr_monitor=True)
    bare_bike = _bike()
    assert capability_tier_for_bike(bare_bike, profile) == "hr"
