"""Download and inspect NASA GSFC LOLA south-polar COG; run from repo root.

No bundled elevation files. Does NOT infer or silently alter vertical datum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import urllib.request
from pathlib import Path
from typing import Any

SOURCE = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF"
FILENAME = "LDEM_80S_80MPP_ADJ.TIF"
DATASET = "GSFC_PGDA_LOLA_SOUTH_POLE_LDEM_80S_80MPP_ADJ"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def normalize_json_metadata(value: Any) -> Any:
    """Convert metadata into strictly JSON-compatible values."""

    if isinstance(value, dict):
        return {key: normalize_json_metadata(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [normalize_json_metadata(item) for item in value]

    if isinstance(value, float) and not math.isfinite(value):
        return None

    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", default="data/dem", help="Directory ignored by Git"
    )
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument(
        "--create-subset",
        action="store_true",
        help="Create an 80 km regional GeoTIFF around -89.5 N, 45 E",
    )
    parser.add_argument("--timeout", type=int, default=90)
    arguments = parser.parse_args()
    directory = Path(arguments.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / FILENAME
    if not destination.is_file():
        if arguments.inspect_only:
            raise FileNotFoundError(destination)
        temporary = destination.with_suffix(".TIF.part")
        print("Downloading original NASA GSFC LOLA DEM (~181 MB):", SOURCE)
        try:
            with (
                urllib.request.urlopen(SOURCE, timeout=arguments.timeout) as response,
                temporary.open("wb") as output,
            ):
                while block := response.read(1024 * 1024):
                    output.write(block)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    digest = checksum(destination)
    import rasterio

    with rasterio.open(destination) as source:
        if source.count != 1:
            raise ValueError("Expected a single-band lunar DEM")

        if source.crs is None:
            raise ValueError("Lunar DEM has no coordinate reference system")

        if source.width != 7600 or source.height != 7600:
            raise ValueError("Unexpected NASA LOLA raster dimensions")

        if abs(source.transform.a - 80.0) > 1e-6:
            raise ValueError("Unexpected DEM horizontal pixel spacing")

        if abs(source.transform.e + 80.0) > 1e-6:
            raise ValueError("Unexpected DEM vertical pixel spacing")

        crs = source.crs.to_dict()

        if crs.get("proj") != "stere":
            raise ValueError("Expected a stereographic projection")

        if abs(float(crs.get("lat_0", 0)) + 90.0) > 1e-7:
            raise ValueError("Unexpected latitude of projection origin")

        if abs(float(crs.get("lon_0", 999))) > 1e-7:
            raise ValueError("Unexpected central meridian")

        if abs(float(crs.get("R", 0)) - 1737400.0) > 0.1:
            raise ValueError("Unexpected lunar reference radius")

        metadata = {
            "dataset_id": DATASET,
            "product_filename": FILENAME,
            "provider": "NASA GSFC Planetary Geodesy Data Archive, LRO LOLA",
            "source_url": SOURCE,
            "product_page": "https://pgda.gsfc.nasa.gov/products/90",
            "publication": "Barker et al. 2023, Planetary Science Journal 4, 183",
            "doi": "10.60903/gsfcpgda-lola-spole",
            "publication_doi": "10.3847/PSJ/acf3e1",
            "local_path": destination.as_posix(),
            "bytes": destination.stat().st_size,
            "sha256": digest,
            "width_px": source.width,
            "height_px": source.height,
            "bands": source.count,
            "dtype": source.dtypes[0],
            "nodata": (
                None
                if source.nodata is not None and not math.isfinite(source.nodata)
                else source.nodata
            ),
            "nodata_representation": (
                "NaN"
                if source.nodata is not None and math.isnan(source.nodata)
                else None
            ),
            "pixel_transform": list(source.transform)[:6],
            "pixel_size_x_m": abs(source.transform.a),
            "pixel_size_y_m": abs(source.transform.e),
            "bounds_projected_m": list(source.bounds),
            "raster_crs_wkt": source.crs.to_wkt() if source.crs else None,
            "raster_crs_proj": source.crs.to_dict() if source.crs else None,
            "raster_units": source.units[0],
            "source_frame": "MOON_ME JPL DE421 (PGDA description)",
            "horizontal_reference": {
                "frame_family": "MOON_ME",
                "source_realization": "DE421-associated",
                "latitude_type": "planetocentric",
                "longitude_direction": "east-positive",
                "projection": "south_polar_stereographic",
                "reference_radius_m": 1737400.0,
            },
            "vertical_reference": {
                "unit": "m",
                "interpretation": "pending_explicit_source_confirmation",
                "datum_confirmed": False,
            },
            "latitude_type": "planetocentric (confirm against delivered raster and source documentation)",
            "longitude_convention": "east-positive (confirm against delivered raster and source documentation)",
            "vertical_interpretation": "surface height Z in metres; vertical datum requires metadata confirmation",
            "validated_for_sampling": False,
            "validation_note": "Inspect CRS, reference radius and height datum before treating values as radial elevation above 1737.4 km.",
            "frame_alignment_note": (
                "Source is DE421-associated MOON_ME; astronomy engine uses "
                "MOON_ME_DE440_ME421. Cross-realization alignment has "
                "not been independently quantified."
            ),
        }
    metadata = normalize_json_metadata(metadata)

    manifest = directory / "terrain-provenance.json"

    manifest.write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print("DEM acquired and opened successfully:", destination)
    print("SHA256:", digest)
    print("Dimensions:", metadata["width_px"], "x", metadata["height_px"])
    print("Pixel spacing (m):", metadata["pixel_size_x_m"], metadata["pixel_size_y_m"])
    print("CRS:", metadata["raster_crs_proj"])
    print("Audit:", manifest)
    if arguments.create_subset:
        from lunar_engine.terrain.dem import south_polar_stereographic_xy
        from rasterio.windows import from_bounds
        from rasterio.windows import transform as window_transform

        center_x, center_y = south_polar_stereographic_xy(-89.5, 45.0)
        half = 40_000  # 80 km square, enough for <=30 km rays from selected site.
        subset_path = directory / "LDEM_80S_80MPP_ADJ_southpole_demo_80km.TIF"
        with rasterio.open(destination) as src:
            win = from_bounds(
                center_x - half,
                center_y - half,
                center_x + half,
                center_y + half,
                transform=src.transform,
            )
            win = win.round_offsets().round_lengths()
            if (
                win.col_off < 0
                or win.row_off < 0
                or win.col_off + win.width > src.width
                or win.row_off + win.height > src.height
            ):
                raise ValueError(
                    "Regional subset exceeds the authoritative source raster"
                )
            profile = src.profile.copy()
            profile.update(
                width=int(win.width),
                height=int(win.height),
                transform=window_transform(win, src.transform),
                compress="deflate",
            )
            with rasterio.open(subset_path, "w", **profile) as out:
                out.write(src.read(window=win))
        subset_metadata = {
            "dataset_id": DATASET + "_demo_80km",
            "derived_from": SOURCE,
            "parent_sha256": digest,
            "subset_path": subset_path.as_posix(),
            "subset_sha256": checksum(subset_path),
            "centre_planetocentric_lat_deg": -89.5,
            "centre_east_positive_lon_deg": 45.0,
            "width_m": 80_000,
            "height_m": 80_000,
            "processing": "pixel-window clip of original projected GeoTIFF; no reprojection or resampling",
            "datum_validation_status": "PENDING_SOURCE_METADATA_CONFIRMATION",
        }
        subset_metadata = normalize_json_metadata(subset_metadata)

        (directory / "terrain-subset-provenance.json").write_text(
            json.dumps(
                subset_metadata,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print("Regional subset:", subset_path)
        print("Subset SHA256:", subset_metadata["subset_sha256"])
    print(
        "IMPORTANT: review vertical datum and CRS metadata; acquisition alone does not establish scientifically correct sampling."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
