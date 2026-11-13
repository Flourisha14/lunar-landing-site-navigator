"""Explicit conventions and metadata; no SPICE or rendering dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite

LUNAR_REFERENCE_RADIUS_KM = 1737.4
"""Reference sphere radius in km, not a claim that the Moon is spherical."""


class LunarFrame(StrEnum):
    """Distinct NAIF frame names; conversions require an explicit transform."""

    ME = "MOON_ME_DE440_ME421"
    PA = "MOON_PA_DE440"
    IAU = "IAU_MOON"


class DistanceUnit(StrEnum):
    KM = "km"


class AngleUnit(StrEnum):
    DEG = "deg"
    RAD = "rad"


class DurationUnit(StrEnum):
    SECOND = "s"


class ElevationDatum(StrEnum):
    """Reference datum, NOT interchangeable with dataset-specific datums."""

    MEAN_RADIUS_1737_4_KM = "MOON_ME_REFERENCE_SPHERE_1737_4_KM"


class LongitudeConvention(StrEnum):
    EAST_POSITIVE_180 = "EAST_POSITIVE_[-180,180)"


class LatitudeConvention(StrEnum):
    PLANETOCENTRIC = "PLANETOCENTRIC_DEGREES"


def normalize_longitude_deg(longitude_deg: float) -> float:
    """Normalize east-positive longitude to [-180, 180), with positive zero."""
    if not isfinite(longitude_deg):
        raise ValueError("Longitude must be finite")
    result = (longitude_deg + 180.0) % 360.0 - 180.0
    return 0.0 if result == 0.0 else result


def parse_utc_timestamp(value: str) -> datetime:
    """Require ISO 8601 with Z, and reject leap seconds until SPICE support.

    UTC -> SPICE ET is NOT a constant offset; it will require a loaded LSK.
    """
    if not value.endswith("Z") or "T" not in value:
        raise ValueError("Timestamp must be ISO 8601 UTC ending in Z")
    try:
        timestamp = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("Invalid ISO 8601 UTC timestamp") from error
    if timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ValueError("Timestamp must be UTC")
    return timestamp


@dataclass(frozen=True, slots=True)
class LunarLocation:
    """Planetocentric coordinates in a specified lunar fixed reference frame.

    Longitude at either exact pole is canonically 0 degrees. Height is radial
    elevation above the declared reference sphere, NOT a geodetic height.
    """

    latitude_deg: float
    longitude_deg: float
    elevation_km: float
    frame: LunarFrame = LunarFrame.ME
    datum: ElevationDatum = ElevationDatum.MEAN_RADIUS_1737_4_KM

    def __post_init__(self) -> None:
        if not isfinite(self.latitude_deg) or not -90.0 <= self.latitude_deg <= 90.0:
            raise ValueError("Latitude must be finite and in [-90, 90]")
        if not isfinite(self.elevation_km):
            raise ValueError("Elevation must be finite")
        if LUNAR_REFERENCE_RADIUS_KM + self.elevation_km <= 0:
            raise ValueError("Radial distance must be positive")
        if not isinstance(self.frame, LunarFrame):
            raise TypeError("frame must be an explicit LunarFrame")
        if not isinstance(self.datum, ElevationDatum):
            raise TypeError("datum must be an explicit ElevationDatum")
        longitude = normalize_longitude_deg(self.longitude_deg)
        if abs(self.latitude_deg) == 90.0:
            longitude = 0.0
        object.__setattr__(self, "longitude_deg", longitude)


@dataclass(frozen=True, slots=True)
class MoonFixedVector:
    """Moon-centred Cartesian vector in km (+X prime, +Y east, +Z north)."""

    x_km: float
    y_km: float
    z_km: float
    frame: LunarFrame

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x_km, self.y_km, self.z_km)):
            raise ValueError("Vector components must be finite")
        if not isinstance(self.frame, LunarFrame):
            raise TypeError("frame must be an explicit LunarFrame")


@dataclass(frozen=True, slots=True)
class ScientificMetadata:
    """Serialization-ready metadata required on computed scientific results."""

    frame: LunarFrame
    datum: ElevationDatum | None
    distance_unit: DistanceUnit = DistanceUnit.KM
    angle_unit: AngleUnit = AngleUnit.DEG
    duration_unit: DurationUnit = DurationUnit.SECOND
    longitude_convention: LongitudeConvention = LongitudeConvention.EAST_POSITIVE_180
    latitude_convention: LatitudeConvention = LatitudeConvention.PLANETOCENTRIC
    kernel_manifest_id: str | None = None
    terrain_dataset_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.frame, LunarFrame):
            raise TypeError("frame must be LunarFrame")
        if self.datum is not None and not isinstance(self.datum, ElevationDatum):
            raise TypeError("datum must be ElevationDatum or None")


# Local East-North-Up is site-relative; no global ENU frame is implied.
# Future ENU vectors must carry the site and Moon-fixed frame metadata.
