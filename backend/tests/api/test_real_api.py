"""QA-005 real scientific E2E parity; skips in CI without large NASA raster.

Set LUNAR_REQUIRE_REAL_API=1 to fail if real data is unavailable.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lunar_api.app import create_app
from lunar_api.service import ScientificService
from lunar_engine.analysis.timeline import analyze_visibility_timeline
from lunar_engine.analysis.visibility import evaluate_terrain_visibility
from lunar_engine.coordinates.frame_transform import analyze_geometry_in_dem_frame
from lunar_engine.terrain.dem import DEFAULT_LOLA_METADATA, LunarDEM

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
@pytest.mark.requires_dem
@pytest.mark.requires_spice
def test_real_lola_spice_http_matches_direct_engine() -> None:
    raw = os.environ.get("LUNAR_DEM_FILE")
    available = (
        raw is not None
        and Path(raw).is_file()
        and os.environ.get("LUNAR_DEM_DATUM_CONFIRMED") == "1"
        and (ROOT / "data/spice/kernel-lock.json").is_file()
        and (ROOT / "data/spice/de421-frame-lock.json").is_file()
    )
    if not available:
        message = "Verified LOLA DEM and SPICE manifests required for API E2E"
        if os.environ.get("LUNAR_REQUIRE_REAL_API") == "1":
            pytest.fail(message)
        pytest.skip(message)
    assert raw is not None
    service = ScientificService(ROOT, dem_file=Path(raw), datum_confirmed=True)
    client = TestClient(create_app(service=service))
    instant = "2027-11-15T12:00:00Z"
    site = {
        "latitude_deg": -89.5,
        "longitude_deg": 45.0,
        "timestamp_utc": instant,
        "observer_height_m": 2.0,
        "terrain": {"max_distance_km": 2.0, "step_m": 80.0, "interpolation": "bilinear"},
    }

    with LunarDEM(Path(raw), metadata=replace(DEFAULT_LOLA_METADATA, datum_confirmed=True)) as dem:
        sample = dem.sample(-89.5, 45.0, interpolation="bilinear")
        direct_geo = analyze_geometry_in_dem_frame(
            -89.5,
            45.0,
            instant,
            terrain_elevation_km=(sample.elevation_m + 2.0) / 1000.0,
            repository_root=ROOT,
        )
        direct_site = evaluate_terrain_visibility(
            dem,
            -89.5,
            45.0,
            instant,
            observer_height_m=2.0,
            max_distance_km=2.0,
            step_m=80.0,
            interpolation="bilinear",
            repository_root=ROOT,
        )
        direct_timeline = analyze_visibility_timeline(
            -89.5,
            45.0,
            "2027-11-15T12:00:00Z",
            "2027-11-15T15:00:00Z",
            3600,
            observer_height_m=2.0,
            mode="terrain_aware",
            dem=dem,
            max_distance_km=2.0,
            step_m=80.0,
            interpolation="bilinear",
            repository_root=ROOT,
        )

    geometry_response = client.post(
        "/api/v1/geometry",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45.0,
            "timestamp_utc": instant,
            "observer_height_m": 2.0,
            "reference_surface_elevation_m": sample.elevation_m,
        },
    )
    assert geometry_response.status_code == 200, geometry_response.text
    assert geometry_response.json()["sun"]["azimuth_deg"] == direct_geo.sun.azimuth_deg
    assert geometry_response.json()["earth"]["elevation_deg"] == direct_geo.earth.elevation_deg
    assert geometry_response.json()["metadata"]["reference_frame"] == direct_geo.frame.value

    site_response = client.post("/api/v1/site-analysis", json=site)
    assert site_response.status_code == 200, site_response.text
    payload = site_response.json()
    assert payload["sun"]["status"] == direct_site.sun.status.value
    assert payload["earth"]["status"] == direct_site.earth.status.value
    assert payload["sun"]["terrain_horizon_deg"] == direct_site.sun.terrain_horizon_deg
    assert payload["metadata"]["terrain_dataset_id"] == direct_site.terrain_dataset_id
    assert payload["metadata"]["kernel_manifest_id"] == direct_site.kernel_manifest_id
    assert client.post("/api/v1/site-analysis", json=site).json() == payload

    timeline_response = client.post(
        "/api/v1/timeline",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45.0,
            "start_utc": "2027-11-15T12:00:00Z",
            "end_utc": "2027-11-15T15:00:00Z",
            "sampling_seconds": 3600,
            "observer_height_m": 2.0,
            "mode": "terrain_aware",
            "terrain": site["terrain"],
        },
    )
    assert timeline_response.status_code == 200, timeline_response.text
    body = timeline_response.json()
    assert len(body["samples"]) == len(direct_timeline.samples)
    assert body["samples"][0]["sun"] == direct_timeline.samples[0].sun.value
    assert body["samples"][0]["earth"] == direct_timeline.samples[0].earth.value
    assert body["metrics"]["illuminated_duration_seconds"] == (
        direct_timeline.metrics.illuminated_duration_seconds
    )
    assert body["metadata"]["terrain_dataset_id"] == direct_timeline.terrain_dataset_id
    assert body["metadata"]["reference_frame"] == direct_timeline.frame.value
    assert body["endpoint_semantics"] == direct_timeline.endpoint_semantics
