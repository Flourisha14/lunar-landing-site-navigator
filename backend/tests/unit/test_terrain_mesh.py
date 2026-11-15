"""FE-005B: real raster transformations, curvature and strict coverage."""

from __future__ import annotations

import numpy as np
import pytest

from lunar_engine.terrain.dem import (
    LunarDEM,
    TerrainMetadata,
    south_polar_stereographic_xy,
)
from lunar_engine.terrain.mesh import (
    TerrainOutsideCoverage,
    generate_terrain_mesh,
)

rasterio = pytest.importorskip("rasterio")
CRS = pytest.importorskip("rasterio.crs").CRS
from_origin = pytest.importorskip("rasterio.transform").from_origin


@pytest.fixture
def dem_path(tmp_path):
    cx, cy = south_polar_stereographic_xy(-89.0, 0.0)
    path = tmp_path / "test_lola.tif"
    data = np.full((13, 13), 100.0, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=13,
        height=13,
        count=1,
        dtype="float32",
        nodata=-9999.0,
        transform=from_origin(cx - 520, cy + 520, 80, 80),
        crs=CRS.from_proj4("+proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=1737400 +units=m +no_defs"),
    ) as dst:
        dst.write(data, 1)
    return path


def open_dem(path):
    return LunarDEM(path, TerrainMetadata("unit_lola", path.name, datum_confirmed=True))


def test_flat_height_has_correct_orientation_and_moon_curvature(dem_path):
    with open_dem(dem_path) as dem:
        mesh = generate_terrain_mesh(dem, -89, 0, radius_m=160, sample_step_m=160)
    assert mesh.status == "complete"
    assert mesh.grid_side == 3
    assert len(mesh.vertices) == 9
    assert len(mesh.indices) == 24
    assert mesh.center_elevation_m == pytest.approx(100)
    assert mesh.vertices[4] == pytest.approx((0, 0, 0), abs=1e-6)
    assert mesh.vertices[0][0] == pytest.approx(-160, abs=0.1)
    assert mesh.vertices[0][2] == pytest.approx(160, abs=0.1)
    assert mesh.vertices[0][1] < 0  # Spherical curvature under tangent plane.
    a, b, c = (mesh.vertices[i] for i in mesh.indices[:3])
    ab = np.subtract(b, a)
    ac = np.subtract(c, a)
    assert np.cross(ab, ac)[1] > 0  # Up-facing triangles.
    assert mesh.metadata["datum_confirmed"] is True


def test_rejects_site_outside_raster(dem_path):
    with open_dem(dem_path) as dem:
        with pytest.raises(TerrainOutsideCoverage):
            generate_terrain_mesh(dem, -80, 0, radius_m=160)


def test_no_excessive_sampling(dem_path):
    with open_dem(dem_path) as dem:
        with pytest.raises(ValueError, match="exceeds"):
            generate_terrain_mesh(dem, -89, 0, radius_m=5000, sample_step_m=80)
        with pytest.raises(ValueError, match="radius"):
            generate_terrain_mesh(dem, -89, 0, radius_m=100)


def test_edge_yields_partial_coverage_without_fabricating_vertices(dem_path):
    cx, cy = south_polar_stereographic_xy(-89, 0)
    from lunar_engine.terrain.dem import south_polar_inverse

    lat, lon = south_polar_inverse(cx + 320, cy)
    with open_dem(dem_path) as dem:
        mesh = generate_terrain_mesh(dem, lat, lon, radius_m=320, sample_step_m=160)
    assert mesh.status == "partial_coverage"
    assert 0 < mesh.valid_samples < mesh.requested_samples
    assert len(mesh.indices) > 0
    assert max(mesh.indices) < len(mesh.vertices)
