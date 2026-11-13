"""Spherical lunar transforms: geometry and frame safety."""

from math import sqrt

import pytest

from lunar_engine.coordinates.spherical import (
    cartesian_to_geographic,
    enu_basis,
    enu_to_fixed,
    fixed_position_to_enu,
    fixed_to_enu,
    geographic_to_cartesian,
    surface_normal,
)
from lunar_engine.core.conventions import LunarFrame, LunarLocation, MoonFixedVector


@pytest.mark.unit
def test_round_trip_and_poles() -> None:
    for lat, lon in ((0, 0), (30, -120), (90, 10), (-90, 175), (0, 180)):
        source = LunarLocation(lat, lon, 0.5)
        recovered = cartesian_to_geographic(geographic_to_cartesian(source))
        assert recovered.latitude_deg == pytest.approx(source.latitude_deg, abs=1e-12)
        assert recovered.longitude_deg == pytest.approx(source.longitude_deg, abs=1e-12)
        assert recovered.elevation_km == pytest.approx(source.elevation_km, abs=1e-9)


@pytest.mark.unit
def test_basis_is_orthonormal_and_right_handed() -> None:
    for lat, lon in ((0, 0), (45, 125), (90, 0), (-90, 0)):
        east, north, up = enu_basis(LunarLocation(lat, lon, 0))
        for v in (east, north, up):
            assert sum(x * x for x in v) == pytest.approx(1, abs=1e-14)
        assert sum(a * b for a, b in zip(east, north, strict=True)) == pytest.approx(0, abs=1e-14)
        cross = (
            east[1] * north[2] - east[2] * north[1],
            east[2] * north[0] - east[0] * north[2],
            east[0] * north[1] - east[1] * north[0],
        )
        assert cross == pytest.approx(up, abs=1e-14)
        normal = surface_normal(LunarLocation(lat, lon, 0))
        assert (normal.x_km, normal.y_km, normal.z_km) == pytest.approx(up)


@pytest.mark.unit
def test_enu_inverse_and_position_origin() -> None:
    site = LunarLocation(-89.0, 25.0, 0)
    vector = MoonFixedVector(1, 2, 3, LunarFrame.ME)
    local = fixed_to_enu(vector, site)
    recovered = enu_to_fixed(local)
    assert (recovered.x_km, recovered.y_km, recovered.z_km) == pytest.approx((1, 2, 3))
    assert sqrt(sum(x * x for x in (local.east_km, local.north_km, local.up_km))) == pytest.approx(
        sqrt(14)
    )
    origin = fixed_position_to_enu(geographic_to_cartesian(site), site)
    assert (origin.east_km, origin.north_km, origin.up_km) == pytest.approx((0, 0, 0), abs=1e-12)


@pytest.mark.unit
def test_frame_mismatch_and_origin_rejected() -> None:
    site = LunarLocation(0, 0, 0)
    with pytest.raises(ValueError):
        fixed_to_enu(MoonFixedVector(1, 0, 0, LunarFrame.PA), site)
    with pytest.raises(ValueError):
        cartesian_to_geographic(MoonFixedVector(0, 0, 0, LunarFrame.ME))
