"""Training-load metrics. Expected values are hand-computed, several
carried over from v0's tests (git tag `v0-legacy`)."""

from __future__ import annotations

import pytest
from soft_floyd_core.metrics.load import (
    RideLoad,
    RideLoadInput,
    normalized_power,
    ride_load,
)
from soft_floyd_core.metrics.zones import (
    lthr_from_max_hr,
    make_zones,
    resolve_lthr,
    time_in_zones,
    zone_for_hr,
)


def test_zone_boundaries_lthr_165():
    z = make_zones(165)
    assert z.z1_max == pytest.approx(132.0)  # 165 * 0.80
    assert z.z2_max == pytest.approx(146.85)  # 165 * 0.89
    assert z.z3_max == pytest.approx(155.1)  # 165 * 0.94
    assert z.z4_max == pytest.approx(163.35)  # 165 * 0.99


def test_zone_classification():
    z = make_zones(165)
    assert zone_for_hr(100.0, z) == 1  # < 132
    assert zone_for_hr(135.0, z) == 2  # 132 <= hr < 146.85
    assert zone_for_hr(150.0, z) == 3  # 146.85 <= hr < 155.1
    assert zone_for_hr(160.0, z) == 4  # 155.1 <= hr < 163.35
    assert zone_for_hr(165.0, z) == 5  # >= 163.35


def test_zone_boundary_is_inclusive_of_the_next_zone():
    z = make_zones(165)
    assert zone_for_hr(146.85, z) == 3
    assert zone_for_hr(132.0, z) == 2


def test_lthr_from_max_hr():
    assert lthr_from_max_hr(190) == 165  # 190 * 0.87 = 165.3


def test_time_in_zones_weights_samples_by_gap():
    z = make_zones(165)
    # First sample counts 1 s; then a 4 s gap, a 1 s gap, and a repeated
    # timestamp (clamped to 1 s). The None sample adds nothing.
    t = [0.0, 4.0, 5.0, 5.0, 6.0]
    hr = [100, 135, None, 150, 165]
    result = time_in_zones(t, hr, z)
    assert result == {1: 1.0, 2: 4.0, 3: 1.0, 4: 0.0, 5: 1.0}


def test_time_in_zones_without_hr_is_all_zero():
    z = make_zones(165)
    assert sum(time_in_zones([0.0, 1.0, 2.0], [None, None, None], z).values()) == 0.0


# ---- per-ride load -------------------------------------------------------


def _steady(seconds: int, power: int | None = None, hr: int | None = None):
    t = [float(i) for i in range(seconds)]
    return t, [power] * seconds, [hr] * seconds


def test_resolve_lthr_prefers_declared_then_max_hr():
    assert resolve_lthr(170, 190) == 170
    assert resolve_lthr(None, 190) == 165
    assert resolve_lthr(None, None) is None


def test_normalized_power_of_constant_power_is_that_power():
    t, p, _ = _steady(600, power=200)
    assert normalized_power(t, p) == pytest.approx(200.0)


def test_normalized_power_hand_computed_two_level_ride():
    # 30 s at 100 W then 30 s at 300 W. The 30 s rolling means run
    # (3200 + 200k) / 30 for k = -1..29 (31 values, 100 W up to 300 W);
    # the mean of their 4th powers, 4th-rooted, is 223.069 W — above the
    # 200 W average, which is the point of NP.
    t = [float(i) for i in range(60)]
    p = [100] * 30 + [300] * 30
    assert normalized_power(t, p) == pytest.approx(223.0694887793096)


def test_normalized_power_needs_thirty_seconds():
    t, p, _ = _steady(29, power=200)
    assert normalized_power(t, p) is None
    assert normalized_power([], []) is None


def test_normalized_power_skips_missing_samples_and_holds_last_value():
    t = [0.0, 10.0, 20.0, 40.0]
    p = [200, None, 200, 200]
    assert normalized_power(t, p) == pytest.approx(200.0)


def test_power_np_load_matches_tss_formula():
    t, p, _ = _steady(3600, power=200)
    ride = RideLoadInput(3600, power_verified=True, t_offset_s=t, power_w=p)
    result = ride_load(ride, ftp_watts=200, lthr=None)
    assert result.basis == "power_np"
    assert result.load == pytest.approx(100.0)  # an hour at FTP

    t, p, _ = _steady(3600, power=150)
    ride = RideLoadInput(3600, power_verified=True, t_offset_s=t, power_w=p)
    # IF 0.75 -> 3600 * 150 * 0.75 / (200 * 3600) * 100
    assert ride_load(ride, ftp_watts=200, lthr=None).load == pytest.approx(56.25)


def test_power_avg_when_ride_has_no_records():
    ride = RideLoadInput(3600, power_verified=True, avg_power_w=150)
    result = ride_load(ride, ftp_watts=200, lthr=None)
    assert result == RideLoad(pytest.approx(56.25), "power_avg")


def test_unverified_power_is_never_used_even_with_an_ftp():
    ride = RideLoadInput(3600, power_verified=False, avg_power_w=250, hr_verified=True, avg_hr=132)
    result = ride_load(ride, ftp_watts=200, lthr=165)
    assert result.basis == "hr_avg"


def test_no_ftp_means_no_power_basis():
    ride = RideLoadInput(3600, power_verified=True, avg_power_w=250)
    assert ride_load(ride, ftp_watts=None, lthr=None).basis == "duration"


def test_hr_zones_load_is_time_weighted():
    t, _, hr = _steady(3600, hr=135)  # LTHR 165: 135 is Z2 (40 per hour)
    ride = RideLoadInput(3600, hr_verified=True, t_offset_s=t, hr=hr)
    assert ride_load(ride, ftp_watts=None, lthr=165) == RideLoad(pytest.approx(40.0), "hr_zones")

    t = [float(i) for i in range(3600)]
    hr = [135] * 1800 + [160] * 1800  # half Z2, half Z4 (80 per hour)
    ride = RideLoadInput(3600, hr_verified=True, t_offset_s=t, hr=hr)
    assert ride_load(ride, ftp_watts=None, lthr=165).load == pytest.approx(60.0)


def test_hr_dropout_falls_back_to_average_hr():
    t = [float(i) for i in range(600)]  # 10 of 60 minutes of HR samples
    ride = RideLoadInput(3600, hr_verified=True, avg_hr=132, t_offset_s=t, hr=[135] * 600)
    result = ride_load(ride, ftp_watts=None, lthr=165)
    assert result.basis == "hr_avg"
    assert result.load == pytest.approx(64.0)  # (132 / 165)^2 * 100


def test_hr_avg_at_threshold_is_100_per_hour():
    ride = RideLoadInput(3600, hr_verified=True, avg_hr=165)
    assert ride_load(ride, ftp_watts=None, lthr=165).load == pytest.approx(100.0)


def test_nothing_verified_scores_duration_as_an_estimate():
    ride = RideLoadInput(7200, avg_power_w=250, avg_hr=150)  # neither verified
    assert ride_load(ride, ftp_watts=200, lthr=165) == RideLoad(pytest.approx(80.0), "duration")


def test_zero_duration_is_zero_load():
    assert ride_load(RideLoadInput(0), ftp_watts=200, lthr=165) == RideLoad(0.0, "duration")
