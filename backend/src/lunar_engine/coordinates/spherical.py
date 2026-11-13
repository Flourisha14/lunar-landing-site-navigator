"""Spherical lunar geometry only; no terrain normal or SPICE frame conversion."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, radians, sin

from lunar_engine.core.conventions import (
    LUNAR_REFERENCE_RADIUS_KM,
    ElevationDatum,
    LunarLocation,
    MoonFixedVector,
)


@dataclass(frozen=True, slots=True)
class LocalENUVector:
    """Vector in km relative to a given spherical site, with explicit metadata."""

    east_km: float
    north_km: float
    up_km: float
    site: LunarLocation


def geographic_to_cartesian(location: LunarLocation) -> MoonFixedVector:
    """Radial altitude above 1737.4 km sphere; axes are in location.frame."""
    if location.datum != ElevationDatum.MEAN_RADIUS_1737_4_KM:
        raise ValueError("Unsupported elevation datum")
    radius = LUNAR_REFERENCE_RADIUS_KM + location.elevation_km
    latitude = radians(location.latitude_deg)
    longitude = radians(location.longitude_deg)
    parallel = radius * cos(latitude)
    return MoonFixedVector(
        parallel * cos(longitude),
        parallel * sin(longitude),
        radius * sin(latitude),
        location.frame,
    )


def cartesian_to_geographic(
    vector: MoonFixedVector, *, datum: ElevationDatum = ElevationDatum.MEAN_RADIUS_1737_4_KM
) -> LunarLocation:
    """Invert spherical mapping. At exact poles, canonical longitude is zero."""
    if datum != ElevationDatum.MEAN_RADIUS_1737_4_KM:
        raise ValueError("Unsupported elevation datum")
    equatorial_radius = hypot(vector.x_km, vector.y_km)
    radius = hypot(equatorial_radius, vector.z_km)
    if radius == 0.0:
        raise ValueError("Undefined location at lunar centre")
    longitude = 0.0 if equatorial_radius == 0.0 else degrees(atan2(vector.y_km, vector.x_km))
    latitude = degrees(atan2(vector.z_km, equatorial_radius))
    return LunarLocation(
        latitude, longitude, radius - LUNAR_REFERENCE_RADIUS_KM, vector.frame, datum
    )


def enu_basis(site: LunarLocation) -> tuple[tuple[float, float, float], ...]:
    """Return east, north, radial-up row vectors in site Moon-fixed frame.

    The longitude is canonicalized to zero at exact poles by LunarLocation.
    """
    lat, lon = radians(site.latitude_deg), radians(site.longitude_deg)
    east = (-sin(lon), cos(lon), 0.0)
    north = (-sin(lat) * cos(lon), -sin(lat) * sin(lon), cos(lat))
    up = (cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat))
    return east, north, up


def surface_normal(site: LunarLocation) -> MoonFixedVector:
    """Outward unit radial normal of reference sphere, NOT of actual terrain."""
    up = enu_basis(site)[2]
    return MoonFixedVector(*up, site.frame)


def fixed_to_enu(vector: MoonFixedVector, site: LunarLocation) -> LocalENUVector:
    """Rotate a FREE vector; does not translate positions (km preserved)."""
    if vector.frame != site.frame:
        raise ValueError("Cannot mix lunar reference frames without a SPICE transform")

    axes = enu_basis(site)
    xyz = (vector.x_km, vector.y_km, vector.z_km)

    east = sum(axes[0][i] * xyz[i] for i in range(3))
    north = sum(axes[1][i] * xyz[i] for i in range(3))
    up = sum(axes[2][i] * xyz[i] for i in range(3))

    return LocalENUVector(
        east_km=east,
        north_km=north,
        up_km=up,
        site=site,
    )


def enu_to_fixed(vector: LocalENUVector) -> MoonFixedVector:
    """Rotate an ENU free vector into its site's Moon-fixed reference frame."""
    axes = enu_basis(vector.site)
    enu = (vector.east_km, vector.north_km, vector.up_km)

    x = sum(enu[j] * axes[j][0] for j in range(3))
    y = sum(enu[j] * axes[j][1] for j in range(3))
    z = sum(enu[j] * axes[j][2] for j in range(3))

    return MoonFixedVector(
        x_km=x,
        y_km=y,
        z_km=z,
        frame=vector.site.frame,
    )


def fixed_position_to_enu(position: MoonFixedVector, site: LunarLocation) -> LocalENUVector:
    """Subtract spherical site origin before rotating a position."""
    origin = geographic_to_cartesian(site)
    if position.frame != site.frame:
        raise ValueError("Cannot mix lunar reference frames")
    offset = MoonFixedVector(
        position.x_km - origin.x_km,
        position.y_km - origin.y_km,
        position.z_km - origin.z_km,
        site.frame,
    )
    return fixed_to_enu(offset, site)
