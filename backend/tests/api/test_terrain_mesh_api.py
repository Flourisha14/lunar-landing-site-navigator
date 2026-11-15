"""FE-005B HTTP contract: no SPICE dependency for terrain geometry."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lunar_api.app import create_app
from lunar_api.service import ScientificService
import numpy as np
rasterio = pytest.importorskip("rasterio")
from rasterio.crs import CRS
from rasterio.transform import from_origin
from lunar_engine.terrain.dem import south_polar_stereographic_xy


@pytest.fixture
def dem_path(tmp_path):
    x, y = south_polar_stereographic_xy(-89, 0)
    path = tmp_path / "api_lola.tif"
    data = np.full((13, 13), 100, dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", height=13, width=13, count=1,
        dtype="float32", nodata=-9999.0,
        crs=CRS.from_proj4(
            "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=1737400 +units=m +no_defs"
        ),
        transform=from_origin(x - 520, y + 520, 80, 80),
    ) as dst:
        dst.write(data, 1)
    return path


def test_missing_dem_returns_503(tmp_path):
    service = ScientificService(tmp_path)
    response = TestClient(create_app(service=service)).get(
        "/api/v1/terrain/mesh", params={"latitude_deg": -89.5, "longitude_deg": 45}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "scientific_data_unavailable"


def test_validation_blocks_invalid_requests(tmp_path):
    service = ScientificService(tmp_path)
    client = TestClient(create_app(service=service))
    response = client.get(
        "/api/v1/terrain/mesh",
        params={"latitude_deg": 100, "longitude_deg": 45},
    )
    assert response.status_code == 422


def test_selected_site_outside_coverage_returns_explicit_code(dem_path, tmp_path):
    service = ScientificService(tmp_path, dem_file=dem_path, datum_confirmed=True)
    response = TestClient(create_app(service=service)).get(
        "/api/v1/terrain/mesh",
        params={"latitude_deg": -80, "longitude_deg": 0, "radius_m": 160},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "outside_coverage"


def test_http_mesh_provenance_and_geometry(dem_path, tmp_path):
    service = ScientificService(tmp_path, dem_file=dem_path, datum_confirmed=True)
    response = TestClient(create_app(service=service)).get(
        "/api/v1/terrain/mesh",
        params={
            "latitude_deg": -89,
            "longitude_deg": 0,
            "radius_m": 160,
            "sample_step_m": 160,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "complete"
    assert body["coordinate_frame"] == "local_east_up_north"
    assert len(body["vertices"]) == 9
    assert len(body["indices"]) == 24
    assert body["metadata"]["dataset_id"] == "GSFC_PGDA_LOLA_SOUTH_POLE_LDEM_80S_80MPP_ADJ"
    assert body["metadata"]["datum_confirmed"] is True
