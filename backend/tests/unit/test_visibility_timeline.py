"""BE-013 deterministic time-grid, independently specified window sequences, and modes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lunar_engine.analysis.timeline import (
    VisibilitySample,
    analyze_visibility_timeline,
    extract_visibility_windows,
    sample_utc_interval,
    summarize_visibility,
)
from lunar_engine.analysis.visibility import VisibilityStatus as S
from lunar_engine.astronomy.geometry import CelestialDirection, CelestialGeometry
from lunar_engine.core.conventions import LunarFrame, LunarLocation, MoonFixedVector

START = "2027-11-15T00:00:00Z"
END = "2027-11-15T05:00:00Z"


def fake_sample(idx: int, sun: S, earth: S) -> VisibilitySample:
    intersection = (
        S.OBSTRUCTED
        if S.OBSTRUCTED in (sun, earth)
        else (S.UNKNOWN if S.UNKNOWN in (sun, earth) else S.VISIBLE)
    )
    when = datetime(2027, 11, 15, tzinfo=UTC) + timedelta(hours=idx)
    return VisibilitySample(
        when.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        sun,
        earth,
        intersection,
        S.VISIBLE,
        S.VISIBLE,
        45.0,
        5.0,
        90.0,
        6.0,
        None,
        None,
        "synthetic-kernels",
        "synthetic",
    )


def compute(suns: list[S], earths: list[S]):
    records = tuple(fake_sample(i, s, e) for i, (s, e) in enumerate(zip(suns, earths, strict=True)))
    windows = extract_visibility_windows(records, END, 3600)
    return records, windows, summarize_visibility(records, windows, END)


def test_grid_start_inclusive_end_exclusive() -> None:
    values = sample_utc_interval(START, "2027-11-15T03:00:00Z", 3600)
    assert len(values) == 3
    assert values[0] == "2027-11-15T00:00:00.000000Z"
    assert values[-1] == "2027-11-15T02:00:00.000000Z"


def test_nondisible_interval_and_final_short_cell() -> None:
    end = "2027-11-15T02:30:00Z"
    values = sample_utc_interval(START, end, 3600)
    assert len(values) == 3
    records = tuple(fake_sample(i, S.VISIBLE, S.VISIBLE) for i in range(3))
    windows = extract_visibility_windows(records, end, 3600)
    assert next(w for w in windows if w.category == "sunlight").estimated_duration_seconds == 9000


@pytest.mark.parametrize(
    "start,end,step",
    [
        (START, START, 60),
        (END, START, 60),
        (START, END, 0),
        (START, END, -1),
        (START, END, 1.5),
        ("bad", END, 60),
        (START, "2028-03-15T00:00:00Z", 60),
    ],
)
def test_invalid_grid(start: str, end: str, step: object) -> None:
    with pytest.raises(ValueError):
        sample_utc_interval(start, end, step)  # type: ignore[arg-type]


def test_workload_limit() -> None:
    with pytest.raises(ValueError, match="workload"):
        sample_utc_interval(START, END, 1, max_samples=10)


def test_all_visible_duration() -> None:
    _, windows, metric = compute([S.VISIBLE] * 5, [S.VISIBLE] * 5)
    assert metric.sampled_simultaneous_fraction == 1
    assert metric.illuminated_duration_seconds == 18000
    assert metric.longest_simultaneous_seconds == 18000
    sunlight = [w for w in windows if w.category == "sunlight"]
    assert len(sunlight) == 1
    assert sunlight[0].is_left_censored and sunlight[0].is_right_censored


def test_all_obstructed_darkness_and_outage() -> None:
    _, windows, metric = compute([S.OBSTRUCTED] * 5, [S.OBSTRUCTED] * 5)
    assert metric.illuminated_duration_seconds == 0
    assert not any(w.category == "sunlight" for w in windows)
    assert next(w for w in windows if w.category == "darkness").estimated_duration_seconds == 18000
    assert (
        next(w for w in windows if w.category == "earth_outage").estimated_duration_seconds == 18000
    )


def test_alternating_and_simultaneous_intersection() -> None:
    _, windows, metric = compute(
        [S.VISIBLE, S.VISIBLE, S.OBSTRUCTED, S.VISIBLE, S.VISIBLE],
        [S.OBSTRUCTED, S.VISIBLE, S.VISIBLE, S.VISIBLE, S.OBSTRUCTED],
    )
    concurrent = [w for w in windows if w.category == "simultaneous"]
    assert [
        (w.start_utc[11:13], w.end_utc[11:13], w.estimated_duration_seconds) for w in concurrent
    ] == [("01", "02", 3600), ("03", "04", 3600)]
    assert metric.simultaneous_duration_seconds == 7200
    assert metric.longest_illumination_seconds == 7200
    assert metric.sampled_sun_fraction == 0.8


def test_unknown_never_counts_as_obstruction() -> None:
    _, windows, metric = compute(
        [S.VISIBLE, S.UNKNOWN, S.VISIBLE, S.OBSTRUCTED, S.VISIBLE],
        [S.VISIBLE, S.VISIBLE, S.UNKNOWN, S.UNKNOWN, S.VISIBLE],
    )
    assert metric.sun_unknown_samples == 1
    assert metric.earth_unknown_samples == 2
    assert metric.simultaneous_unknown_samples == 2
    assert metric.sun_unknown_duration_seconds == 3600
    assert metric.illuminated_duration_seconds == 10800
    assert not any(w.category == "darkness" and w.start_utc[11:13] == "01" for w in windows)
    assert metric.longest_simultaneous_seconds == 3600


def test_three_value_intersection_when_one_known_obstructed() -> None:
    records, _, _ = compute([S.UNKNOWN] * 5, [S.OBSTRUCTED] * 5)
    assert all(s.simultaneous is S.OBSTRUCTED for s in records)


def test_windows_reject_unsorted_duplicate_or_gap() -> None:
    records = (fake_sample(0, S.VISIBLE, S.VISIBLE), fake_sample(0, S.VISIBLE, S.VISIBLE))
    with pytest.raises(ValueError):
        extract_visibility_windows(records, END, 3600)
    records = (fake_sample(0, S.VISIBLE, S.VISIBLE), fake_sample(2, S.VISIBLE, S.VISIBLE))
    with pytest.raises(ValueError):
        extract_visibility_windows(records, END, 3600)


def direction(body: str, elev: float) -> CelestialDirection:
    return CelestialDirection(
        body=body,
        azimuth_deg=0.0,
        elevation_deg=elev,
        east_unit=0.0,
        north_unit=1.0,
        up_unit=0.0,
        range_km=1e6,
        geometric_visible=elev > 0,
        position_moon_fixed=MoonFixedVector(1e6, 0, 0, LunarFrame.ME_DE421),
    )


def fake_provider(sun: float, earth: float):
    calls: list[str] = []

    def provide(
        lat: float,
        lon: float,
        timestamp_utc: str,
        *,
        terrain_elevation_km: float,
        repository_root: Path,
    ) -> CelestialGeometry:
        calls.append(timestamp_utc)
        return CelestialGeometry(
            LunarLocation(lat, lon, terrain_elevation_km, LunarFrame.ME_DE421),
            timestamp_utc,
            0.0,
            LunarFrame.ME_DE421,
            "synthetic-kernels",
            direction("SUN", sun),
            direction("EARTH", earth),
        )

    return provide, calls


def test_geometric_mode_no_dem_and_exact_one_provider_call_per_epoch() -> None:
    p, calls = fake_provider(5.0, -2.0)
    result = analyze_visibility_timeline(
        -89.0,
        45.0,
        START,
        END,
        3600,
        mode="geometric",
        geometry_provider=p,
    )
    assert len(calls) == 5
    assert all(s.sun is S.VISIBLE and s.earth is S.OBSTRUCTED for s in result.samples)
    assert result.terrain_dataset_id is None
    assert result.metrics.earth_visible_duration_seconds == 0
    assert result.max_distance_km is None
    again = analyze_visibility_timeline(
        -89.0,
        45.0,
        START,
        END,
        3600,
        mode="geometric",
        geometry_provider=p,
    )
    assert result == again  # processing wall clock excluded from scientific equality


def test_geometric_boundary_is_obstructed() -> None:
    p, _ = fake_provider(0, 0)
    result = analyze_visibility_timeline(
        -89, 0, START, END, 3600, mode="geometric", geometry_provider=p
    )
    assert all(s.sun is S.OBSTRUCTED for s in result.samples)


def test_terrain_mode_requires_dem() -> None:
    p, _ = fake_provider(10, 10)
    with pytest.raises(ValueError, match="DEM"):
        analyze_visibility_timeline(-89, 0, START, END, 3600, geometry_provider=p)


def test_invalid_mode_and_coordinates() -> None:
    p, _ = fake_provider(10, 10)
    with pytest.raises(ValueError):
        analyze_visibility_timeline(-89, 0, START, END, 3600, mode="invalid", geometry_provider=p)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        analyze_visibility_timeline(91, 0, START, END, 3600, mode="geometric", geometry_provider=p)


def test_manifest_change_rejected() -> None:
    p, _ = fake_provider(10, 10)

    def mutable(*args, **kwargs):
        geo = p(*args, **kwargs)
        from dataclasses import replace

        return replace(geo, kernel_manifest_id=geo.timestamp_utc)

    with pytest.raises(ValueError, match="manifest"):
        analyze_visibility_timeline(
            -89, 0, START, END, 3600, mode="geometric", geometry_provider=mutable
        )


def test_terrain_mode_reuses_shared_visibility_and_cache() -> None:
    from dataclasses import dataclass

    @dataclass
    class Meta:
        frame: LunarFrame = LunarFrame.ME_DE421
        dataset_id: str = "synthetic-fixed-dem"
        reference_radius_m: float = 1737400.0

    @dataclass
    class TerrainSample:
        location: LunarLocation
        elevation_m: float
        dataset_id: str

    class DEM:
        metadata = Meta()
        calls = 0

        def sample(self, lat: float, lon: float, *, interpolation="bilinear"):
            self.calls += 1
            return TerrainSample(
                LunarLocation(lat, lon, 0, LunarFrame.ME_DE421), 0.0, self.metadata.dataset_id
            )

    p, calls = fake_provider(10, -30)
    terrain = DEM()
    out = analyze_visibility_timeline(
        -89,
        0,
        START,
        "2027-11-15T02:00:00Z",
        3600,
        mode="terrain_aware",
        dem=terrain,
        max_distance_km=1,
        step_m=200,
        geometry_provider=p,
    )
    assert len(calls) == 2
    assert all(s.sun is S.VISIBLE for s in out.samples)
    assert all(s.earth is S.OBSTRUCTED for s in out.samples)
    assert out.terrain_cache_hits > 0
    assert out.terrain_dataset_id == terrain.metadata.dataset_id
    assert out.samples[0].earth_geometric is S.OBSTRUCTED


def test_terrain_unknown_propagates_to_timeline() -> None:
    from dataclasses import dataclass

    from lunar_engine.terrain.dem import TerrainDataError

    @dataclass
    class Meta:
        frame: LunarFrame = LunarFrame.ME_DE421
        dataset_id: str = "synthetic-partial"
        reference_radius_m: float = 1737400.0

    @dataclass
    class TerrainSample:
        location: LunarLocation
        elevation_m: float
        dataset_id: str

    class DEM:
        metadata = Meta()

        def sample(self, lat: float, lon: float, *, interpolation="bilinear"):
            if lat > -88.999:
                raise TerrainDataError("missing")
            return TerrainSample(
                LunarLocation(lat, lon, 0, LunarFrame.ME_DE421), 0.0, self.metadata.dataset_id
            )

    p, _ = fake_provider(10, 20)
    out = analyze_visibility_timeline(
        -89,
        0,
        START,
        "2027-11-15T02:00:00Z",
        3600,
        mode="terrain_aware",
        dem=DEM(),
        max_distance_km=1,
        step_m=100,
        geometry_provider=p,
    )
    assert all(s.sun is S.UNKNOWN for s in out.samples)
    assert out.metrics.sun_unknown_duration_seconds == 7200
    assert out.metrics.illuminated_duration_seconds == 0
    assert out.metrics.longest_illumination_seconds == 0
    assert not any(w.category == "sunlight" for w in out.windows)
