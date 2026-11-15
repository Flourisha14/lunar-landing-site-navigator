"""Synthetic, independent verification of candidate screening and score logic."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from lunar_engine.analysis.recommendations import (
    MissionConstraints,
    _halton,
    _score_site,
    recommend_lunar_sites,
)
from lunar_engine.core.conventions import LunarFrame
from lunar_engine.terrain.dem import TerrainDataError


def timeline(sun=0.75, earth=0.5, both=0.25, unknown=0, windows=()):
    metrics = SimpleNamespace(
        sampled_sun_fraction=sun,
        sampled_earth_fraction=earth,
        sampled_simultaneous_fraction=both,
        sun_unknown_samples=unknown,
        earth_unknown_samples=0,
        simultaneous_unknown_samples=0,
    )
    return SimpleNamespace(
        metrics=metrics,
        windows=windows,
        samples=(object(), object()),
        terrain_dataset_id="test-dem",
        frame=LunarFrame.ME_DE421,
        kernel_manifest_id="test-spice",
    )


def test_weighted_score_and_equality() -> None:
    result = _score_site(-89.5, 45, timeline(), MissionConstraints(), "test-dem")
    assert result.suitability == "SUITABLE"
    assert result.score == pytest.approx(0.40 * 0.75 + 0.35 * 0.5 + 0.25 * 0.25)
    assert result.checks["min_earth_fraction"] is True
    assert result.checks["min_simultaneous_fraction"] is True


def test_constraints_override_score() -> None:
    result = _score_site(
        -89, 10, timeline(sun=1, earth=0.49, both=0.49), MissionConstraints(), "test-dem"
    )
    assert result.suitability == "UNSUITABLE"
    assert result.score is not None
    assert result.checks["min_earth_fraction"] is False


def test_unknown_is_never_scored() -> None:
    result = _score_site(-89, 10, timeline(unknown=1), MissionConstraints(), "test-dem")
    assert result.suitability == "INSUFFICIENT_DATA"
    assert result.score is None
    assert all(value is None for value in result.checks.values())


def test_wrong_provenance_is_unknown() -> None:
    result = _score_site(-89, 10, timeline(), MissionConstraints(), "other-dem")
    assert result.suitability == "INSUFFICIENT_DATA"


def test_outage_and_darkness_constraints() -> None:
    windows = (
        SimpleNamespace(category="darkness", estimated_duration_seconds=7200),
        SimpleNamespace(category="earth_outage", estimated_duration_seconds=3600),
    )
    rules = MissionConstraints(max_darkness_seconds=7200, max_earth_outage_seconds=3599)
    result = _score_site(-89, 10, timeline(windows=windows), rules, "test-dem")
    assert result.checks["max_darkness_seconds"] is True
    assert result.checks["max_earth_outage_seconds"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_sun_fraction": -0.1},
        {"min_earth_fraction": 1.1},
        {"max_darkness_seconds": -1},
    ],
)
def test_invalid_constraints(kwargs) -> None:
    with pytest.raises(ValueError):
        MissionConstraints(**kwargs)


def fake_dem():
    return SimpleNamespace(
        metadata=SimpleNamespace(frame=LunarFrame.ME_DE421, dataset_id="test-dem")
    )


def run_fake(
    *,
    evaluator=None,
    generator=None,
    constraints=None,
    candidate_count=3,
    max_recommendations=2,
):
    def default_evaluator(lat, lon, *args, **kwargs):
        return timeline()

    def default_generator(*args, **kwargs):
        return ((-89.5, 30), (-89.5, 10), (-89.7, 20))[:candidate_count]

    return recommend_lunar_sites(
        fake_dem(),
        start_utc="2027-11-15T00:00:00Z",
        end_utc="2027-11-15T02:00:00Z",
        sampling_seconds=3600,
        candidate_count=candidate_count,
        max_recommendations=max_recommendations,
        constraints=constraints or MissionConstraints(),
        timeline_evaluator=evaluator or default_evaluator,
        candidate_generator=generator or default_generator,
    )


def test_ranking_ties_use_coordinates() -> None:
    result = run_fake()
    assert [c.longitude_deg for c in result.recommendations] == [20, 10]
    assert result.suitable_count == 3
    assert result.generated_count == 3
    assert result.resolution == "suitable_candidates"


def test_no_suitable_is_empty_list() -> None:
    result = run_fake(constraints=MissionConstraints(min_sun_fraction=0.99))
    assert result.recommendations == ()
    assert result.resolution == "no_suitable_candidates"


def test_insufficient_is_distinct() -> None:
    result = run_fake(evaluator=lambda *a, **k: timeline(unknown=1))
    assert result.resolution == "insufficient_data"
    assert not result.recommendations


def test_dem_coverage_error_is_insufficient() -> None:
    def unavailable(*args, **kwargs):
        raise TerrainDataError("out of coverage")

    result = run_fake(evaluator=unavailable)
    assert result.insufficient_count == 3
    assert result.resolution == "insufficient_data"


def test_mixed_ranking_and_filter() -> None:
    def mixed(lat, lon, *args, **kwargs):
        return timeline(sun=1 if lon == 10 else 0.2)

    result = run_fake(evaluator=mixed)
    assert len(result.recommendations) == 1
    assert result.recommendations[0].longitude_deg == 10


def test_deterministic_repeatability() -> None:
    a, b = run_fake(), run_fake()
    assert replace(a, processing_seconds=0) == replace(b, processing_seconds=0)


def test_invalid_candidate_count() -> None:
    with pytest.raises(ValueError):
        run_fake(candidate_count=13)


def test_halton_is_deterministic_and_bounded() -> None:
    assert [_halton(i, 2) for i in range(1, 6)] == [0.5, 0.25, 0.75, 0.125, 0.625]


def test_science_mode_forced_terrain_aware() -> None:
    seen = []

    def evaluator(*args, **kwargs):
        seen.append(kwargs["mode"])
        return timeline()

    run_fake(evaluator=evaluator)
    assert seen == ["terrain_aware"] * 3


def test_projected_candidate_generation_bounds_and_nodata() -> None:
    from affine import Affine

    from lunar_engine.analysis.recommendations import generate_candidate_sites
    from lunar_engine.terrain.dem import TerrainDataError, south_polar_stereographic_xy

    class Raster:
        bounds = SimpleNamespace(left=-40_000, right=40_000, bottom=-40_000, top=40_000)
        transform = Affine(80, 0, -40_000, 0, -80, 40_000)

    class MockDEM:
        metadata = SimpleNamespace(
            frame=LunarFrame.ME_DE421,
            dataset_id="test-dem",
            pixel_size_m=80.0,
            central_meridian_deg=0.0,
            reference_radius_m=1_737_400.0,
        )

        def _open_raster(self):
            return Raster()

        def sample(self, latitude_deg, longitude_deg, *, interpolation="bilinear"):
            x, y = south_polar_stereographic_xy(latitude_deg, longitude_deg)
            assert -37_480 < x < 37_480
            assert -37_480 < y < 37_480
            # Reject half the footprint to exercise nodata exclusion.
            if x < 0:
                raise TerrainDataError("nodata")
            return SimpleNamespace(elevation_m=-400.0, dataset_id="test-dem")

    dem = MockDEM()
    a = generate_candidate_sites(dem, 5, max_distance_km=2)
    b = generate_candidate_sites(dem, 5, max_distance_km=2)
    assert a == b
    assert len(a) == 5
    assert len(set(a)) == 5
    assert all(-90 <= lat < 0 and -180 <= lon < 180 for lat, lon in a)


def test_projected_candidate_rejects_small_footprint() -> None:
    from affine import Affine

    from lunar_engine.analysis.recommendations import generate_candidate_sites

    class Dem:
        metadata = SimpleNamespace(
            frame=LunarFrame.ME_DE421,
            dataset_id="test-dem",
            pixel_size_m=80.0,
            central_meridian_deg=0.0,
            reference_radius_m=1_737_400.0,
        )

        def _open_raster(self):
            return SimpleNamespace(
                bounds=SimpleNamespace(left=-500, right=500, bottom=-500, top=500),
                transform=Affine(80, 0, -500, 0, -80, 500),
            )

    with pytest.raises(ValueError, match="footprint too small"):
        generate_candidate_sites(Dem(), 1, max_distance_km=2)
