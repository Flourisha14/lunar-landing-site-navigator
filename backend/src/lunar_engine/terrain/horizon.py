"""Terrain horizon against a spherical lunar reference, using 3-D ray geometry.

All positions and local ENU vectors use the DEM's *native* Moon-fixed frame.
A result with incomplete DEM coverage has no certified horizon angle.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, degrees, isfinite, pi, radians, sin, sqrt
from typing import Literal, Protocol

from lunar_engine.coordinates.spherical import enu_basis, geographic_to_cartesian
from lunar_engine.core.conventions import LUNAR_REFERENCE_RADIUS_KM, LunarFrame, LunarLocation
from lunar_engine.terrain.dem import TerrainDataError

MAX_SAMPLES_PER_RAY = 100_000
MAX_PROFILE_RAYS = 720


class TerrainSampleLike(Protocol):
    location: LunarLocation
    elevation_m: float
    dataset_id: str


class TerrainSource(Protocol):
    metadata: object

    def sample(
        self,
        latitude_deg: float,
        longitude_deg: float,
        *,
        interpolation: Literal["nearest", "bilinear"] = "bilinear",
    ) -> TerrainSampleLike: ...


@dataclass(frozen=True, slots=True)
class HorizonPoint:
    azimuth_deg: float
    arc_distance_km: float
    latitude_deg: float
    longitude_deg: float
    elevation_m: float
    sightline_elevation_deg: float


@dataclass(frozen=True, slots=True)
class HorizonRay:
    observer: LunarLocation
    observer_terrain_elevation_m: float
    observer_height_m: float
    azimuth_deg: float
    horizon_elevation_deg: float | None
    controlling_point: HorizonPoint | None
    coverage: str
    samples_completed: int
    samples_requested: int
    first_missing_distance_km: float | None
    max_distance_km: float
    step_m: float
    interpolation: str
    dataset_id: str
    frame: LunarFrame
    reference_radius_km: float = LUNAR_REFERENCE_RADIUS_KM
    model: str = "3d_radial_sphere_straight_line"

    @property
    def complete(self) -> bool:
        return self.coverage == "complete"


@dataclass(frozen=True, slots=True)
class HorizonProfile:
    observer: LunarLocation
    observer_height_m: float
    rays: tuple[HorizonRay, ...]
    complete: bool
    dataset_id: str
    frame: LunarFrame


def destination_on_sphere(
    site: LunarLocation, azimuth_deg: float, arc_distance_km: float
) -> tuple[float, float]:
    """Great-circle destination in site's lunar frame (arc distance in km)."""
    if not all(isfinite(v) for v in (azimuth_deg, arc_distance_km)):
        raise ValueError("Azimuth and arc distance must be finite")
    if not 0 <= arc_distance_km < pi * LUNAR_REFERENCE_RADIUS_KM:
        raise ValueError("Arc distance outside supported range")
    east, north, up = enu_basis(site)
    bearing = radians(azimuth_deg % 360.0)
    theta = arc_distance_km / LUNAR_REFERENCE_RADIUS_KM
    tangent = tuple(sin(bearing) * east[i] + cos(bearing) * north[i] for i in range(3))
    xyz = tuple(cos(theta) * up[i] + sin(theta) * tangent[i] for i in range(3))
    lat = degrees(atan2(xyz[2], sqrt(xyz[0] ** 2 + xyz[1] ** 2)))
    lon = degrees(atan2(xyz[1], xyz[0])) if xyz[0] != 0 or xyz[1] != 0 else 0.0
    destination = LunarLocation(lat, lon, 0.0, site.frame)
    return destination.latitude_deg, destination.longitude_deg


def obstruction_angle_deg(
    arc_distance_km: float,
    target_terrain_elevation_m: float,
    observer_terrain_elevation_m: float,
    observer_height_m: float = 0.0,
) -> float:
    """Exact signed elevation for two radial heights on a spherical reference.

    Negative values are meaningful: even a feature below local horizontal can
    be the controlling terrain point. Never clamp negative horizons to zero.
    """
    values = (
        arc_distance_km,
        target_terrain_elevation_m,
        observer_terrain_elevation_m,
        observer_height_m,
    )
    if not all(isfinite(v) for v in values):
        raise ValueError("Inputs must be finite")
    if not 0 < arc_distance_km < pi * LUNAR_REFERENCE_RADIUS_KM or observer_height_m < 0:
        raise ValueError("Invalid distance or observer height")
    reference = LUNAR_REFERENCE_RADIUS_KM
    observer_radius = reference + (observer_terrain_elevation_m + observer_height_m) / 1000.0
    target_radius = reference + target_terrain_elevation_m / 1000.0
    if min(observer_radius, target_radius) <= 0:
        raise ValueError("Terrain radial distance must be positive")
    theta = arc_distance_km / reference
    east_north_magnitude = target_radius * sin(theta)
    up_component = target_radius * cos(theta) - observer_radius
    return degrees(atan2(up_component, east_north_magnitude))


def _validated_metadata(dem: TerrainSource) -> tuple[LunarFrame, str]:
    metadata = getattr(dem, "metadata", None)
    frame = getattr(metadata, "frame", None)
    dataset_id = getattr(metadata, "dataset_id", None)
    reference_radius = getattr(metadata, "reference_radius_m", None)
    if frame is not LunarFrame.ME_DE421:
        raise ValueError("Terrain horizon requires a DE421-native DEM; do not relabel frames")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ValueError("Missing terrain source provenance")
    if (
        reference_radius is None
        or abs(float(reference_radius) / 1000 - LUNAR_REFERENCE_RADIUS_KM) > 1e-9
    ):
        raise ValueError("DEM/reference-sphere datum mismatch")
    return frame, dataset_id


