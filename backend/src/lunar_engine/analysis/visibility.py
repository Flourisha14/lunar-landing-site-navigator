"""Terrain-aware geometric SUN/EARTH center visibility; no illumination or RF claim.

Uses verified SPICE DE421/DE440 adapter and the existing BE-010 terrain ray.
SPICE uses geometric positions (aberration NONE), not light-time apparent centers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import isclose, isfinite
from pathlib import Path
from typing import Literal

from lunar_engine.astronomy.ephemeris import canonical_utc
from lunar_engine.astronomy.geometry import CelestialDirection, CelestialGeometry
from lunar_engine.coordinates.frame_transform import analyze_geometry_in_dem_frame
from lunar_engine.core.conventions import LunarFrame, LunarLocation
from lunar_engine.terrain.dem import TerrainDataError
from lunar_engine.terrain.horizon import HorizonRay, TerrainSource, terrain_horizon_ray


class VisibilityStatus(StrEnum):
    VISIBLE = "visible"
    OBSTRUCTED = "obstructed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BodyVisibility:
    body: Literal["SUN", "EARTH"]
    status: VisibilityStatus
    azimuth_deg: float | None
    elevation_deg: float
    terrain_horizon_deg: float | None
    clearance_deg: float | None
    horizon: HorizonRay | None
    reason: str | None
    fidelity: str = "geometric_point_center_spice_none_finite_sampled_dem"

    @property
    def visible(self) -> bool | None:
        """Tri-state visibility: NEVER collapse UNKNOWN into False."""
        if self.status is VisibilityStatus.UNKNOWN:
            return None
        return self.status is VisibilityStatus.VISIBLE


@dataclass(frozen=True, slots=True)
class TerrainVisibilityResult:
    observer: LunarLocation
    observer_height_m: float
    timestamp_utc: str
    frame: LunarFrame
    terrain_dataset_id: str
    kernel_manifest_id: str
    max_distance_km: float
    step_m: float
    interpolation: str
    sun: BodyVisibility
    earth: BodyVisibility
    ephemeris_aberration: str = "NONE"
    model: str = "spherical_radial_lunar_horizon_point_centers"


# Injectable only for deterministic analytical tests; production uses BUG-001.
GeometryFunction = Callable[..., CelestialGeometry]


def _body_visibility(
    *,
    body: Literal["SUN", "EARTH"],
    target: CelestialDirection,
    dem: TerrainSource,
    latitude_deg: float,
    longitude_deg: float,
    observer_height_m: float,
    max_distance_km: float,
    step_m: float,
    interpolation: Literal["nearest", "bilinear"],
) -> BodyVisibility:
    if target.body != body:
        raise ValueError("Celestial target identity mismatch")
    elevation = target.elevation_deg
    if not isfinite(elevation) or not -90.0 <= elevation <= 90.0:
        raise ValueError("Celestial elevation outside physical range")
    if target.position_moon_fixed.frame is not LunarFrame.ME_DE421:
        raise ValueError("Celestial target not in DEM's MOON_ME_DE421 frame")
    # Exactly vertical directions do not have a well-defined geographic azimuth.
    # Do not invent an azimuth or silently infer unobstructed DEM coverage.
    if target.azimuth_deg is None:
        return BodyVisibility(
            body,
            VisibilityStatus.UNKNOWN,
            None,
            elevation,
            None,
            None,
            None,
            "undefined_celestial_azimuth",
        )
    if not isfinite(target.azimuth_deg):
        raise ValueError("Celestial azimuth must be finite")
    ray = terrain_horizon_ray(
        dem,
        latitude_deg,
        longitude_deg,
        target.azimuth_deg,
        observer_height_m=observer_height_m,
        max_distance_km=max_distance_km,
        step_m=step_m,
        interpolation=interpolation,
    )
    if not ray.complete or ray.horizon_elevation_deg is None:
        return BodyVisibility(
            body,
            VisibilityStatus.UNKNOWN,
            target.azimuth_deg,
            elevation,
            None,
            None,
            ray,
            "incomplete_dem_coverage",
        )
    # Strict point-source test: equality is obstructed (tangency).
    clearance = elevation - ray.horizon_elevation_deg
    status = VisibilityStatus.VISIBLE if clearance > 0.0 else VisibilityStatus.OBSTRUCTED
    return BodyVisibility(
        body, status, target.azimuth_deg, elevation, ray.horizon_elevation_deg, clearance, ray, None
    )


def evaluate_terrain_visibility(
    dem: TerrainSource,
    latitude_deg: float,
    longitude_deg: float,
    timestamp_utc: str,
    *,
    observer_height_m: float = 2.0,
    max_distance_km: float = 30.0,
    step_m: float = 160.0,
    interpolation: Literal["nearest", "bilinear"] = "bilinear",
    repository_root: Path | None = None,
    geometry_provider: GeometryFunction | None = None,
) -> TerrainVisibilityResult:
    """Evaluate both bodies with ONE shared SPICE geometry computation.

    For production the caller must supply repository_root with verified DE421
    and DE440 lock files. The injected provider exists for unit tests only.
    """
    # Validate input *before* costly or side-effectful DEM/SPICE operations.
    observer_location = LunarLocation(latitude_deg, longitude_deg, 0.0, LunarFrame.ME_DE421)
    canonical = canonical_utc(timestamp_utc)
    if not isfinite(observer_height_m) or observer_height_m < 0:
        raise ValueError("Observer height must be finite and nonnegative")
    if not isfinite(max_distance_km) or not isfinite(step_m):
        raise ValueError("Ray distance and sampling step must be finite")
    if max_distance_km <= 0 or step_m <= 0:
        raise ValueError("Ray distance and sampling step must be positive")
    if interpolation not in ("nearest", "bilinear"):
        raise ValueError("Unsupported interpolation")
    metadata = getattr(dem, "metadata", None)
    if getattr(metadata, "frame", None) is not LunarFrame.ME_DE421:
        raise ValueError("DEM must be tagged MOON_ME_DE421")
    dataset_id = getattr(metadata, "dataset_id", None)
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ValueError("DEM source identifier required")
    # DEM origin sample is required; no fallback terrain elevation is ever used.
    observer_sample = dem.sample(
        observer_location.latitude_deg, observer_location.longitude_deg, interpolation=interpolation
    )
    if (
        observer_sample.location.frame is not LunarFrame.ME_DE421
        or observer_sample.dataset_id != dataset_id
    ):
        raise ValueError("Observer DEM sample metadata mismatch")
    if not isfinite(observer_sample.elevation_m):
        raise TerrainDataError("Nonfinite DEM observer elevation")
    elevation_km = (observer_sample.elevation_m + observer_height_m) / 1000.0
    observer = LunarLocation(
        observer_location.latitude_deg,
        observer_location.longitude_deg,
        elevation_km,
        LunarFrame.ME_DE421,
    )
    if geometry_provider is None:
        if repository_root is None:
            raise ValueError("repository_root required for verified SPICE geometry")
        geometry_provider = analyze_geometry_in_dem_frame
    if repository_root is None and geometry_provider is not analyze_geometry_in_dem_frame:
        # An artificial provider in unit tests does not need kernel files.
        repository_root = Path(".")
    assert repository_root is not None
    # BUG-001 adapter accepts terrain_elevation_km, but the parameter represents
    # the radial height of its site. Include instrument height for correct geometry.
    geometry = geometry_provider(
        observer.latitude_deg,
        observer.longitude_deg,
        canonical,
        terrain_elevation_km=elevation_km,
        repository_root=repository_root,
    )
    if geometry.frame is not LunarFrame.ME_DE421 or geometry.site.frame is not LunarFrame.ME_DE421:
        raise ValueError("Astronomy/terrain frames differ")
    if (
        not isclose(geometry.site.latitude_deg, observer.latitude_deg, abs_tol=1e-12)
        or not isclose(geometry.site.longitude_deg, observer.longitude_deg, abs_tol=1e-12)
        or not isclose(geometry.site.elevation_km, elevation_km, rel_tol=0.0, abs_tol=1e-9)
    ):
        raise ValueError("Astronomical site does not match terrain observer")
    if geometry.timestamp_utc != canonical:
        raise ValueError("Astronomical epoch mismatch")
    if geometry.aberration != "NONE":
        raise ValueError("Unexpected aberration model")
    sun = _body_visibility(
        body="SUN",
        target=geometry.sun,
        dem=dem,
        latitude_deg=observer.latitude_deg,
        longitude_deg=observer.longitude_deg,
        observer_height_m=observer_height_m,
        max_distance_km=max_distance_km,
        step_m=step_m,
        interpolation=interpolation,
    )
    earth = _body_visibility(
        body="EARTH",
        target=geometry.earth,
        dem=dem,
        latitude_deg=observer.latitude_deg,
        longitude_deg=observer.longitude_deg,
        observer_height_m=observer_height_m,
        max_distance_km=max_distance_km,
        step_m=step_m,
        interpolation=interpolation,
    )
    return TerrainVisibilityResult(
        observer,
        observer_height_m,
        canonical,
        LunarFrame.ME_DE421,
        dataset_id,
        geometry.kernel_manifest_id,
        max_distance_km,
        step_m,
        interpolation,
        sun,
        earth,
        geometry.aberration,
    )
