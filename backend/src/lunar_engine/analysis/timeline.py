"""BE-013: bounded, deterministic UTC sampling and point-center visibility windows.

Intervals are [start, end); each sample owns a left-anchored time cell. Window
boundaries and durations are cell-based estimates, NOT measured transition times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Literal

from lunar_engine.analysis.visibility import (
    GeometryFunction,
    VisibilityStatus,
    evaluate_terrain_visibility,
)
from lunar_engine.astronomy.ephemeris import canonical_utc
from lunar_engine.astronomy.geometry import CelestialGeometry
from lunar_engine.coordinates.frame_transform import analyze_geometry_in_dem_frame
from lunar_engine.core.conventions import LunarFrame, LunarLocation
from lunar_engine.terrain.horizon import TerrainSampleLike, TerrainSource

VisibilityMode = Literal["geometric", "terrain_aware"]
WindowCategory = Literal["sunlight", "earth_visible", "simultaneous", "darkness", "earth_outage"]
MAX_SAMPLES = 2048
MAX_MISSION_DAYS = 90


def _as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(canonical_utc(value).replace("Z", "+00:00"))


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sample_utc_interval(
    start_utc: str,
    end_utc: str,
    sampling_seconds: int,
    *,
    max_samples: int = MAX_SAMPLES,
) -> tuple[str, ...]:
    """Start-inclusive/end-exclusive integer-second UTC grid, no float drift.

    A short final cell is allowed. The end timestamp is a boundary, not a sample.
    """
    start, end = _as_datetime(start_utc), _as_datetime(end_utc)
    if end <= start:
        raise ValueError("Mission start must precede end")
    if type(sampling_seconds) is not int or sampling_seconds <= 0:
        raise ValueError("sampling_seconds must be a positive integer")
    if type(max_samples) is not int or not 1 <= max_samples <= MAX_SAMPLES:
        raise ValueError(f"max_samples must be within [1, {MAX_SAMPLES}]")
    total = end - start
    if total > timedelta(days=MAX_MISSION_DAYS):
        raise ValueError("Mission duration exceeds supported 90-day limit")
    step_us = sampling_seconds * 1_000_000
    total_us = total // timedelta(microseconds=1)
    count = (total_us + step_us - 1) // step_us
    if count > max_samples:
        raise ValueError(f"Sampling workload exceeds {max_samples} samples")
    return tuple(_format_utc(start + timedelta(microseconds=i * step_us)) for i in range(count))


@dataclass(frozen=True, slots=True)
class VisibilitySample:
    timestamp_utc: str
    sun: VisibilityStatus
    earth: VisibilityStatus
    simultaneous: VisibilityStatus
    sun_geometric: VisibilityStatus
    earth_geometric: VisibilityStatus
    sun_azimuth_deg: float | None
    sun_elevation_deg: float
    earth_azimuth_deg: float | None
    earth_elevation_deg: float
    sun_terrain_horizon_deg: float | None
    earth_terrain_horizon_deg: float | None
    kernel_manifest_id: str
    fidelity: str


@dataclass(frozen=True, slots=True)
class VisibilityWindow:
    category: WindowCategory
    state: VisibilityStatus
    start_utc: str
    end_utc: str
    estimated_duration_seconds: float
    sampling_seconds: int
    sample_count: int
    is_left_censored: bool
    is_right_censored: bool
    boundary_uncertainty_seconds: int


@dataclass(frozen=True, slots=True)
class VisibilityMetrics:
    sampled_sun_fraction: float
    sampled_earth_fraction: float
    sampled_simultaneous_fraction: float
    sun_unknown_samples: int
    earth_unknown_samples: int
    simultaneous_unknown_samples: int
    sun_unknown_duration_seconds: float
    earth_unknown_duration_seconds: float
    simultaneous_unknown_duration_seconds: float
    illuminated_duration_seconds: float
    earth_visible_duration_seconds: float
    simultaneous_duration_seconds: float
    longest_illumination_seconds: float
    longest_earth_visibility_seconds: float
    longest_simultaneous_seconds: float


@dataclass(frozen=True, slots=True)
class VisibilityTimeline:
    observer: LunarLocation
    observer_height_m: float
    mode: VisibilityMode
    start_utc: str
    end_utc: str
    sampling_seconds: int
    endpoint_semantics: str
    samples: tuple[VisibilitySample, ...]
    windows: tuple[VisibilityWindow, ...]
    metrics: VisibilityMetrics
    terrain_dataset_id: str | None
    frame: LunarFrame
    kernel_manifest_id: str
    max_distance_km: float | None
    step_m: float | None
    interpolation: str | None
    processing_seconds: float = field(compare=False)
    terrain_cache_hits: int
    terrain_cache_misses: int
    fidelity: str


def _and_state(a: VisibilityStatus, b: VisibilityStatus) -> VisibilityStatus:
    if VisibilityStatus.OBSTRUCTED in (a, b):
        return VisibilityStatus.OBSTRUCTED
    if VisibilityStatus.UNKNOWN in (a, b):
        return VisibilityStatus.UNKNOWN
    return VisibilityStatus.VISIBLE


def _invert_state(value: VisibilityStatus) -> VisibilityStatus:
    if value is VisibilityStatus.VISIBLE:
        return VisibilityStatus.OBSTRUCTED
    if value is VisibilityStatus.OBSTRUCTED:
        return VisibilityStatus.VISIBLE
    return VisibilityStatus.UNKNOWN


def _category_status(sample: VisibilitySample, category: WindowCategory) -> VisibilityStatus:
    if category == "sunlight":
        return sample.sun
    if category == "earth_visible":
        return sample.earth
    if category == "simultaneous":
        return sample.simultaneous
    if category == "darkness":
        return _invert_state(sample.sun)
    return _invert_state(sample.earth)


def extract_visibility_windows(
    samples: tuple[VisibilitySample, ...],
    end_utc: str,
    sampling_seconds: int,
) -> tuple[VisibilityWindow, ...]:
    """Extract only confirmed VISIBLE runs; UNKNOWN segments split runs.

    Darkness and outages use inverted states. Their UNKNOWN spans are excluded.
    Each sample represents [sample_time, next_sample_time), last through end_utc.
    """
    if not samples:
        raise ValueError("At least one visibility sample is required")
    if type(sampling_seconds) is not int or sampling_seconds <= 0:
        raise ValueError("sampling_seconds must be positive integer")
    times = [_as_datetime(s.timestamp_utc) for s in samples]
    end = _as_datetime(end_utc)
    if any(b <= a for a, b in zip(times, times[1:], strict=False)) or times[-1] >= end:
        raise ValueError("Sample timestamps must be strictly increasing and before end")
    if any(
        b - a != timedelta(seconds=sampling_seconds) for a, b in zip(times, times[1:], strict=False)
    ):
        raise ValueError("Sample timestamps must follow the requested fixed grid")
    if end - times[-1] > timedelta(seconds=sampling_seconds):
        raise ValueError("Final sample does not cover endpoint")
    categories: tuple[WindowCategory, ...] = (
        "sunlight",
        "earth_visible",
        "simultaneous",
        "darkness",
        "earth_outage",
    )
    result: list[VisibilityWindow] = []
    for category in categories:
        begin: int | None = None
        for index in range(len(samples) + 1):
            active = (
                index < len(samples)
                and _category_status(samples[index], category) is VisibilityStatus.VISIBLE
            )
            if active and begin is None:
                begin = index
            if not active and begin is not None:
                stop = times[index] if index < len(times) else end
                duration = (stop - times[begin]).total_seconds()
                result.append(
                    VisibilityWindow(
                        category,
                        VisibilityStatus.VISIBLE,
                        _format_utc(times[begin]),
                        _format_utc(stop),
                        duration,
                        sampling_seconds,
                        index - begin,
                        begin == 0,
                        index == len(samples),
                        sampling_seconds,
                    )
                )
                begin = None
    return tuple(result)


def summarize_visibility(
    samples: tuple[VisibilitySample, ...],
    windows: tuple[VisibilityWindow, ...],
    end_utc: str,
) -> VisibilityMetrics:
    """Sample fractions use all samples, with UNKNOWN counts explicit.

    Duration sums weight each sample's represented cell, including short final.
    """
    if not samples:
        raise ValueError("At least one sample is required")
    times = [_as_datetime(s.timestamp_utc) for s in samples]
    stop = _as_datetime(end_utc)
    edges = [*times, stop]
    durations = [(edges[i + 1] - edges[i]).total_seconds() for i in range(len(samples))]
    if any(v <= 0 for v in durations):
        raise ValueError("Invalid nonpositive sample cell")

    def count(field: str, status: VisibilityStatus) -> int:
        return sum(getattr(sample, field) is status for sample in samples)

    def duration(field: str, status: VisibilityStatus) -> float:
        return sum(
            dt
            for sample, dt in zip(samples, durations, strict=True)
            if getattr(sample, field) is status
        )

    def longest(category: WindowCategory) -> float:
        return max(
            (w.estimated_duration_seconds for w in windows if w.category == category), default=0.0
        )

    n = len(samples)
    return VisibilityMetrics(
        count("sun", VisibilityStatus.VISIBLE) / n,
        count("earth", VisibilityStatus.VISIBLE) / n,
        count("simultaneous", VisibilityStatus.VISIBLE) / n,
        count("sun", VisibilityStatus.UNKNOWN),
        count("earth", VisibilityStatus.UNKNOWN),
        count("simultaneous", VisibilityStatus.UNKNOWN),
        duration("sun", VisibilityStatus.UNKNOWN),
        duration("earth", VisibilityStatus.UNKNOWN),
        duration("simultaneous", VisibilityStatus.UNKNOWN),
        duration("sun", VisibilityStatus.VISIBLE),
        duration("earth", VisibilityStatus.VISIBLE),
        duration("simultaneous", VisibilityStatus.VISIBLE),
        longest("sunlight"),
        longest("earth_visible"),
        longest("simultaneous"),
    )


def _geometry_states(geometry: CelestialGeometry) -> tuple[VisibilityStatus, VisibilityStatus]:
    def state(elevation: float) -> VisibilityStatus:
        if not isfinite(elevation) or not -90 <= elevation <= 90:
            raise ValueError("Invalid astronomical elevation")
        return VisibilityStatus.VISIBLE if elevation > 0 else VisibilityStatus.OBSTRUCTED

    if geometry.frame is not LunarFrame.ME_DE421:
        raise ValueError("Astronomy must be transformed to MOON_ME_DE421")
    if (
        geometry.sun.body != "SUN"
        or geometry.earth.body != "EARTH"
        or geometry.sun.position_moon_fixed.frame is not LunarFrame.ME_DE421
        or geometry.earth.position_moon_fixed.frame is not LunarFrame.ME_DE421
    ):
        raise ValueError("Astronomy targets must have expected identities and DE421 frame")
    if geometry.aberration != "NONE":
        raise ValueError("Expected geometric SPICE aberration NONE")
    return state(geometry.sun.elevation_deg), state(geometry.earth.elevation_deg)


def analyze_visibility_timeline(
    latitude_deg: float,
    longitude_deg: float,
    start_utc: str,
    end_utc: str,
    sampling_seconds: int,
    *,
    observer_height_m: float = 2.0,
    mode: VisibilityMode = "terrain_aware",
    dem: TerrainSource | None = None,
    max_distance_km: float = 30.0,
    step_m: float = 160.0,
    interpolation: Literal["nearest", "bilinear"] = "bilinear",
    repository_root: Path | None = None,
    geometry_provider: GeometryFunction | None = None,
    max_samples: int = MAX_SAMPLES,
) -> VisibilityTimeline:
    """Evaluate each UTC sample using the existing shared SPICE/DEM engine.

    A supplied DEM handle is owned by the caller and never opened/closed here.
    Geometric mode uses a zero-elevation reference sphere if DEM is omitted.
    Horizon rays are re-evaluated at their *actual* azimuth each epoch; no
    scientifically unsafe coarse-azimuth cache is used. The DEM handle is reused.
    """
    start_clock = perf_counter()
    timestamps = sample_utc_interval(start_utc, end_utc, sampling_seconds, max_samples=max_samples)
    if mode not in ("geometric", "terrain_aware"):
        raise ValueError("mode must be geometric or terrain_aware")
    if not isfinite(observer_height_m) or observer_height_m < 0:
        raise ValueError("observer_height_m must be finite and nonnegative")
    site = LunarLocation(latitude_deg, longitude_deg, 0.0, LunarFrame.ME_DE421)
    if mode == "terrain_aware" and dem is None:
        raise ValueError("terrain_aware mode requires an open DEM")
    if geometry_provider is None:
        if repository_root is None:
            raise ValueError("repository_root required for verified SPICE geometry")
        geometry_provider = analyze_geometry_in_dem_frame
    root = repository_root if repository_root is not None else Path(".")
    dataset_id: str | None = None
    altitude_km = observer_height_m / 1000.0
    if dem is not None:
        metadata = getattr(dem, "metadata", None)
        if getattr(metadata, "frame", None) is not LunarFrame.ME_DE421:
            raise ValueError("DEM must use MOON_ME_DE421")
        dataset_id = getattr(metadata, "dataset_id", None)
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError("DEM provenance required")
        sampled_site = dem.sample(
            site.latitude_deg, site.longitude_deg, interpolation=interpolation
        )
        if (
            sampled_site.dataset_id != dataset_id
            or sampled_site.location.frame is not LunarFrame.ME_DE421
        ):
            raise ValueError("DEM observer sample provenance/frame mismatch")
        if not isfinite(sampled_site.elevation_m):
            raise ValueError("Invalid DEM observer elevation")
        altitude_km += sampled_site.elevation_m / 1000.0
    observer = LunarLocation(
        site.latitude_deg, site.longitude_deg, altitude_km, LunarFrame.ME_DE421
    )
    # Safe session-local cache: exact coordinates/interpolation, same DEM handle,
    # frame, metadata, observer and configuration for this one analysis.
    # No azimuth bucketing or horizon angle interpolation is performed.
    cache_hits = cache_misses = 0
    source = dem
    if mode == "terrain_aware":
        assert dem is not None
        actual_dem: TerrainSource = dem

        @lru_cache(maxsize=16_384)
        def cached_sample(
            latitude_deg: float,
            longitude_deg: float,
            interpolation: Literal["nearest", "bilinear"],
        ) -> TerrainSampleLike:
            return actual_dem.sample(
                latitude_deg,
                longitude_deg,
                interpolation=interpolation,
            )

        class CachedTerrain:
            metadata = actual_dem.metadata

            def sample(
                self,
                latitude_deg: float,
                longitude_deg: float,
                *,
                interpolation: Literal["nearest", "bilinear"] = "bilinear",
            ) -> TerrainSampleLike:
                return cached_sample(
                    latitude_deg,
                    longitude_deg,
                    interpolation,
                )

        source = CachedTerrain()
    rows: list[VisibilitySample] = []
    manifest: str | None = None
    for instant in timestamps:
        if mode == "terrain_aware":
            assert source is not None
            outcome = evaluate_terrain_visibility(
                source,
                site.latitude_deg,
                site.longitude_deg,
                instant,
                observer_height_m=observer_height_m,
                max_distance_km=max_distance_km,
                step_m=step_m,
                interpolation=interpolation,
                repository_root=root,
                geometry_provider=geometry_provider,
            )
            sun, earth = outcome.sun.status, outcome.earth.status
            sun_az, earth_az = outcome.sun.azimuth_deg, outcome.earth.azimuth_deg
            sun_el, earth_el = outcome.sun.elevation_deg, outcome.earth.elevation_deg
            sun_h, earth_h = outcome.sun.terrain_horizon_deg, outcome.earth.terrain_horizon_deg
            sample_manifest = outcome.kernel_manifest_id
        else:
            geo = geometry_provider(
                site.latitude_deg,
                site.longitude_deg,
                instant,
                terrain_elevation_km=altitude_km,
                repository_root=root,
            )
            if geo.site.frame is not LunarFrame.ME_DE421 or geo.site != observer:
                raise ValueError("Astronomical observer does not match requested site")
            if geo.timestamp_utc != instant:
                raise ValueError("Astronomical timestamp mismatch")
            sun, earth = _geometry_states(geo)
            sun_az, earth_az = geo.sun.azimuth_deg, geo.earth.azimuth_deg
            sun_el, earth_el = geo.sun.elevation_deg, geo.earth.elevation_deg
            sun_h = earth_h = None
            sample_manifest = geo.kernel_manifest_id
        if manifest is None:
            manifest = sample_manifest
        elif manifest != sample_manifest:
            raise ValueError("Ephemeris kernel manifest changed during timeline")
        sun_geo = VisibilityStatus.VISIBLE if sun_el > 0 else VisibilityStatus.OBSTRUCTED
        earth_geo = VisibilityStatus.VISIBLE if earth_el > 0 else VisibilityStatus.OBSTRUCTED
        rows.append(
            VisibilitySample(
                instant,
                sun,
                earth,
                _and_state(sun, earth),
                sun_geo,
                earth_geo,
                sun_az,
                sun_el,
                earth_az,
                earth_el,
                sun_h,
                earth_h,
                sample_manifest,
                "geometric_point_centers_spice_none_terrain"
                if mode == "terrain_aware"
                else "geometric_point_centers_spice_none_spherical_tangent",
            )
        )
    if mode == "terrain_aware":
        assert source is not None
        info = cached_sample.cache_info()
        cache_hits, cache_misses = info.hits, info.misses
    samples = tuple(rows)
    windows = extract_visibility_windows(samples, end_utc, sampling_seconds)
    metrics = summarize_visibility(samples, windows, end_utc)
    return VisibilityTimeline(
        observer,
        observer_height_m,
        mode,
        canonical_utc(start_utc),
        canonical_utc(end_utc),
        sampling_seconds,
        "[start,end); left-edge sample controls each time cell",
        samples,
        windows,
        metrics,
        dataset_id,
        LunarFrame.ME_DE421,
        manifest or "",
        max_distance_km if mode == "terrain_aware" else None,
        step_m if mode == "terrain_aware" else None,
        interpolation if mode == "terrain_aware" else None,
        perf_counter() - start_clock,
        cache_hits,
        cache_misses,
        "sampled_geometric_point_centers_no_exact_transitions",
    )
