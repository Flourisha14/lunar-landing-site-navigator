"""LOLA south-polar DEM sampling with explicit planetary datum and projection.

No raster data is bundled. This module never silently falls back to zero elevation.
The current spherical polar projection is verified against the chosen COG metadata
at acquisition time; any unknown/mismatched source must be rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, atan2, cos, degrees, floor, hypot, isfinite, pi, radians, sin, tan
from pathlib import Path
from typing import Any, Literal

from lunar_engine.coordinates.spherical import geographic_to_cartesian
from lunar_engine.core.conventions import (
    LUNAR_REFERENCE_RADIUS_KM,
    LunarFrame,
    LunarLocation,
    MoonFixedVector,
)

DEMO_PRODUCT = "LDEM_80S_80MPP_ADJ.TIF"
SOUTH_POLE_RADIUS_M = LUNAR_REFERENCE_RADIUS_KM * 1000.0


class TerrainDataError(ValueError):
    """No defensible terrain result is available for this query."""


@dataclass(frozen=True, slots=True)
class TerrainMetadata:
    dataset_id: str
    source_filename: str
    frame: LunarFrame = LunarFrame.ME_DE421
    source_frame_note: str = (
        "Source: MOON_ME DE421. "
        "SPICE engine: MOON_ME_DE440_ME421. "
        "Cross-realization alignment not independently validated."
    )
    reference_radius_m: float = SOUTH_POLE_RADIUS_M
    pixel_size_m: float = 80.0
    datum: str = "radial_height_above_1737400m_sphere"
    longitude_positive: str = "east"
    latitude_type: str = "planetocentric"
    projection: str = "south_polar_stereographic_sphere"
    central_meridian_deg: float = 0.0
    projection_scale_at_pole: float = 1.0
    height_unit: str = "m"
    datum_confirmed: bool = False  # Must inspect publisher label/metadata before scientific use.

    def __post_init__(self) -> None:
        if self.frame != LunarFrame.ME_DE421:
            raise ValueError(
                "DEM is declared only in its source ME frame; no implicit PA conversion"
            )
        if self.reference_radius_m != SOUTH_POLE_RADIUS_M:
            raise ValueError("DEM radius must match BE-002 reference sphere")
        if self.datum != "radial_height_above_1737400m_sphere":
            raise ValueError("Unsupported DEM elevation datum")
        if self.projection != "south_polar_stereographic_sphere":
            raise ValueError("Unsupported projection")
        if self.projection_scale_at_pole != 1.0:
            raise ValueError("Only pole-tangent stereographic k=1 is supported")
        if self.height_unit != "m" or self.latitude_type != "planetocentric":
            raise ValueError("Only metre, planetocentric DEM supported")
        if self.longitude_positive != "east":
            raise ValueError("Only east-positive DEM longitude supported")
        if not isfinite(self.central_meridian_deg):
            raise ValueError("Invalid projection meridian")
        if self.pixel_size_m <= 0 or not isfinite(self.pixel_size_m):
            raise ValueError("Invalid pixel size")


DEFAULT_LOLA_METADATA = TerrainMetadata(
    dataset_id="GSFC_PGDA_LOLA_SOUTH_POLE_LDEM_80S_80MPP_ADJ",
    source_filename=DEMO_PRODUCT,
)


def south_polar_stereographic_xy(
    latitude_deg: float,
    longitude_deg: float,
    *,
    central_meridian_deg: float = 0.0,
    radius_m: float = SOUTH_POLE_RADIUS_M,
) -> tuple[float, float]:
    """Project east-positive planetocentric coordinates onto a south-pole tangent plane.

    Snyder: rho=2R*tan(pi/4 + phi/2), x=rho*sin(lam-lam0),
    y=rho*cos(lam-lam0). Unit: metres.
    """
    if not all(isfinite(x) for x in (latitude_deg, longitude_deg, radius_m)):
        raise ValueError("Nonfinite projection input")
    if not -90 <= latitude_deg < 0 or radius_m <= 0:
        raise ValueError("South polar projection requires latitude [-90,0) and R>0")
    rho = 2 * radius_m * tan(pi / 4 + radians(latitude_deg) / 2)
    delta = radians(longitude_deg - central_meridian_deg)
    return rho * sin(delta), rho * cos(delta)


def south_polar_inverse(
    x_m: float,
    y_m: float,
    *,
    central_meridian_deg: float = 0.0,
    radius_m: float = SOUTH_POLE_RADIUS_M,
) -> tuple[float, float]:
    if not all(isfinite(v) for v in (x_m, y_m, central_meridian_deg, radius_m)) or radius_m <= 0:
        raise ValueError("Invalid inverse-projection input")
    rho = hypot(x_m, y_m)
    lat = degrees(2 * atan(rho / (2 * radius_m)) - pi / 2)
    lon = 0.0 if rho == 0 else (degrees(atan2(x_m, y_m)) + central_meridian_deg + 180) % 360 - 180
    return lat, lon


@dataclass(frozen=True, slots=True)
class TerrainSample:
    location: LunarLocation
    elevation_m: float
    dataset_id: str
    interpolation: str
    pixel_row: float
    pixel_col: float
    projected_x_m: float
    projected_y_m: float

    @property
    def elevation_km(self) -> float:
        return self.elevation_m / 1000.0

    def to_moon_fixed(self) -> MoonFixedVector:
        site = LunarLocation(
            self.location.latitude_deg,
            self.location.longitude_deg,
            self.elevation_km,
            self.location.frame,
        )
        return geographic_to_cartesian(site)


class LunarDEM:
    """Lazy rasterio-backed loader; all external data errors are explicit."""

    def __init__(self, path: str | Path, metadata: TerrainMetadata = DEFAULT_LOLA_METADATA):
        self.path = Path(path)
        self.metadata = metadata
        self._src: Any | None = None

    def __enter__(self) -> LunarDEM:
        try:
            import rasterio  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("Install rasterio with pip install -e '.[science]'") from exc
        if not self.path.is_file():
            raise TerrainDataError(f"DEM file not found: {self.path}")
        if not self.metadata.datum_confirmed:
            raise TerrainDataError(
                "DEM vertical datum not verified: set datum_confirmed=True only after "
                "checking GSFC source metadata and recording the evidence"
            )
        self._src = rasterio.open(self.path)
        try:
            if self._src.count != 1:
                raise TerrainDataError("Only single-band DEM datasets are supported")
            transform = self._src.transform
            if abs(transform.b) > 1e-9 or abs(transform.d) > 1e-9:
                raise TerrainDataError("Rotated/sheared DEM grids are not supported")
            if (
                abs(abs(transform.a) - self.metadata.pixel_size_m) > 0.1
                or abs(abs(transform.e) - self.metadata.pixel_size_m) > 0.1
            ):
                raise TerrainDataError("DEM pixel spacing differs from declared metadata")
            # Rasterio CRS must be checked against metadata before scientific use.
            crs = self._src.crs
            if crs is not None:
                properties = crs.to_dict()
                if properties.get("proj") not in ("stere",):
                    raise TerrainDataError("DEM CRS is not stereographic")
                lat0 = float(properties.get("lat_0", -90))
                lon0 = float(properties.get("lon_0", 0))
                if abs(lat0 + 90) > 1e-7 or abs(lon0 - self.metadata.central_meridian_deg) > 1e-7:
                    raise TerrainDataError("DEM projection origin differs from metadata")
                if "R" not in properties and "a" not in properties:
                    raise TerrainDataError("DEM CRS has no identifiable lunar radius")
                radius = float(properties.get("R", properties.get("a")))
                if abs(radius - self.metadata.reference_radius_m) > 0.1:
                    raise TerrainDataError("DEM projection reference radius mismatch")
                if abs(float(properties.get("k", 1.0)) - 1.0) > 1e-8:
                    raise TerrainDataError("DEM stereographic scale factor mismatch")
                if properties.get("units", "m") != "m":
                    raise TerrainDataError("DEM coordinate units not metres")
            else:
                raise TerrainDataError("DEM CRS missing; cannot validate planetary projection")
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self._src is not None:
            self._src.close()
            self._src = None

    def _open_raster(self) -> Any:
        if self._src is None:
            raise RuntimeError("Use LunarDEM as a context manager")
        return self._src

    def sample(
        self,
        latitude_deg: float,
        longitude_deg: float,
        *,
        interpolation: Literal["nearest", "bilinear"] = "bilinear",
    ) -> TerrainSample:
        src = self._open_raster()
        if interpolation not in ("nearest", "bilinear"):
            raise ValueError("Unsupported interpolation")
        site = LunarLocation(latitude_deg, longitude_deg, 0.0, self.metadata.frame)
        if site.latitude_deg >= 0:
            raise TerrainDataError("Outside supported south-polar projection")
        x, y = south_polar_stereographic_xy(
            site.latitude_deg,
            site.longitude_deg,
            central_meridian_deg=self.metadata.central_meridian_deg,
            radius_m=self.metadata.reference_radius_m,
        )
        col, row = (~src.transform) @ (x, y)
        if interpolation == "nearest":
            # Rasterio's transform maps pixel corners; floor selects containing pixel.
            c, r = floor(col), floor(row)
            value = self._read(r, c)
        else:
            # Pixel centers occur at integer + 0.5 in continuous index coordinates.
            c0, r0 = floor(col - 0.5), floor(row - 0.5)
            dc, dr = col - 0.5 - c0, row - 0.5 - r0
            weights = (
                (r0, c0, (1 - dr) * (1 - dc)),
                (r0, c0 + 1, (1 - dr) * dc),
                (r0 + 1, c0, dr * (1 - dc)),
                (r0 + 1, c0 + 1, dr * dc),
            )
            # At pixel centers/edges, tiny floating-point weights must not
            # cause a *zero-contribution* nodata neighbor to invalidate a sample.
            positive = [(r, c, max(0.0, w)) for r, c, w in weights if w > 1e-12]
            total = sum(w for _, _, w in positive)
            value = sum(self._read(r, c) * w for r, c, w in positive) / total
        return TerrainSample(
            site,
            float(value),
            self.metadata.dataset_id,
            interpolation,
            row,
            col,
            x,
            y,
        )

    def _read(self, row: int, col: int) -> float:
        src = self._open_raster()
        if row < 0 or col < 0 or row >= src.height or col >= src.width:
            raise TerrainDataError("Sample outside raster coverage")
        from rasterio.windows import Window  # type: ignore[import-untyped]

        masked = src.read(1, window=Window(col, row, 1, 1), masked=True)
        if bool(masked.mask[0, 0]):
            raise TerrainDataError("No valid lunar elevation at this pixel")
        value = float(masked[0, 0])
        if not isfinite(value):
            raise TerrainDataError("Nonfinite lunar elevation")
        return value
