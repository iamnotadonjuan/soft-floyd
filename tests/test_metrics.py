"""Training-load metrics. Expected values are hand-computed, several
carried over from v0's tests (git tag `v0-legacy`)."""

from __future__ import annotations

import pytest
from soft_floyd_core.metrics.zones import (
    lthr_from_max_hr,
    make_zones,
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
