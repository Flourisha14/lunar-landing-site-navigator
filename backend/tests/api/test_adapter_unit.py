"""QA-005: HTTP serialization of synthetic fixtures; NOT astronomical goldens."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from lunar_api.app import create_app
from lunar_api.schemas import GeometryRequest
from lunar_api.service import ScientificService
from lunar_engine.analysis.visibility import (
    BodyVisibility,
    TerrainVisibilityResult,
    VisibilityStatus,
)
from lunar_engine.astronomy.geometry import CelestialDirection, CelestialGeometry
from lunar_engine.core.conventions import LunarFrame, LunarLocation, MoonFixedVector

UTC = "2027-11-15T12:00:00.000000Z"


def fake_direction(name: str, elevation: float) -> CelestialDirection:
    return CelestialDirection(
        body=name,
        azimuth_deg=45.0,
        elevation_deg=elevation,
        east_unit=0.5,
        north_unit=0.4,
        up_unit=0.3,
        range_km=100_000.0,
        geometric_visible=elevation > 0.0,
        position_moon_fixed=MoonFixedVector(1, 2, 3, LunarFrame.ME_DE421),
    )


def fake_geometry(lat: float, lon: float, timestamp: str, altitude_km: float) -> CelestialGeometry:
    return CelestialGeometry(
        site=LunarLocation(lat, lon, altitude_km, LunarFrame.ME_DE421),
        timestamp_utc=timestamp,
        et_seconds=0.0,
        frame=LunarFrame.ME_DE421,
        kernel_manifest_id="synthetic-fixture-not-spice",
        sun=fake_direction("SUN", 4.0),
        earth=fake_direction("EARTH", -2.0),
    )


def configured_service(tmp_path: Path) -> ScientificService:
    base = tmp_path / "data" / "spice"
    base.mkdir(parents=True)
    (base / "kernel-lock.json").write_text("{}")
    (base / "de421-frame-lock.json").write_text("{}")
    return ScientificService(tmp_path)


def test_geometry_http_matches_adapter_and_preserves_frame(monkeypatch, tmp_path: Path) -> None:
    service = configured_service(tmp_path)
    monkeypatch.setattr(service, "_geometry", fake_geometry)
    client = TestClient(create_app(service=service))
    payload = {
        "latitude_deg": -89.5,
        "longitude_deg": 45.0,
        "timestamp_utc": "2027-11-15T12:00:00Z",
    }
    direct = service.geometry(GeometryRequest(**payload))
    response = client.post("/api/v1/geometry", json=payload)
    assert response.status_code == 200
    assert response.json() == direct.model_dump(mode="json")
    assert response.json()["metadata"]["reference_frame"] == LunarFrame.ME_DE421.value
    assert response.json()["sun"]["geometric_visibility"] == "visible"
    assert response.json()["earth"]["geometric_visibility"] == "obstructed"
    assert response.json()["sun"]["position_moon_fixed_km"] == [1, 2, 3]


def test_geometric_site_analysis_no_dem(monkeypatch, tmp_path: Path) -> None:
    service = configured_service(tmp_path)
    monkeypatch.setattr(service, "_geometry", fake_geometry)
    resp = TestClient(create_app(service=service)).post(
        "/api/v1/site-analysis",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "timestamp_utc": "2027-11-15T12:00:00Z",
            "mode": "geometric",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["terrain_dataset_id"] is None
    assert resp.json()["earth"]["terrain_horizon_deg"] is None
    assert resp.json()["earth"]["status"] == "obstructed"


def test_unknown_terrain_is_not_falsely_visible(monkeypatch, tmp_path: Path) -> None:
    service = configured_service(tmp_path)

    @contextmanager
    def fake_dem() -> Iterator[object]:
        yield object()

    monkeypatch.setattr(service, "_open_dem", fake_dem)

    def fake_eval(*args: object, **kwargs: object) -> TerrainVisibilityResult:
        site = LunarLocation(-89.5, 45, 0, LunarFrame.ME_DE421)
        sun = BodyVisibility(
            "SUN", VisibilityStatus.UNKNOWN, 45.0, 5.0, None, None, None, "incomplete_dem_coverage"
        )
        earth = BodyVisibility(
            "EARTH", VisibilityStatus.OBSTRUCTED, 20.0, 2.0, 4.0, -2.0, None, None
        )
        return TerrainVisibilityResult(
            site,
            2.0,
            UTC,
            LunarFrame.ME_DE421,
            "synthetic-dem",
            "synthetic-fixture",
            2.0,
            80.0,
            "bilinear",
            sun,
            earth,
        )

    monkeypatch.setattr("lunar_api.service.evaluate_terrain_visibility", fake_eval)
    res = TestClient(create_app(service=service)).post(
        "/api/v1/site-analysis",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "timestamp_utc": "2027-11-15T12:00:00Z",
            "mode": "terrain_aware",
        },
    )
    assert res.status_code == 200
    assert res.json()["sun"]["status"] == "unknown"
    assert res.json()["sun"]["terrain_horizon_deg"] is None
    assert res.json()["sun"]["clearance_deg"] is None
    assert res.json()["sun"]["reason"] == "incomplete_dem_coverage"
    assert res.json()["metadata"]["terrain_dataset_id"] == "synthetic-dem"


def test_timeline_http_matches_existing_window_functions(monkeypatch, tmp_path: Path) -> None:
    """Synthetic states exercise JSON contract; underlying windows are *real* BE-013."""
    from lunar_api.schemas import TimelineRequest
    from lunar_engine.analysis.timeline import (
        VisibilitySample,
        VisibilityTimeline,
        extract_visibility_windows,
        summarize_visibility,
    )

    service = configured_service(tmp_path)
    start = "2027-11-15T12:00:00.000000Z"
    end = "2027-11-15T14:00:00.000000Z"

    def record(timestamp: str, sun: VisibilityStatus, earth: VisibilityStatus) -> VisibilitySample:
        return VisibilitySample(
            timestamp,
            sun,
            earth,
            (
                VisibilityStatus.OBSTRUCTED
                if VisibilityStatus.OBSTRUCTED in (sun, earth)
                else VisibilityStatus.UNKNOWN
                if VisibilityStatus.UNKNOWN in (sun, earth)
                else VisibilityStatus.VISIBLE
            ),
            VisibilityStatus.VISIBLE,
            VisibilityStatus.VISIBLE,
            45.0,
            5.0,
            20.0,
            4.0,
            None,
            None,
            "synthetic-fixture",
            "synthetic-contract-fixture",
        )

    rows = (
        record(start, VisibilityStatus.VISIBLE, VisibilityStatus.VISIBLE),
        record("2027-11-15T13:00:00.000000Z", VisibilityStatus.UNKNOWN, VisibilityStatus.VISIBLE),
    )
    windows = extract_visibility_windows(rows, end, 3600)
    metrics = summarize_visibility(rows, windows, end)
    outcome = VisibilityTimeline(
        observer=LunarLocation(-89.5, 45, 0.002, LunarFrame.ME_DE421),
        observer_height_m=2.0,
        mode="geometric",
        start_utc=start,
        end_utc=end,
        sampling_seconds=3600,
        endpoint_semantics="[start,end); left-edge sample controls each time cell",
        samples=rows,
        windows=windows,
        metrics=metrics,
        terrain_dataset_id=None,
        frame=LunarFrame.ME_DE421,
        kernel_manifest_id="synthetic-fixture",
        max_distance_km=None,
        step_m=None,
        interpolation=None,
        processing_seconds=0.01,
        terrain_cache_hits=0,
        terrain_cache_misses=0,
        fidelity="synthetic-contract-fixture",
    )
    monkeypatch.setattr("lunar_api.service.analyze_visibility_timeline", lambda *a, **k: outcome)
    payload = {
        "latitude_deg": -89.5,
        "longitude_deg": 45,
        "start_utc": start,
        "end_utc": end,
        "sampling_seconds": 3600,
        "mode": "geometric",
    }
    direct = service.timeline(TimelineRequest(**payload))
    response = TestClient(create_app(service=service)).post("/api/v1/timeline", json=payload)
    assert response.status_code == 200
    assert response.json() == direct.model_dump(mode="json")
    assert response.json()["samples"][1]["sun"] == "unknown"
    assert response.json()["metrics"]["sun_unknown_samples"] == 1
    assert response.json()["metrics"]["illuminated_duration_seconds"] == 3600


def test_out_of_ephemeris_coverage_returns_422(monkeypatch, tmp_path: Path) -> None:
    service = configured_service(tmp_path)

    class SpiceSPKINSUFFDATA(Exception):
        pass

    def raise_ephemeris(*args: object, **kwargs: object) -> None:
        raise SpiceSPKINSUFFDATA("SPICE(SPKINSUFFDATA): no state for requested epoch")

    monkeypatch.setattr(service, "_geometry", raise_ephemeris)
    client = TestClient(create_app(service=service), raise_server_exceptions=False)
    response = client.post(
        "/api/v1/geometry",
        json={
            "latitude_deg": -89.5,
            "longitude_deg": 45,
            "timestamp_utc": "2027-11-15T12:00:00Z",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ephemeris_out_of_coverage"
