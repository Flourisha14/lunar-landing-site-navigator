"""Independent analytical projection cases from Snyder's south polar equations."""

import math

import pytest

from lunar_engine.terrain.dem import (
    south_polar_inverse,
    south_polar_stereographic_xy,
)


def test_south_pole_is_projection_origin():
    assert south_polar_stereographic_xy(-90, 157) == pytest.approx((0, 0), abs=1e-9)
    assert south_polar_inverse(0, 0) == (-90, 0)


@pytest.mark.parametrize(
    "longitude,expected",
    [
        (0, (0, 1)),
        (90, (1, 0)),
        (180, (0, -1)),
        (270, (-1, 0)),
    ],
)
def test_independent_cardinal_axes(longitude, expected):
    x, y = south_polar_stereographic_xy(-89, longitude)
    rho = 2 * 1737400 * math.tan(math.radians(0.5))
    assert (x, y) == pytest.approx(tuple(rho * value for value in expected), abs=1e-7)


def test_projection_roundtrip_near_south_pole():
    for lat, lon in [(-89.5, 45), (-85, 179), (-80.01, -170)]:
        x, y = south_polar_stereographic_xy(lat, lon)
        lat2, lon2 = south_polar_inverse(x, y)
        assert lat2 == pytest.approx(lat, abs=1e-10)
        assert lon2 == pytest.approx(lon, abs=1e-10)


def test_invalid_north_query_rejected():
    with pytest.raises(ValueError):
        south_polar_stereographic_xy(50, 0)
