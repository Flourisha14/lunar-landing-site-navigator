"""BE-011/BE-012: deterministic synthetic terrain + mocked astronomical directions."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from pathlib import Path

import pytest

from lunar_engine.analysis.visibility import VisibilityStatus, evaluate_terrain_visibility
from lunar_engine.astronomy.geometry import CelestialDirection, CelestialGeometry
from lunar_engine.core.conventions import (
    LUNAR_REFERENCE_RADIUS_KM,
    LunarFrame,
    LunarLocation,
    MoonFixedVector,
)
from lunar_engine.terrain.dem import TerrainDataError

EPOCH = "2027-11-15T12:00:00.000000Z"


@dataclass(frozen=True)
class FakeMetadata:
    frame: LunarFrame = LunarFrame.ME_DE421
    dataset_id: str = "synthetic_visibility_test"
    reference_radius_m: float = 1_737_400.0


@dataclass(frozen=True)
class FakeSample:
    location: LunarLocation
    elevation_m: float
    dataset_id: str


class FakeDEM:
    def __init__(self, missing_after_km: float | None = None):
        self.metadata = FakeMetadata()
        self.missing_after_km = missing_after_km

    def sample(
        self, latitude_deg: float, longitude_deg: float, *, interpolation: str = "bilinear"
    ) -> FakeSample:
        distance_km = (latitude_deg + 89.0) * pi / 180.0 * LUNAR_REFERENCE_RADIUS_KM
        if self.missing_after_km is not None and distance_km > self.missing_after_km:
            raise TerrainDataError("synthetic missing raster")
        return FakeSample(
            LunarLocation(latitude_deg, longitude_deg, 0.0, LunarFrame.ME_DE421),
            0.0,
            self.metadata.dataset_id,
        )


def target(
    body: str,
    elevation: float,
    azimuth: float | None = 0.0,
    *,
    frame: LunarFrame = LunarFrame.ME_DE421,
) -> CelestialDirection:
    return CelestialDirection(
        body=body,
        azimuth_deg=azimuth,
        elevation_deg=elevation,
        east_unit=0.0,
        north_unit=1.0,
        up_unit=0.0,
        range_km=1e6,
        geometric_visible=elevation > 0,
        position_moon_fixed=MoonFixedVector(1e6, 0.0, 0.0, frame),
    )


def provider(sun: CelestialDirection, earth: CelestialDirection, *, site_shift_km: float = 0.0):
    calls: list[tuple[str, float]] = []

    def fake(
        latitude_deg: float,
        longitude_deg: float,
        timestamp_utc: str,
        *,
        terrain_elevation_km: float,
        repository_root: Path,
    ) -> CelestialGeometry:
        calls.append((timestamp_utc, terrain_elevation_km))
        return CelestialGeometry(
            site=LunarLocation(
                latitude_deg,
                longitude_deg,
                terrain_elevation_km + site_shift_km,
                LunarFrame.ME_DE421,
            ),
            timestamp_utc=timestamp_utc,
            et_seconds=0.0,
            frame=LunarFrame.ME_DE421,
            kernel_manifest_id="synthetic_ephemeris",
            sun=sun,
            earth=earth,
        )

    return fake, calls


def evaluate(
    sun_elev: float,
    earth_elev: float,
    *,
    dem: FakeDEM | None = None,
    height: float = 2.0,
    sun_az: float | None = 0.0,
    earth_az: float | None = 0.0,
):
    fake, calls = provider(target("SUN", sun_elev, sun_az), target("EARTH", earth_elev, earth_az))
    result = evaluate_terrain_visibility(
        dem or FakeDEM(),
        -89.0,
        0.0,
        EPOCH,
        observer_height_m=height,
        max_distance_km=2.0,
        step_m=100.0,
        repository_root=Path("."),
        geometry_provider=fake,
    )
    assert len(calls) == 1  # No duplicated SPICE/astronomical request.
    assert calls[0][1] == pytest.approx(height / 1000.0)
    return result


def test_sun_above_terrain_horizon() -> None:
    result = evaluate(10.0, 10.0)
    assert result.sun.status is VisibilityStatus.VISIBLE
    assert result.sun.visible is True
    assert result.sun.clearance_deg is not None and result.sun.clearance_deg > 0


def test_sun_below_terrain_horizon() -> None:
    result = evaluate(-20.0, 10.0)
    assert result.sun.status is VisibilityStatus.OBSTRUCTED
    assert result.sun.visible is False


def test_earth_above_terrain_horizon() -> None:
    assert evaluate(10.0, 5.0).earth.status is VisibilityStatus.VISIBLE


def test_earth_below_terrain_horizon() -> None:
    assert evaluate(10.0, -20.0).earth.status is VisibilityStatus.OBSTRUCTED


def test_exact_boundary_is_obstructed() -> None:
    # The same production horizon API computes the synthetic angle; this test
    # validates strict comparison, not independent spherical geometry.
    from lunar_engine.terrain.horizon import terrain_horizon_ray

    dem = FakeDEM()
    ray = terrain_horizon_ray(dem, -89.0, 0.0, 0, max_distance_km=2, step_m=100)
    assert ray.horizon_elevation_deg is not None
    result = evaluate(ray.horizon_elevation_deg, ray.horizon_elevation_deg, dem=dem)
    assert result.sun.status is VisibilityStatus.OBSTRUCTED


def test_negative_celestial_elevation_can_be_visible_over_depressed_terrain() -> None:
    # Above the sampled terrain horizon, even when below the ideal tangent plane.
    from lunar_engine.terrain.horizon import terrain_horizon_ray

    dem = FakeDEM()
    ray = terrain_horizon_ray(dem, -89, 0, 0, max_distance_km=2, step_m=100)
    assert ray.horizon_elevation_deg is not None and ray.horizon_elevation_deg < 0
    assert evaluate(ray.horizon_elevation_deg / 2, 1, dem=dem, height=2).sun.visible is True


def test_missing_dem_is_unknown_not_obstructed() -> None:
    result = evaluate(20.0, 20.0, dem=FakeDEM(missing_after_km=0.5))
    for body in (result.sun, result.earth):
        assert body.status is VisibilityStatus.UNKNOWN
        assert body.visible is None
        assert body.terrain_horizon_deg is None
        assert body.reason == "incomplete_dem_coverage"
        assert body.horizon is not None and not body.horizon.complete


def test_unknown_azimuth_is_not_invented() -> None:
    result = evaluate(90.0, 1.0, sun_az=None)
    assert result.sun.status is VisibilityStatus.UNKNOWN
    assert result.sun.reason == "undefined_celestial_azimuth"
    assert result.earth.status is VisibilityStatus.VISIBLE


def test_observer_height_can_change_visibility() -> None:
    from lunar_engine.terrain.horizon import terrain_horizon_ray

    dem = FakeDEM()
    low = terrain_horizon_ray(dem, -89, 0, 0, observer_height_m=2, max_distance_km=2, step_m=100)
    high = terrain_horizon_ray(dem, -89, 0, 0, observer_height_m=10, max_distance_km=2, step_m=100)
    assert low.horizon_elevation_deg is not None and high.horizon_elevation_deg is not None
    assert high.horizon_elevation_deg < low.horizon_elevation_deg
    midpoint = (high.horizon_elevation_deg + low.horizon_elevation_deg) / 2
    assert evaluate(midpoint, midpoint, dem=dem, height=2).sun.visible is False
    assert evaluate(midpoint, midpoint, dem=dem, height=10).sun.visible is True


def test_repeated_calls_are_deterministic() -> None:
    assert evaluate(1.0, -1.0) == evaluate(1.0, -1.0)


@pytest.mark.parametrize(
    "lat,lon,when",
    [
        (91.0, 0.0, EPOCH),
        (-91.0, 0.0, EPOCH),
        (-89.0, float("nan"), EPOCH),
        (-89.0, 0.0, "not-a-timestamp"),
        (-89.0, 0.0, "2027-11-15T12:00:00+00:00"),
    ],
)
def test_reject_invalid_coordinates_or_timestamps(lat: float, lon: float, when: str) -> None:
    fake, _ = provider(target("SUN", 10.0), target("EARTH", 10.0))
    with pytest.raises(ValueError):
        evaluate_terrain_visibility(
            FakeDEM(), lat, lon, when, repository_root=Path("."), geometry_provider=fake
        )


def test_reject_wrong_dem_frame() -> None:
    dem = FakeDEM()
    dem.metadata = FakeMetadata(frame=LunarFrame.ME)
    fake, _ = provider(target("SUN", 10), target("EARTH", 10))
    with pytest.raises(ValueError, match="MOON_ME_DE421"):
        evaluate_terrain_visibility(
            dem, -89, 0, EPOCH, repository_root=Path("."), geometry_provider=fake
        )


def test_reject_wrong_celestial_frame() -> None:
    fake, _ = provider(target("SUN", 10, frame=LunarFrame.ME), target("EARTH", 10))
    with pytest.raises(ValueError, match="MOON_ME_DE421"):
        evaluate_terrain_visibility(
            FakeDEM(), -89, 0, EPOCH, repository_root=Path("."), geometry_provider=fake
        )


def test_reject_mismatched_observer_geometry() -> None:
    fake, _ = provider(target("SUN", 10), target("EARTH", 10), site_shift_km=0.02)
    with pytest.raises(ValueError, match="Astronomical site"):
        evaluate_terrain_visibility(
            FakeDEM(), -89, 0, EPOCH, repository_root=Path("."), geometry_provider=fake
        )


def test_repository_root_required_for_real_geometry() -> None:
    with pytest.raises(ValueError, match="repository_root"):
        evaluate_terrain_visibility(FakeDEM(), -89, 0, EPOCH)


def test_invalid_height() -> None:
    fake, _ = provider(target("SUN", 10), target("EARTH", 10))
    with pytest.raises(ValueError, match="height"):
        evaluate_terrain_visibility(
            FakeDEM(),
            -89,
            0,
            EPOCH,
            observer_height_m=-1,
            repository_root=Path("."),
            geometry_provider=fake,
        )
