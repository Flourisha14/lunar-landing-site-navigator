"""Unit tests for standards only; not astronomical reference validation."""

from datetime import UTC

import pytest

from lunar_engine.core.conventions import (
    LUNAR_REFERENCE_RADIUS_KM,
    ElevationDatum,
    LunarFrame,
    LunarLocation,
    MoonFixedVector,
    ScientificMetadata,
    normalize_longitude_deg,
    parse_utc_timestamp,
)
from tests.numerical import numerically_close


@pytest.mark.unit
def test_reference_radius(lunar_reference_radius_km: float) -> None:
    assert lunar_reference_radius_km == LUNAR_REFERENCE_RADIUS_KM == 1737.4


@pytest.mark.unit
def test_frame_names_are_distinct(nominal_moon_frame: LunarFrame) -> None:
    assert nominal_moon_frame is LunarFrame.ME
    assert len({item.value for item in LunarFrame}) == 3
    assert LunarFrame.PA != LunarFrame.ME


@pytest.mark.unit
def test_longitude_and_polar_canonicalization() -> None:
    assert normalize_longitude_deg(180.0) == -180.0
    assert normalize_longitude_deg(360.0) == 0.0
    assert LunarLocation(-90.0, 135.0, 0.0).longitude_deg == 0.0
    assert LunarLocation(90.0, -43.0, 0.0).longitude_deg == 0.0


@pytest.mark.unit
def test_invalid_values_rejected() -> None:
    with pytest.raises(ValueError):
        LunarLocation(90.01, 0.0, 0.0)
    with pytest.raises(ValueError):
        LunarLocation(0.0, float("nan"), 0.0)
    with pytest.raises(ValueError):
        MoonFixedVector(float("inf"), 0.0, 0.0, LunarFrame.ME)
    with pytest.raises(ValueError):
        LunarLocation(0.0, 0.0, -1737.4)


@pytest.mark.unit
def test_explicit_metadata() -> None:
    meta = ScientificMetadata(LunarFrame.ME, ElevationDatum.MEAN_RADIUS_1737_4_KM)
    assert meta.frame.value == "MOON_ME_DE440_ME421"
    assert meta.distance_unit.value == "km"
    assert meta.angle_unit.value == "deg"


@pytest.mark.unit
def test_utc_inputs() -> None:
    assert parse_utc_timestamp("2026-11-14T01:23:45.123Z").tzinfo is UTC
    for invalid in ("2026-11-14T01:23:45", "2026-11-14T01:23:45+05:30", "2026-12-31T23:59:60Z"):
        with pytest.raises(ValueError):
            parse_utc_timestamp(invalid)


@pytest.mark.unit
def test_tolerance_utility() -> None:
    assert numerically_close(1.0, 1.0 + 1e-13)
    assert not numerically_close(float("nan"), 1.0)
    assert not numerically_close(1.0, 2.0)
