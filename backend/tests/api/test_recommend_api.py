"""HTTP request validation and recommendation response contracts without fabricated physics."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lunar_api.app import create_app
from lunar_api.recommend_schemas import RecommendSitesRequest, RecommendSitesResponse
from lunar_api.service import ScientificService
from lunar_engine.analysis.recommendations import MissionConstraints, ScreenedSite


def request_body():
    return {
        "start_utc": "2027-11-15T00:00:00Z",
        "duration_hours": 2,
        "sampling_seconds": 3600,
        "candidate_count": 2,
        "max_recommendations": 1,
        "terrain": {"max_distance_km": 2, "step_m": 160, "interpolation": "bilinear"},
    }


def test_request_contract_duration_and_limits() -> None:
    req = RecommendSitesRequest.model_validate(request_body())
    assert req.end_utc == "2027-11-15T02:00:00.000000Z"
    assert req.constraints.to_engine() == MissionConstraints()


def test_invalid_request_returns_422() -> None:
    app = create_app(service=ScientificService(Path("/missing")))
    client = TestClient(app)
    for change in (
        {"candidate_count": 0},
        {"candidate_count": 13},
        {"max_recommendations": 3},
        {"sampling_seconds": 0},
        {"duration_hours": -1},
        {"constraints": {"min_sun_fraction": 1.5}},
        {"start_utc": "bad"},
    ):
        response = client.post("/api/v1/recommend-sites", json={**request_body(), **change})
        assert response.status_code == 422


def test_no_dem_returns_503_not_geometric_fallback() -> None:
    client = TestClient(create_app(service=ScientificService(Path("/missing"))))
    response = client.post("/api/v1/recommend-sites", json=request_body())
    assert response.status_code == 503
    assert response.json()["code"] == "scientific_data_unavailable"


def test_openapi_contract() -> None:
    client = TestClient(create_app(service=ScientificService(Path("/missing"))))
    schema = client.get("/openapi.json").json()
    post = schema["paths"]["/api/v1/recommend-sites"]["post"]
    assert "requestBody" in post
    assert "200" in post["responses"]
    assert "RecommendSitesResponse" in schema["components"]["schemas"]


def test_serializer_is_renderer_independent() -> None:
    from lunar_api.recommend_schemas import RecommendationConstraints, TerrainConfig

    site = ScreenedSite(
        -89.5,
        45.0,
        "SUITABLE",
        0.625,
        0.75,
        0.5,
        0.6,
        0,
        0,
        0,
        0,
        0,
        2,
        {"min_sun_fraction": True},
        "Meets constraints",
        "test-dem",
        "MOON_ME_DE421",
        "test-spice",
    )
    result = RecommendSitesResponse(
        start_utc="2027-11-15T00:00:00Z",
        end_utc="2027-11-15T02:00:00Z",
        sampling_seconds=3600,
        constraints=RecommendationConstraints(),
        terrain=TerrainConfig(),
        candidate_count=1,
        requested_recommendations=1,
        generated_count=1,
        evaluated_count=1,
        suitable_count=1,
        unsuitable_count=0,
        insufficient_count=0,
        resolution="suitable_candidates",
        candidates=[{name: getattr(site, name) for name in site.__dataclass_fields__}],
        recommendations=[{name: getattr(site, name) for name in site.__dataclass_fields__}],
        dataset_id="test-dem",
        reference_frame="MOON_ME_DE421",
        kernel_manifest_id="test-spice",
        weights={"sun": 0.4, "earth": 0.35, "simultaneous": 0.25},
        screening_scope="regional DEM",
        fidelity="point-center sampled",
        processing_seconds=0,
        limitations=["not landing safety"],
    )
    serialized = result.model_dump(mode="json")
    assert serialized["recommendations"][0]["score"] == 0.625
    assert serialized["recommendations"][0]["reference_frame"] == "MOON_ME_DE421"
