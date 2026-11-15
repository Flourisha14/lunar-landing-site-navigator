"""Bounded LOLA terrain geometry in a selected site's lunar local ENU frame.

The spherical surface is converted into local tangent coordinates at the DEM
sampled site. Terrain is never extrapolated outside validated raster coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, ceil, cos, degrees, hypot, radians, sin

from lunar_engine.terrain.dem import LunarDEM, TerrainDataError

MAX_MESH_SIDE = 65


class TerrainOutsideCoverage(TerrainDataError):
    """Selected observer location has no supported DEM elevation."""


@dataclass(frozen=True, slots=True)
class TerrainMesh:
    latitude_deg: float
    longitude_deg: float
    center_elevation_m: float
    vertices: list[tuple[float, float, float]]
    indices: list[int]
    status: str
    valid_samples: int
    requested_samples: int
    radius_m: float
    sample_step_m: float
    grid_side: int
    metadata: dict[str, object]


def generate_terrain_mesh(
    dem: LunarDEM,
    latitude_deg: float,
    longitude_deg: float,
    *,
    radius_m: float = 5000.0,
    sample_step_m: float = 160.0,
) -> TerrainMesh:
    """Sample square ENU footprint (half-width ``radius_m``) from the DEM.

    Rows run north to south; columns run west to east. Coordinates are in
    metres; Babylon X=east, Y=up, Z=north. No vertical exaggeration.
    """
    if not (160 <= radius_m <= 5000 and 80 <= sample_step_m <= 640):
        raise ValueError("Terrain radius must be 160..5000 m; step must be 80..640 m")
    intervals = ceil(2 * radius_m / sample_step_m)
    side = intervals + 1
    if side > MAX_MESH_SIDE:
        raise ValueError(f"Terrain mesh exceeds {MAX_MESH_SIDE} samples per side")

    try:
        center = dem.sample(latitude_deg, longitude_deg, interpolation="bilinear")
    except TerrainDataError as exc:
        raise TerrainOutsideCoverage("Selected site lies outside valid LOLA DEM coverage") from exc

    lat = radians(center.location.latitude_deg)
    lon = radians(center.location.longitude_deg)
    r = dem.metadata.reference_radius_m
    h0 = center.elevation_m
    # Moon-fixed Cartesian unit vectors: radial/up, east, north.
    up = (cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat))
    east = (-sin(lon), cos(lon), 0.0)
    north = (-sin(lat) * cos(lon), -sin(lat) * sin(lon), cos(lat))
    basis = (east, up, north)

    positions: list[tuple[float, float, float]] = []
    ids: dict[tuple[int, int], int] = {}
    # Use exactly [-radius,+radius] to keep coverage and centering explicit.
    spacing = 2 * radius_m / intervals
    for row in range(side):
        n = radius_m - row * spacing
        for col in range(side):
            e = -radius_m + col * spacing
            d = hypot(e, n)
            theta = d / r
            if d:
                tangent = tuple((e * east[k] + n * north[k]) / d for k in range(3))
                direction = tuple(cos(theta) * up[k] + sin(theta) * tangent[k] for k in range(3))
            else:
                direction = up
            sample_lat = degrees(asin(max(-1.0, min(1.0, direction[2]))))
            sample_lon = degrees(atan2(direction[1], direction[0]))
            try:
                sample = dem.sample(sample_lat, sample_lon, interpolation="bilinear")
            except TerrainDataError:
                continue  # Explicit gap: never synthesize a height.
            world_offset = tuple(
                (r + sample.elevation_m) * direction[k] - (r + h0) * up[k]
                for k in range(3)
            )
            xyz = tuple(sum(world_offset[k] * axis[k] for k in range(3)) for axis in basis)
            ids[row, col] = len(positions)
            positions.append(xyz)

    indices: list[int] = []
    for row in range(side - 1):
        for col in range(side - 1):
            tl = ids.get((row, col))
            tr = ids.get((row, col + 1))
            bl = ids.get((row + 1, col))
            br = ids.get((row + 1, col + 1))
            # +Y-facing winding in the (East, Up, North) coordinate convention.
            if tl is not None and tr is not None and bl is not None:
                indices.extend((tl, tr, bl))
            if tr is not None and br is not None and bl is not None:
                indices.extend((tr, br, bl))

    if not indices:
        raise TerrainDataError("No supported terrain triangles in requested footprint")

    total = side * side
    meta = dem.metadata
    return TerrainMesh(
        latitude_deg=center.location.latitude_deg,
        longitude_deg=center.location.longitude_deg,
        center_elevation_m=h0,
        vertices=positions,
        indices=indices,
        status="complete" if len(positions) == total else "partial_coverage",
        valid_samples=len(positions),
        requested_samples=total,
        radius_m=radius_m,
        sample_step_m=spacing,
        grid_side=side,
        metadata={
            "dataset_id": meta.dataset_id,
            "source_filename": dem.path.name,
            "reference_frame": meta.frame.value,
            "reference_radius_m": r,
            "datum": meta.datum,
            "datum_confirmed": meta.datum_confirmed,
            "projection": meta.projection,
            "pixel_size_m": meta.pixel_size_m,
            "latitude_type": meta.latitude_type,
            "longitude_positive": meta.longitude_positive,
            "vertical_exaggeration": 1.0,
            "coordinate_frame": "local_east_up_north",
            "center_is_local_origin": True,
            "center_sample_interpolation": "bilinear",
            "frame_alignment_note": meta.source_frame_note,
            "visual_only": True,
            "limitations": "Render footprint is not a complete horizon/visibility model",
        },
    )
