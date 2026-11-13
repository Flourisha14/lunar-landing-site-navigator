"""Properties complement, but cannot replace, independent golden cases."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lunar_engine.coordinates.spherical import cartesian_to_geographic, geographic_to_cartesian
from lunar_engine.core.conventions import LunarLocation


@pytest.mark.property
@given(
    latitude=st.floats(min_value=-89.9, max_value=89.9, allow_nan=False),
    longitude=st.floats(min_value=-179.9, max_value=179.9, allow_nan=False),
    elevation=st.floats(min_value=-10, max_value=10, allow_nan=False),
)
def test_geographic_roundtrip(latitude: float, longitude: float, elevation: float) -> None:
    location = LunarLocation(latitude, longitude, elevation)
    recovered = cartesian_to_geographic(geographic_to_cartesian(location))
    assert recovered.latitude_deg == pytest.approx(latitude, abs=1e-11)
    assert recovered.longitude_deg == pytest.approx(longitude, abs=1e-11)
    assert recovered.elevation_km == pytest.approx(elevation, abs=1e-9)
