"""QA-005 contract tests: no fabricated astronomical golden values."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from lunar_api.app import create_app
from lunar_api.schemas import GeometryRequest, SiteAnalysisRequest, TimelineRequest
from lunar_api.service import ScientificService


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(service=ScientificService(tmp_path)))


def test_health(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["science_available"] is False


def test_metadata(client: TestClient) -> None:
    res = client.get("/api/v1/metadata")
    assert res.status_code == 200
    assert res.json()["modes"] == ["geometric", "terrain_aware"]
    assert res.json()["terrain_configured"] is False


@pytest.mark.parametrize("latitude,longitude", [(91, 45), (-91, 45), ("nan", 45), (0, "nan")])
def test_invalid_coordinates(client: TestClient, latitude: object, longitude: object) -> None:
    res = client.post(
        "/api/v1/geometry",
        json={
            "latitude_deg": latitude,
            "longitude_deg": longitude,
            "timestamp_utc": "2027-11-15T12:00:00Z",
        },
    )
    assert res.status_code == 422


def test_invalid_timestamp(client: TestClient) -> None:
    res = client.post(
        "/api/v1/geometry",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "timestamp_utc": "2027-11-15T12:00:00+00:00",
        },
    )
    assert res.status_code == 422


def test_missing_kernels_is_503(client: TestClient) -> None:
    res = client.post(
        "/api/v1/geometry",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "timestamp_utc": "2027-11-15T12:00:00Z",
        },
    )
    assert res.status_code == 503
    assert res.json()["code"] == "scientific_data_unavailable"


def test_missing_dem_is_503(tmp_path: Path) -> None:
    # Manifests exist, DEM does not; no geometric fallback allowed.
    (tmp_path / "data" / "spice").mkdir(parents=True)
    (tmp_path / "data" / "spice" / "kernel-lock.json").write_text("{}")
    (tmp_path / "data" / "spice" / "de421-frame-lock.json").write_text("{}")
    with TestClient(create_app(service=ScientificService(tmp_path))) as client:
        res = client.post(
            "/api/v1/site-analysis",
            json={
                "latitude_deg": -89.5,
                "longitude_deg": 45,
                "timestamp_utc": "2027-11-15T12:00:00Z",
            },
        )
    assert res.status_code == 503


def test_invalid_timeline_interval(client: TestClient) -> None:
    res = client.post(
        "/api/v1/timeline",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "start_utc": "2027-11-15T12:00:00Z",
            "end_utc": "2027-11-15T11:00:00Z",
            "sampling_seconds": 3600,
        },
    )
    assert res.status_code == 422


def test_workload_rejected(client: TestClient) -> None:
    res = client.post(
        "/api/v1/timeline",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "start_utc": "2027-11-15T00:00:00Z",
            "end_utc": "2027-11-16T00:00:00Z",
            "sampling_seconds": 1,
        },
    )
    assert res.status_code == 422


def test_schema_rejects_unknown_request_field() -> None:
    with pytest.raises(ValidationError):
        GeometryRequest.model_validate(
            {
                "latitude_deg": -89.5,
                "longitude_deg": 45,
                "timestamp_utc": "2027-11-15T12:00:00Z",
                "unknown": "surprise",
            }
        )


def test_schema_canonical_utc() -> None:
    r = GeometryRequest(latitude_deg=-89.5, longitude_deg=45, timestamp_utc="2027-11-15T12:00:00Z")
    assert r.timestamp_utc == "2027-11-15T12:00:00.000000Z"


def test_reject_geometric_terrain_mix() -> None:
    with pytest.raises(ValidationError):
        SiteAnalysisRequest.model_validate(
            {
                "latitude_deg": -89.5,
                "longitude_deg": 45,
                "timestamp_utc": "2027-11-15T12:00:00Z",
                "mode": "geometric",
                "terrain": {},
            }
        )


def test_reject_noninteger_sampling() -> None:
    with pytest.raises(ValidationError):
        TimelineRequest.model_validate(
            {
                "latitude_deg": -89.5,
                "longitude_deg": 45,
                "start_utc": "2027-11-15T00:00:00Z",
                "end_utc": "2027-11-16T00:00:00Z",
                "sampling_seconds": 3600.5,
            }
        )


def test_cors(tmp_path: Path) -> None:
    client = TestClient(create_app(service=ScientificService(tmp_path)))
    resp = client.options(
        "/api/v1/geometry",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert all(
        p in paths
        for p in (
            "/api/v1/health",
            "/api/v1/metadata",
            "/api/v1/geometry",
            "/api/v1/site-analysis",
            "/api/v1/timeline",
        )
    )


def test_excessive_terrain_ray_workload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/site-analysis",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "timestamp_utc": "2027-11-15T12:00:00Z",
            "mode": "terrain_aware",
            "terrain": {"max_distance_km": 1000.0, "step_m": 1.0},
        },
    )
    assert response.status_code == 422
