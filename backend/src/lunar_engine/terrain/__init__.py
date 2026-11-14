"""Lunar terrain sampling and horizon analysis."""

from .dem import LunarDEM, TerrainDataError, TerrainMetadata, TerrainSample
from .horizon import (
    HorizonPoint,
    HorizonProfile,
    HorizonRay,
    destination_on_sphere,
    obstruction_angle_deg,
    terrain_horizon_profile,
    terrain_horizon_ray,
)

__all__ = [
    "LunarDEM",
    "TerrainDataError",
    "TerrainMetadata",
    "TerrainSample",
    "HorizonPoint",
    "HorizonProfile",
    "HorizonRay",
    "destination_on_sphere",
    "obstruction_angle_deg",
    "terrain_horizon_profile",
    "terrain_horizon_ray",
]
