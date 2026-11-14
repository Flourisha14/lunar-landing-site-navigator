"""QA-004: actual NASA LOLA regional raster, supplied locally via environment.

This test is skipped on CI without the non-redistributed dataset. Set
LUNAR_REQUIRE_REAL_DEM=1 to fail instead of skip for a dedicated validation run.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from lunar_engine.core.conventions import LunarFrame
from lunar_engine.terrain.dem import DEFAULT_LOLA_METADATA, LunarDEM
from lunar_engine.terrain.horizon import (
    obstruction_angle_deg,
    terrain_horizon_profile,
    terrain_horizon_ray,
)


@pytest.mark.integration
@pytest.mark.requires_dem
def test_real_lola_horizon_and_provenance() -> None:
    raw = os.environ.get("LUNAR_DEM_FILE")
    if not raw or not Path(raw).is_file() or os.environ.get("LUNAR_DEM_DATUM_CONFIRMED") != "1":
        reason = (
            "Real LOLA DEM and acknowledged datum required: "
            "LUNAR_DEM_FILE, LUNAR_DEM_DATUM_CONFIRMED=1"
        )
        if os.environ.get("LUNAR_REQUIRE_REAL_DEM") == "1":
            pytest.fail(reason)
        pytest.skip(reason)
    path = Path(raw)
    before = path.stat().st_size, path.stat().st_mtime_ns
    metadata = replace(DEFAULT_LOLA_METADATA, datum_confirmed=True)
    with LunarDEM(path, metadata=metadata) as dem:
        site = dem.sample(-89.5, 45.0, interpolation="nearest")
        assert site.location.frame is LunarFrame.ME_DE421
        assert site.elevation_m == pytest.approx(-405.3225402832031, abs=1e-5)
        ray = terrain_horizon_ray(
            dem, -89.5, 45, 0, max_distance_km=2, step_m=160, interpolation="nearest"
        )
        rerun = terrain_horizon_ray(
            dem, -89.5, 45, 0, max_distance_km=2, step_m=160, interpolation="nearest"
        )
        assert ray == rerun
        assert ray.frame is LunarFrame.ME_DE421
        assert ray.dataset_id == metadata.dataset_id
        assert ray.complete
        assert ray.coverage == "complete"
        assert ray.horizon_elevation_deg is not None

        point = ray.controlling_point
        assert point is not None

        analytical = obstruction_angle_deg(
            point.arc_distance_km,
            point.elevation_m,
            site.elevation_m,
            2.0,
        )

        assert ray.horizon_elevation_deg == pytest.approx(
            analytical,
            abs=1e-8,
        )

        # Generate the four-cardinal-azimuth horizon profile.
        profile = terrain_horizon_profile(
            dem,
            -89.5,
            45.0,
            azimuth_step_deg=90.0,
            max_distance_km=2.0,
            step_m=160.0,
            interpolation="nearest",
        )

        assert len(profile.rays) == 4
        assert profile.frame is LunarFrame.ME_DE421

        # QA-004: The documented demonstration site has complete
        # DEM coverage over the tested 2 km search distance.
        assert profile.complete
        assert all(ray.complete for ray in profile.rays)
        assert all(ray.coverage == "complete" for ray in profile.rays)
        assert all(ray.horizon_elevation_deg is not None for ray in profile.rays)

        # Observer-height sensitivity:
        # Higher observers must not see the same terrain at a
        # greater apparent elevation angle.
        height_angles = []

        for observer_height in (2.0, 5.0, 10.0):
            height_ray = terrain_horizon_ray(
                dem,
                -89.5,
                45.0,
                180.0,
                observer_height_m=observer_height,
                max_distance_km=2.0,
                step_m=80.0,
                interpolation="bilinear",
            )

            assert height_ray.complete
            assert height_ray.horizon_elevation_deg is not None

            height_angles.append(height_ray.horizon_elevation_deg)

        assert height_angles[0] > height_angles[1]
        assert height_angles[1] > height_angles[2]

        # Search-distance sensitivity:
        # Extending the search using the same sampling grid and
        # interpolation must not decrease the maximum obstruction.
        distance_angles = []

        for max_distance in (2.0, 5.0, 10.0):
            distance_ray = terrain_horizon_ray(
                dem,
                -89.5,
                45.0,
                90.0,
                observer_height_m=2.0,
                max_distance_km=max_distance,
                step_m=80.0,
                interpolation="bilinear",
            )

            assert distance_ray.complete
            assert distance_ray.horizon_elevation_deg is not None

            distance_angles.append(distance_ray.horizon_elevation_deg)

        assert distance_angles[0] <= distance_angles[1] + 1e-9
        assert distance_angles[1] <= distance_angles[2] + 1e-9
    assert (path.stat().st_size, path.stat().st_mtime_ns) == before