def _sample_checked(
    dem: TerrainSource,
    latitude_deg: float,
    longitude_deg: float,
    interpolation: Literal["nearest", "bilinear"],
    frame: LunarFrame,
    dataset_id: str,
) -> TerrainSampleLike:
    sample = dem.sample(latitude_deg, longitude_deg, interpolation=interpolation)
    if sample.location.frame is not frame or sample.dataset_id != dataset_id:
        raise ValueError("DEM sample frame or provenance differs from declared metadata")
    if not isfinite(sample.elevation_m):
        raise TerrainDataError("Nonfinite DEM elevation")
    return sample


def terrain_horizon_ray(
    dem: TerrainSource,
    latitude_deg: float,
    longitude_deg: float,
    azimuth_deg: float,
    *,
    observer_height_m: float = 2.0,
    max_distance_km: float = 30.0,
    step_m: float = 160.0,
    interpolation: Literal["nearest", "bilinear"] = "bilinear",
) -> HorizonRay:
    """Maximum signed terrain-elevation angle along a DEM-native great-circle ray.

    Samples every at-most step_m along the reference sphere, including the endpoint.
    Missing samples yield coverage='incomplete', angle=None (never false-clear).
    """
    frame, dataset_id = _validated_metadata(dem)
    values = (azimuth_deg, observer_height_m, max_distance_km, step_m)
    if not all(isfinite(v) for v in values):
        raise ValueError("Horizon configuration must be finite")
    if (
        observer_height_m < 0
        or step_m <= 0
        or not 0 < max_distance_km < pi * LUNAR_REFERENCE_RADIUS_KM
    ):
        raise ValueError("Invalid observer height, step, or distance")
    if interpolation not in {"nearest", "bilinear"}:
        raise ValueError("Unsupported DEM interpolation")
    count = max(1, ceil(max_distance_km * 1000 / step_m))
    if count > MAX_SAMPLES_PER_RAY:
        raise ValueError("Too many samples; increase step_m or shorten the ray")
    azimuth = azimuth_deg % 360.0
    site = LunarLocation(latitude_deg, longitude_deg, 0.0, frame)
    observer = _sample_checked(
        dem, site.latitude_deg, site.longitude_deg, interpolation, frame, dataset_id
    )
    observer_site = LunarLocation(
        site.latitude_deg,
        site.longitude_deg,
        (observer.elevation_m + observer_height_m) / 1000.0,
        frame,
    )
    observer_vector = geographic_to_cartesian(observer_site)
    east, north, up = enu_basis(observer_site)
    maximum: HorizonPoint | None = None
    for index in range(1, count + 1):
        distance = min(index * step_m / 1000, max_distance_km)
        latitude, longitude = destination_on_sphere(site, azimuth, distance)
        try:
            terrain = _sample_checked(dem, latitude, longitude, interpolation, frame, dataset_id)
        except TerrainDataError:
            return HorizonRay(
                observer_site,
                observer.elevation_m,
                observer_height_m,
                azimuth,
                None,
                maximum,
                "incomplete",
                index - 1,
                count,
                distance,
                max_distance_km,
                step_m,
                interpolation,
                dataset_id,
                frame,
            )
        terrain_location = LunarLocation(latitude, longitude, terrain.elevation_m / 1000, frame)
        target_vector = geographic_to_cartesian(terrain_location)
        delta = (
            target_vector.x_km - observer_vector.x_km,
            target_vector.y_km - observer_vector.y_km,
            target_vector.z_km - observer_vector.z_km,
        )
        # Local radial-horizontal, independent of meridian/polar discontinuities.
        horizontal = sqrt(
            sum(sum(delta[i] * axis[i] for i in range(3)) ** 2 for axis in (east, north))
        )
        vertical = sum(delta[i] * up[i] for i in range(3))
        angle = degrees(atan2(vertical, horizontal))
        if maximum is None or angle > maximum.sightline_elevation_deg:
            maximum = HorizonPoint(
                azimuth, distance, latitude, longitude, terrain.elevation_m, angle
            )
    return HorizonRay(
        observer_site,
        observer.elevation_m,
        observer_height_m,
        azimuth,
        maximum.sightline_elevation_deg if maximum else None,
        maximum,
        "complete",
        count,
        count,
        None,
        max_distance_km,
        step_m,
        interpolation,
        dataset_id,
        frame,
    )


def terrain_horizon_profile(
    dem: TerrainSource,
    latitude_deg: float,
    longitude_deg: float,
    *,
    azimuth_step_deg: float = 10.0,
    observer_height_m: float = 2.0,
    max_distance_km: float = 30.0,
    step_m: float = 160.0,
    interpolation: Literal["nearest", "bilinear"] = "bilinear",
) -> HorizonProfile:
    """Generate azimuth rays [0,360) without a duplicate 360-degree endpoint."""
    _validated_metadata(dem)
    if not isfinite(azimuth_step_deg) or not 0 < azimuth_step_deg <= 360:
        raise ValueError("Azimuth step must lie in (0,360]")
    count = ceil(360.0 / azimuth_step_deg)
    if count > MAX_PROFILE_RAYS:
        raise ValueError("Too many azimuth rays")
    rays = tuple(
        terrain_horizon_ray(
            dem,
            latitude_deg,
            longitude_deg,
            i * azimuth_step_deg,
            observer_height_m=observer_height_m,
            max_distance_km=max_distance_km,
            step_m=step_m,
            interpolation=interpolation,
        )
        for i in range(count)
    )
    return HorizonProfile(
        rays[0].observer,
        observer_height_m,
        rays,
        all(ray.complete for ray in rays),
        rays[0].dataset_id,
        rays[0].frame,
    )
