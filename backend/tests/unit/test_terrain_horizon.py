"""QA-004: independent analytical spherical cases and synthetic DEM fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, pi, radians, sin, sqrt, tan

import pytest

from lunar_engine.core.conventions import LUNAR_REFERENCE_RADIUS_KM, LunarFrame, LunarLocation
from lunar_engine.terrain.dem import TerrainDataError
from lunar_engine.terrain.horizon import (
    destination_on_sphere,
    obstruction_angle_deg,
    terrain_horizon_profile,
    terrain_horizon_ray,
)


@dataclass(frozen=True)
class FakeMetadata:
    frame: LunarFrame = LunarFrame.ME_DE421
    dataset_id: str = "analytical_spherical_fixture"
    reference_radius_m: float = 1_737_400.0


@dataclass(frozen=True)
class FakeSample:
    location: LunarLocation
    elevation_m: float
    dataset_id: str


class AnalyticDEM:
    """Controlled heights along a meridian, no raster sampling artifacts."""

    def __init__(
        self, ridges: tuple[tuple[float, float, float], ...] = (), missing_km: float | None = None
    ):
        self.metadata = FakeMetadata()
        self.ridges = ridges
        self.missing_km = missing_km

    def sample(
        self, latitude_deg: float, longitude_deg: float, *, interpolation: str = "bilinear"
    ) -> FakeSample:
        if interpolation not in {"nearest", "bilinear"}:
            raise ValueError("bad interpolation")
        # Observer is (-89.0, 0). Distance along due-north meridian.
        arc_km = (latitude_deg + 89.0) * pi / 180.0 * LUNAR_REFERENCE_RADIUS_KM
        if self.missing_km is not None and arc_km > self.missing_km:
            raise TerrainDataError("deliberate synthetic gap")
        height = max((h for lo, hi, h in self.ridges if lo <= arc_km <= hi), default=0.0)
        return FakeSample(
            LunarLocation(latitude_deg, longitude_deg, 0.0, LunarFrame.ME_DE421),
            height,
            self.metadata.dataset_id,
        )


def test_analytical_equal_sphere_angle_below_horizontal() -> None:
    distance = 10.0
    expected = -degrees(distance / (2 * LUNAR_REFERENCE_RADIUS_KM))
    assert obstruction_angle_deg(distance, 0, 0) == pytest.approx(expected, abs=1e-11)


def test_analytical_ridge_geometry_from_independent_triangle() -> None:
    distance = 1.0
    target_radius = LUNAR_REFERENCE_RADIUS_KM + 0.2
    theta = distance / LUNAR_REFERENCE_RADIUS_KM
    observer_radius = LUNAR_REFERENCE_RADIUS_KM
    # Independent law of cosines, with altitude recovered from chord angle.
    chord = sqrt(
        observer_radius**2
        + target_radius**2
        - 2 * observer_radius * target_radius * (1 - 2 * sin(theta / 2) ** 2)
    )
    sin_elevation = (target_radius**2 - observer_radius**2 - chord**2) / (
        2 * observer_radius * chord
    )
    expected = degrees(atan2(sin_elevation, sqrt(1 - sin_elevation**2)))
    assert obstruction_angle_deg(distance, 200, 0) == pytest.approx(expected, abs=1e-7)


def test_flat_spherical_horizon_stays_negative() -> None:
    result = terrain_horizon_ray(
        AnalyticDEM(), -89, 0, 0, observer_height_m=0, max_distance_km=5, step_m=100
    )
    assert result.complete
    assert result.horizon_elevation_deg is not None
    assert result.horizon_elevation_deg < 0
    assert result.controlling_point is not None
    assert result.controlling_point.arc_distance_km == pytest.approx(0.1)


def test_single_ridge_and_observer_height() -> None:
    dem = AnalyticDEM(((0.99, 1.01, 200),))
    low = terrain_horizon_ray(dem, -89, 0, 0, observer_height_m=0, max_distance_km=2, step_m=100)
    high = terrain_horizon_ray(dem, -89, 0, 0, observer_height_m=100, max_distance_km=2, step_m=100)
    assert low.controlling_point is not None
    assert low.controlling_point.arc_distance_km == pytest.approx(1.0)
    assert low.horizon_elevation_deg == pytest.approx(obstruction_angle_deg(1, 200, 0), abs=1e-7)
    assert high.horizon_elevation_deg is not None and low.horizon_elevation_deg is not None
    assert high.horizon_elevation_deg < low.horizon_elevation_deg


def test_multiple_ridges_choose_highest_angle_not_height() -> None:
    dem = AnalyticDEM(((0.99, 1.01, 100), (2.99, 3.01, 200)))
    ray = terrain_horizon_ray(dem, -89, 0, 0, observer_height_m=0, max_distance_km=4, step_m=100)
    assert ray.controlling_point is not None
    # Nearer 100 m ridge subtends a larger angle than 200 m at 3 km.
    assert ray.controlling_point.arc_distance_km == pytest.approx(1.0)


def test_distance_and_resolution_sensitivity() -> None:
    dem = AnalyticDEM(((0.95, 1.05, 200),))
    short = terrain_horizon_ray(dem, -89, 0, 0, max_distance_km=0.8, step_m=100)
    coarse = terrain_horizon_ray(dem, -89, 0, 0, max_distance_km=2, step_m=300)
    fine = terrain_horizon_ray(dem, -89, 0, 0, max_distance_km=2, step_m=50)
    assert short.horizon_elevation_deg is not None
    assert fine.horizon_elevation_deg is not None
    assert fine.horizon_elevation_deg > short.horizon_elevation_deg
    assert coarse.horizon_elevation_deg is not None
    assert coarse.horizon_elevation_deg < fine.horizon_elevation_deg


def test_incomplete_data_is_not_clear() -> None:
    result = terrain_horizon_ray(
        AnalyticDEM(missing_km=1.5), -89, 0, 0, max_distance_km=3, step_m=250
    )
    assert result.coverage == "incomplete"
    assert result.horizon_elevation_deg is None
    assert result.first_missing_distance_km is not None
    assert result.controlling_point is not None
    assert result.samples_completed < result.samples_requested


def test_polar_and_longitude_geometry() -> None:
    pole = LunarLocation(-90, 90, 0, LunarFrame.ME_DE421)
    assert pole.longitude_deg == 0
    for bearing in (0, 90, 180, 270):
        lat, lon = destination_on_sphere(pole, bearing, 2)
        assert -90 < lat < -89
        assert -180 <= lon < 180
    wrapped = LunarLocation(-89, 179.999, 0, LunarFrame.ME_DE421)
    lat, lon = destination_on_sphere(wrapped, 90, 10)
    assert -90 < lat < -88
    assert -180 <= lon < 180


def test_profile_azimuths_deterministic_and_distinct() -> None:
    dem = AnalyticDEM()
    one = terrain_horizon_profile(dem, -89, 0, azimuth_step_deg=90, max_distance_km=1, step_m=250)
    two = terrain_horizon_profile(dem, -89, 0, azimuth_step_deg=90, max_distance_km=1, step_m=250)
    assert one == two
    assert [r.azimuth_deg for r in one.rays] == [0, 90, 180, 270]
    assert one.complete and one.frame is LunarFrame.ME_DE421


def test_unsupported_frame_rejected_without_implicit_conversion() -> None:
    dem = AnalyticDEM()
    dem.metadata = FakeMetadata(frame=LunarFrame.ME)
    with pytest.raises(ValueError, match="DE421-native"):
        terrain_horizon_ray(dem, -89, 0, 0)


@pytest.mark.parametrize(
    "options",
    [
        {"observer_height_m": -1},
        {"max_distance_km": 0},
        {"step_m": 0},
        {"step_m": 1e-6},
        {"azimuth_deg": float("nan")},
        {"max_distance_km": pi * LUNAR_REFERENCE_RADIUS_KM},
    ],
)
def test_invalid_ray_parameters(options: dict[str, float]) -> None:
    bearing = options.pop("azimuth_deg", 0.0)
    with pytest.raises(ValueError):
        terrain_horizon_ray(AnalyticDEM(), -89, 0, bearing, **options)


def test_invalid_profile_step() -> None:
    with pytest.raises(ValueError):
        terrain_horizon_profile(AnalyticDEM(), -89, 0, azimuth_step_deg=0)


def test_finite_and_horizontal_angle_limits() -> None:
    assert -90 < obstruction_angle_deg(1.0, 0, 0) < 0
    assert 0 < obstruction_angle_deg(1.0, 1000, 0) < 90
    assert tan(radians(obstruction_angle_deg(1, 1000, 0))) > 0
