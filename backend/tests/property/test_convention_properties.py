"""Deterministic property-based invariants, not scientific ground truth."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lunar_engine.core.conventions import LunarLocation, normalize_longitude_deg

finite_longitudes = st.floats(
    min_value=-1e6,
    max_value=1e6,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)


@pytest.mark.property
@given(finite_longitudes)
def test_normalized_range_and_idempotence(longitude: float) -> None:
    normalized = normalize_longitude_deg(longitude)
    assert -180.0 <= normalized < 180.0
    assert normalize_longitude_deg(normalized) == pytest.approx(normalized, abs=1e-9)


@pytest.mark.property
@given(
    st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
    finite_longitudes,
)
def test_location_normalizes_longitude(latitude: float, longitude: float) -> None:
    site = LunarLocation(latitude, longitude, 0.0)
    assert -180.0 <= site.longitude_deg < 180.0
    if abs(latitude) == 90.0:
        assert site.longitude_deg == 0.0
