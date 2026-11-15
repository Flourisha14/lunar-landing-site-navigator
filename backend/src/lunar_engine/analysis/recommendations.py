"""Deterministic NASA LOLA candidate screening; not a landing-safety certification.

All astronomy, horizon, and time-window calculations are delegated to BE-013.
The requesting service owns and closes the DEM handle; nothing here loads data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

from lunar_engine.analysis.timeline import (
    VisibilityTimeline,
    analyze_visibility_timeline,
    sample_utc_interval,
)
from lunar_engine.core.conventions import LunarFrame
from lunar_engine.terrain.dem import (
    TerrainDataError,
    TerrainMetadata,
    south_polar_inverse,
)
from lunar_engine.terrain.horizon import TerrainSource

Suitability = Literal["SUITABLE", "UNSUITABLE", "INSUFFICIENT_DATA"]
Resolution = Literal["suitable_candidates", "no_suitable_candidates", "insufficient_data"]
TimelineEvaluator = Callable[..., VisibilityTimeline]

# Strict live-demo workload bounds; all are screening, not NASA landing thresholds.
MAX_CANDIDATES = 12
MAX_TIME_SAMPLES = 24
MAX_TOTAL_RAY_SAMPLES = 120_000
WEIGHTS = (0.40, 0.35, 0.25)


@dataclass(frozen=True, slots=True)
class MissionConstraints:
    min_sun_fraction: float = 0.50
    min_earth_fraction: float = 0.50
    min_simultaneous_fraction: float = 0.25
    max_darkness_seconds: float | None = None
    max_earth_outage_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("min_sun_fraction", "min_earth_fraction", "min_simultaneous_fraction"):
            value = getattr(self, name)
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite fraction in [0,1]")
        for name in ("max_darkness_seconds", "max_earth_outage_seconds"):
            value = getattr(self, name)
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f"{name} must be nonnegative and finite")


@dataclass(frozen=True, slots=True)
class ScreenedSite:
    latitude_deg: float
    longitude_deg: float
    suitability: Suitability
    score: float | None
    sun_fraction: float | None
    earth_fraction: float | None
    simultaneous_fraction: float | None
    longest_darkness_seconds: float | None
    longest_earth_outage_seconds: float | None
    unknown_sun_samples: int | None
    unknown_earth_samples: int | None
    unknown_simultaneous_samples: int | None
    total_samples: int | None
    checks: dict[str, bool | None]
    explanation: str
    terrain_dataset_id: str
    reference_frame: str
    kernel_manifest_id: str | None


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    candidates: tuple[ScreenedSite, ...]
    recommendations: tuple[ScreenedSite, ...]
    resolution: Resolution
    requested_count: int
    generated_count: int
    suitable_count: int
    unsuitable_count: int
    insufficient_count: int
    dataset_id: str
    frame: str
    processing_seconds: float
    screening_scope: str
    fidelity: str


def _halton(index: int, base: int) -> float:
    value, multiplier = 0.0, 1.0 / base
    while index:
        index, remainder = divmod(index, base)
        value += remainder * multiplier
        multiplier /= base
    return value


def generate_candidate_sites(
    dem: TerrainSource,
    count: int,
    *,
    max_distance_km: float = 2.0,
    interpolation: Literal["nearest", "bilinear"] = "bilinear",
) -> tuple[tuple[float, float], ...]:
    """Deterministic low-discrepancy sampling in the *actual opened raster*.

    Inset by search radius for conservative directional edge protection; verify
    each selected pixel via the existing DEM sampler (including nodata).
    Uses private raster extent only for discovery, never for elevation physics.
    """
    if type(count) is not int or not 1 <= count <= MAX_CANDIDATES:
        raise ValueError(f"candidate_count must be between 1 and {MAX_CANDIDATES}")
    if not isfinite(max_distance_km) or not 0 < max_distance_km <= 20:
        raise ValueError("candidate search radius must be in (0,20] km")
    if interpolation not in ("nearest", "bilinear"):
        raise ValueError("unsupported interpolation")
    metadata = cast(TerrainMetadata, dem.metadata)
    if getattr(metadata, "frame", None) is not LunarFrame.ME_DE421:
        raise ValueError("candidate DEM must use MOON_ME_DE421")
    if not isinstance(getattr(metadata, "dataset_id", None), str):
        raise ValueError("DEM dataset provenance missing")
    raster = getattr(dem, "_open_raster", None)
    if not callable(raster):
        raise ValueError("candidate discovery requires an open LunarDEM raster")
    src = raster()
    bounds = src.bounds
    # 10% radial allowance plus 4 pixels for bilinear sampling and projection.
    inset = max_distance_km * 1100.0 + 4.0 * metadata.pixel_size_m
    xmin, xmax = bounds.left + inset, bounds.right - inset
    ymin, ymax = bounds.bottom + inset, bounds.top - inset
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("DEM footprint too small for requested horizon radius")
    found: list[tuple[float, float]] = []
    cells: set[tuple[int, int]] = set()
    # Low-discrepancy sampling over projected metres avoids polar longitude bias.
    # Attempt budget is constant-bounded and deterministic; no random seeds.
    for i in range(1, count * 48 + 1):
        x = xmin + (xmax - xmin) * _halton(i, 2)
        y = ymin + (ymax - ymin) * _halton(i, 3)
        lat, lon = south_polar_inverse(
            x,
            y,
            central_meridian_deg=metadata.central_meridian_deg,
            radius_m=metadata.reference_radius_m,
        )
        col, row = (~src.transform) @ (x, y)
        key = (int(row), int(col))
        if key in cells:
            continue
        try:
            sample = dem.sample(lat, lon, interpolation=interpolation)
        except TerrainDataError:
            continue
        if not isfinite(sample.elevation_m) or sample.dataset_id != metadata.dataset_id:
            continue
        cells.add(key)
        found.append((lat, lon))
        if len(found) == count:
            break
    return tuple(found)


def _longest(timeline: VisibilityTimeline, category: str) -> float:
    return max(
        (w.estimated_duration_seconds for w in timeline.windows if w.category == category),
        default=0.0,
    )


def _score_site(
    lat: float,
    lon: float,
    timeline: VisibilityTimeline,
    constraints: MissionConstraints,
    dataset_id: str,
) -> ScreenedSite:
    metrics = timeline.metrics
    missing = (
        metrics.sun_unknown_samples > 0
        or metrics.earth_unknown_samples > 0
        or metrics.simultaneous_unknown_samples > 0
        or timeline.terrain_dataset_id != dataset_id
        or timeline.frame is not LunarFrame.ME_DE421
    )
    sunlight = metrics.sampled_sun_fraction
    earth = metrics.sampled_earth_fraction
    both = metrics.sampled_simultaneous_fraction
    darkness = _longest(timeline, "darkness")
    outage = _longest(timeline, "earth_outage")
    checks: dict[str, bool | None] = {
        "min_sun_fraction": sunlight >= constraints.min_sun_fraction,
        "min_earth_fraction": earth >= constraints.min_earth_fraction,
        "min_simultaneous_fraction": both >= constraints.min_simultaneous_fraction,
        "max_darkness_seconds": (
            None
            if constraints.max_darkness_seconds is None
            else darkness <= constraints.max_darkness_seconds
        ),
        "max_earth_outage_seconds": (
            None
            if constraints.max_earth_outage_seconds is None
            else outage <= constraints.max_earth_outage_seconds
        ),
    }
    if missing:
        # Partial timelines are not sufficient for definitive weighted scoring.
        status: Suitability = "INSUFFICIENT_DATA"
        score = None
        for name in checks:
            checks[name] = None
        reason = "Incomplete scientific coverage; no definitive suitability score"
    else:
        score = WEIGHTS[0] * sunlight + WEIGHTS[1] * earth + WEIGHTS[2] * both
        status = "SUITABLE" if all(v is not False for v in checks.values()) else "UNSUITABLE"
        reason = (
            "Meets configured visibility screening thresholds"
            if status == "SUITABLE"
            else "Fails one or more configured visibility screening thresholds"
        )
    return ScreenedSite(
        lat,
        lon,
        status,
        score,
        sunlight,
        earth,
        both,
        darkness,
        outage,
        metrics.sun_unknown_samples,
        metrics.earth_unknown_samples,
        metrics.simultaneous_unknown_samples,
        len(timeline.samples),
        checks,
        reason,
        dataset_id,
        timeline.frame.value,
        timeline.kernel_manifest_id,
    )


def recommend_lunar_sites(
    dem: TerrainSource,
    *,
    start_utc: str,
    end_utc: str,
    sampling_seconds: int,
    candidate_count: int = 8,
    max_recommendations: int = 5,
    observer_height_m: float = 2.0,
    max_distance_km: float = 2.0,
    step_m: float = 160.0,
    interpolation: Literal["nearest", "bilinear"] = "bilinear",
    constraints: MissionConstraints | None = None,
    repository_root: Path | None = None,
    timeline_evaluator: TimelineEvaluator = analyze_visibility_timeline,
    candidate_generator: Callable[..., tuple[tuple[float, float], ...]] = generate_candidate_sites,
) -> RecommendationResult:
    """Screen the sampled DEM footprint using BE-013. No global Moon claims."""
    t0 = perf_counter()
    if type(candidate_count) is not int or not 1 <= candidate_count <= MAX_CANDIDATES:
        raise ValueError(f"candidate_count must be between 1 and {MAX_CANDIDATES}")
    if type(max_recommendations) is not int or not 1 <= max_recommendations <= candidate_count:
        raise ValueError("max_recommendations must be within [1,candidate_count]")
    if not isfinite(observer_height_m) or not 0 <= observer_height_m <= 100_000:
        raise ValueError("observer height outside supported range")
    if not isfinite(step_m) or step_m <= 0:
        raise ValueError("step_m must be positive and finite")
    if constraints is None:
        constraints = MissionConstraints()
    if not isinstance(constraints, MissionConstraints):
        raise ValueError("invalid mission constraints")
    times = sample_utc_interval(start_utc, end_utc, sampling_seconds, max_samples=MAX_TIME_SAMPLES)
    rays_per_body = int(max_distance_km * 1000 / step_m) + 1
    if candidate_count * len(times) * 2 * rays_per_body > MAX_TOTAL_RAY_SAMPLES:
        raise ValueError("Recommendation workload exceeds bounded terrain-ray budget")
    if getattr(dem.metadata, "frame", None) is not LunarFrame.ME_DE421:
        raise ValueError("DEM reference frame must be MOON_ME_DE421")
    dataset_id = cast(TerrainMetadata, dem.metadata).dataset_id
    locations = candidate_generator(
        dem, candidate_count, max_distance_km=max_distance_km, interpolation=interpolation
    )
    output: list[ScreenedSite] = []
    for latitude_deg, longitude_deg in locations:
        try:
            timeline = timeline_evaluator(
                latitude_deg,
                longitude_deg,
                start_utc,
                end_utc,
                sampling_seconds,
                observer_height_m=observer_height_m,
                mode="terrain_aware",
                dem=dem,
                max_distance_km=max_distance_km,
                step_m=step_m,
                interpolation=interpolation,
                repository_root=repository_root,
            )
            output.append(
                _score_site(latitude_deg, longitude_deg, timeline, constraints, dataset_id)
            )
        except TerrainDataError:
            output.append(
                ScreenedSite(
                    latitude_deg,
                    longitude_deg,
                    "INSUFFICIENT_DATA",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    {},
                    "Terrain coverage insufficient for this candidate",
                    dataset_id,
                    LunarFrame.ME_DE421.value,
                    None,
                )
            )
    suitable = sorted(
        (site for site in output if site.suitability == "SUITABLE"),
        key=lambda site: (-cast(float, site.score), site.latitude_deg, site.longitude_deg),
    )
    suitable_count = len(suitable)
    insufficient_count = sum(site.suitability == "INSUFFICIENT_DATA" for site in output)
    if suitable_count:
        resolution: Resolution = "suitable_candidates"
    elif not output or insufficient_count == len(output):
        resolution = "insufficient_data"
    else:
        resolution = "no_suitable_candidates"
    return RecommendationResult(
        tuple(output),
        tuple(suitable[:max_recommendations]),
        resolution,
        candidate_count,
        len(locations),
        suitable_count,
        sum(site.suitability == "UNSUITABLE" for site in output),
        insufficient_count,
        dataset_id,
        LunarFrame.ME_DE421.value,
        perf_counter() - t0,
        "Deterministic, non-exhaustive screening inside loaded NASA LOLA DEM footprint",
        "BE-013 sampled Sun/Earth point-center terrain visibility; no landing-hazard certification",
    )
