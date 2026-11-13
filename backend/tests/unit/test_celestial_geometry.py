"""Independent axis-aligned geometry and boundary tests without SPICE kernels."""

from math import isclose, sqrt

import pytest

from lunar_engine.astronomy.ephemeris import EphemerisPosition
from lunar_engine.astronomy.geometry import local_direction
from lunar_engine.core.conventions import LunarFrame, LunarLocation, MoonFixedVector


def _target(x: float, y: float, z: float) -> EphemerisPosition:
    return EphemerisPosition(
        "SUN",
        "2027-11-15T12:00:00.000000Z",
        0.0,
        MoonFixedVector(x, y, z, LunarFrame.ME),
        "synthetic-axis-case",
    )


@pytest.mark.unit
def test_independent_enu_cardinal_reference() -> None:
    """At (0,0), +X radial up, +Y east, +Z north by definition."""
    site = LunarLocation(0.0, 0.0, 0.0)
    east = local_direction(_target(1737.4, 100, 0), site)
    north = local_direction(_target(1737.4, 0, 100), site)
    zenith = local_direction(_target(1837.4, 0, 0), site)
    nadir = local_direction(_target(1637.4, 0, 0), site)
    assert east.azimuth_deg == pytest.approx(90.0)
    assert north.azimuth_deg == pytest.approx(0.0)
    assert east.elevation_deg == pytest.approx(0.0, abs=1e-12)
    assert north.elevation_deg == pytest.approx(0.0, abs=1e-12)
    assert not east.geometric_visible
    assert zenith.azimuth_deg is None
    assert zenith.elevation_deg == pytest.approx(90)
    assert zenith.geometric_visible
    assert nadir.azimuth_deg is None
    assert nadir.elevation_deg == pytest.approx(-90)
    assert not nadir.geometric_visible


@pytest.mark.unit
def test_known_horizon_crossings() -> None:
    site = LunarLocation(0.0, 0.0, 0.0)
    above = local_direction(_target(1738.4, 100.0, 0), site)
    below = local_direction(_target(1736.4, 100.0, 0), site)
    assert above.geometric_visible
    assert not below.geometric_visible
    assert above.elevation_deg == pytest.approx(0.5729386976834859, abs=1e-10)
    assert below.elevation_deg == pytest.approx(-0.5729386976834859, abs=1e-10)


@pytest.mark.unit
def test_direction_norm_and_distance() -> None:
    site = LunarLocation(-90, 120, 0)
    direction = local_direction(_target(1000, 2000, -1737.4), site)
    norm = sqrt(sum(v * v for v in (direction.east_unit, direction.north_unit, direction.up_unit)))
    assert isclose(norm, 1.0, abs_tol=1e-14)
    assert direction.range_km == pytest.approx(sqrt(5_000_000), abs=1e-9)
    assert 0 <= (direction.azimuth_deg or 0) < 360
    assert -90 <= direction.elevation_deg <= 90


@pytest.mark.unit
def test_invalid_frame_or_coincident_target() -> None:
    site = LunarLocation(0, 0, 0)
    wrong = EphemerisPosition(
        "EARTH",
        "2027-11-15T12:00:00.000000Z",
        0.0,
        MoonFixedVector(2000, 0, 0, LunarFrame.PA),
        "synthetic",
    )
    with pytest.raises(ValueError, match="same Moon-fixed frame"):
        local_direction(wrong, site)
    with pytest.raises(ValueError, match="coincides"):
        local_direction(_target(1737.4, 0, 0), site)
