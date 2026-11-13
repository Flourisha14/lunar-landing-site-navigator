"""Geometric Sun and Earth local directions above a spherical lunar horizon."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot, isfinite, sqrt
from pathlib import Path

from lunar_engine.astronomy.ephemeris import EphemerisPosition, default_provider
from lunar_engine.coordinates.spherical import fixed_to_enu, geographic_to_cartesian
from lunar_engine.core.conventions import LunarFrame, LunarLocation, MoonFixedVector


@dataclass(frozen=True, slots=True)
class CelestialDirection:
    """Point-source geometric direction from the site to a target center."""

    body: str
    azimuth_deg: float | None  # None for a zenith/nadir-aligned ray
    elevation_deg: float
    east_unit: float
    north_unit: float
    up_unit: float
    range_km: float
    geometric_visible: bool  # center of target strictly above spherical local horizon
    position_moon_fixed: MoonFixedVector


@dataclass(frozen=True, slots=True)
class CelestialGeometry:
    """Renderer-independent scientific result with shared epoch and provenance."""

    site: LunarLocation
    timestamp_utc: str
    et_seconds: float
    frame: LunarFrame
    kernel_manifest_id: str
    sun: CelestialDirection
    earth: CelestialDirection
    aberration: str = "NONE"
    horizon_model: str = "spherical_radial_tangent_plane"
    distance_unit: str = "km"
    angular_unit: str = "deg"


def local_direction(target: EphemerisPosition, site: LunarLocation) -> CelestialDirection:
    """Compute topocentric geometry from Moon-centred target minus fixed site position."""
    if target.position.frame != site.frame:
        raise ValueError("Target and observer must use the same Moon-fixed frame")
    site_xyz = geographic_to_cartesian(site)
    offset = MoonFixedVector(
        target.position.x_km - site_xyz.x_km,
        target.position.y_km - site_xyz.y_km,
        target.position.z_km - site_xyz.z_km,
        site.frame,
    )
    enu = fixed_to_enu(offset, site)
    horizontal = hypot(enu.east_km, enu.north_km)
    distance = sqrt(horizontal * horizontal + enu.up_km * enu.up_km)
    if distance == 0.0 or not isfinite(distance):
        raise ValueError("Undefined line of sight: target coincides with site")
    east = enu.east_km / distance
    north = enu.north_km / distance
    up = enu.up_km / distance
    elevation = degrees(atan2(enu.up_km, horizontal))
    # At exact zenith/nadir azimuth is mathematically undefined.
    azimuth = None if horizontal <= distance * 1e-14 else degrees(atan2(east, north)) % 360.0
    return CelestialDirection(
        body=target.body,
        azimuth_deg=azimuth,
        elevation_deg=elevation,
        east_unit=east,
        north_unit=north,
        up_unit=up,
        range_km=distance,
        geometric_visible=elevation > 0.0,
        position_moon_fixed=target.position,
    )


def analyze_celestial_geometry(
    latitude_deg: float,
    longitude_deg: float,
    timestamp_utc: str,
    *,
    elevation_km: float = 0.0,
    frame: LunarFrame = LunarFrame.ME,
    repository_root: Path | None = None,
) -> CelestialGeometry:
    """Compute geometric Sun/Earth center directions; requires local verified SPICE kernels.

    This is NOT terrain-aware lighting, atmospheric refraction, solar-disk illumination,
    or a guarantee of direct-to-Earth radio connectivity.
    """
    site = LunarLocation(latitude_deg, longitude_deg, elevation_km, frame)
    with default_provider(repository_root) as provider:
        sun = provider.position("SUN", timestamp_utc, frame)
        earth = provider.position("EARTH", timestamp_utc, frame)
        return CelestialGeometry(
            site=site,
            timestamp_utc=sun.timestamp_utc,
            et_seconds=sun.et_seconds,
            frame=frame,
            kernel_manifest_id=provider.kernel_manifest_id,
            sun=local_direction(sun, site),
            earth=local_direction(earth, site),
        )
