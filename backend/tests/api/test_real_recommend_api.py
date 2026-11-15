"""Optional actual NASA LOLA + SPICE recommendation API/engine equivalence."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lunar_api.app import create_app
from lunar_api.service import ScientificService
from lunar_engine.analysis.recommendations import recommend_lunar_sites
from lunar_engine.terrain.dem import DEFAULT_LOLA_METADATA, LunarDEM

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
@pytest.mark.requires_dem
@pytest.mark.requires_spice
def test_recommendations_match_real_scientific_engine() -> None:
    raw = os.environ.get("LUNAR_DEM_FILE")
    available = (
        bool(raw)
        and Path(raw).is_file()
        and os.environ.get("LUNAR_DEM_DATUM_CONFIRMED") == "1"
        and (ROOT / "data/spice/kernel-lock.json").is_file()
        and (ROOT / "data/spice/de421-frame-lock.json").is_file()
    )
    if not available:
        if os.environ.get("LUNAR_REQUIRE_REAL_RECOMMENDATION") == "1":
            pytest.fail("Verified NASA LOLA DEM and SPICE kernel locks required")
        pytest.skip("NASA LOLA DEM and SPICE assets are not provisioned")
    assert raw is not None
    service = ScientificService(ROOT, dem_file=Path(raw), datum_confirmed=True)
    request = {
        "start_utc": "2027-11-15T00:00:00Z",
        "duration_hours": 2,
        "sampling_seconds": 3600,
        "candidate_count": 2,
        "max_recommendations": 1,
        "terrain": {"max_distance_km": 2, "step_m": 160, "interpolation": "bilinear"},
    }
    http = TestClient(create_app(service=service)).post("/api/v1/recommend-sites", json=request)
    assert http.status_code == 200, http.text
    response = http.json()
    with LunarDEM(Path(raw), metadata=replace(DEFAULT_LOLA_METADATA, datum_confirmed=True)) as dem:
        direct = recommend_lunar_sites(
            dem,
            start_utc="2027-11-15T00:00:00Z",
            end_utc="2027-11-15T02:00:00.000000Z",
            sampling_seconds=3600,
            candidate_count=2,
            max_recommendations=1,
            max_distance_km=2,
            step_m=160,
            interpolation="bilinear",
            repository_root=ROOT,
        )
    assert response["reference_frame"] == direct.frame
    assert response["dataset_id"] == direct.dataset_id
    assert response["resolution"] == direct.resolution
    assert response["generated_count"] == direct.generated_count
    assert [(v["latitude_deg"], v["longitude_deg"]) for v in response["recommendations"]] == [
        (v.latitude_deg, v.longitude_deg) for v in direct.recommendations
    ]
    assert response["weights"] == {"sun": 0.4, "earth": 0.35, "simultaneous": 0.25}
