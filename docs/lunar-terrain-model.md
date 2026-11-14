# Lunar terrain model — Sprint 4

## Provenance and selection

NASA GSFC Planetary Geodesy Data Archive (PGDA), **A New View of the Lunar South Pole from LOLA**, product 90: `LDEM_80S_80MPP_ADJ.TIF` (approximately 181 MB original, **80 metres/pixel**, coverage nominally 80°S–90°S). The page describes this as a COG in south-polar stereographic X/Y metres, lunar `MOON_ME` DE421 frame, with LDEM height Z values in metres. Source: https://pgda.gsfc.nasa.gov/products/90 . Direct source: https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF . Data DOI `10.60903/gsfcpgda-lola-spole`; cite Barker et al. (2023), *Planetary Science Journal* 4, 183, DOI `10.3847/PSJ/acf3e1`.

**Critical:** publisher web prose does not alone establish GeoTIFF embedded CRS and vertical datum. The acquisition script records the actual raster CRS, transform, nodata, and SHA-256. Check the source's exact elevation/reference-sphere convention before enabling terrain-aware claims. The software currently requires radial height in metres above the **1737400 m** lunar reference sphere and rejects unexpected map projection/radius; conversion from other vertical datums must be explicit. It additionally **refuses DEM opening until `TerrainMetadata(datum_confirmed=True)` is explicitly passed**, which must only happen after checking the original source documentation. The real-DEM integration test requires `LUNAR_DEM_DATUM_CONFIRMED=1` after that review. The DEM/source `MOON_ME` (DE421) is not assumed interchangeable with `MOON_PA` or `IAU_MOON`. Existing `MOON_ME_DE440_ME421` follows the ME421 realization but ephemeris/terrain registration accuracy requires separate assessment.

## Acquire, verify, and subset (from repository root)

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\backend\.venv\Scripts\python.exe .\scripts\acquire_lunar_dem.py --create-subset
Get-Content .\data\dem\terrain-provenance.json
Get-Content .\data\dem\terrain-subset-provenance.json
```

This downloads the original COG then makes a **single 80 km × 80 km** pixel-window, *without reprojection or resampling*, centered at latitude **−89.5°**, longitude **45° east** for the demonstration. It is large enough for up to ~30 km radial rays from this location, but not necessarily for every possible location. Both original and subset are in `data/dem/` and ignored by Git. The subset checksum depends on the resulting GeoTIFF bytes and is computed locally (never fabricated).

## Sampling and geometry

`LunarDEM` opens a projected single-band GeoTIFF. At each planetocentric east-positive latitude/longitude, transform to spherical south-polar stereographic:

- `rho = 2R tan(pi/4 + latitude/2)`
- `x = rho sin(longitude - central_meridian)`
- `y = rho cos(longitude - central_meridian)`

`R = 1,737,400 m`; source CRS and projection parameters must match. Use the raster affine transform for coordinate-to-pixel mapping. Nearest sampling chooses the containing pixel; bilinear interpolates four **pixel-center** values, failing rather than extrapolating if a required pixel is nodata or outside coverage. A zero-weight nodata neighbor is ignored. Height is converted from metres to kilometres only when creating a `LunarLocation`. Cartesian conversions use BE-005 spherical radial coordinates, not Earth geodetic algorithms.

At exact south pole, longitude is canonicalized to 0 by BE-002; this makes azimuth conventions repeatable but absolute compass azimuth at the pole requires a selected meridian.

## Curvature-aware horizon

Observer radius `r_o = R + (h_observer_terrain + observer_height)/1000` km. A terrain point at spherical surface arc length `d` (km) and radial height `h_target` (m) has radius `r_t = R + h_target/1000`; `theta=d/R`. Relative to the observer's local radial horizontal:

- horizontal = `r_t sin(theta)`
- vertical = `r_t cos(theta) - r_o`
- target elevation = `atan2(vertical, horizontal)`

The ray samples terrain at fixed surface arc-length steps along an initial local ENU azimuth, follows the great circle, and reports the maximum point elevation. The **effective spherical geometric horizon** is `max(0°, highest sampled terrain angle)`. A complete result requires data at every requested sample. If any required sample is missing, `complete=False` and `horizon_elevation_deg=None`; the maximum of sampled angles is diagnostic only, **not evidence of visibility**. Horizon profiles are collections of independently evaluated azimuth rays.

Synthetic independent reference: for equal observer/target radii and observer height 0, target angle is `−d/(2R)` radians exactly for arc distance `d` (on the near hemisphere). Tests also check a known 200 m ridge at 1 km and monotonic response to observer height.

### Practical limits

The ray search truncates at the configured maximum range and cannot certify unobstructed terrain beyond it. The DEM is 80 m nominal pixels, so a 160 m sampling step may miss narrow obstructions; use a smaller step and azimuth interval for higher fidelity. Coordinate and vertical datum uncertainty, DEM interpolated voids, finite solar/Earth discs, antenna pointing, rover height, SPICE aberration choices, and independent reference profiles remain outstanding. Results are **geometry estimates**, not mission-certified illumination/communication forecasts.

### Validation categories

- **Analytical:** projection origin/cardinals, exact flat-sphere depression angle, synthetic ridge profile.
- **Internal:** roundtrip projection, deterministic results, increasing observer-height property.
- **Raster integration:** synthetic 3 × 3 lunar stereographic GeoTIFF with known heights and nodata.
- **Real-DEM integration:** gated by `LUNAR_DEM_FILE`; must pass locally before BE-008/009/010 or QA-004 are marked fully complete.
- **Independent external terrain-horizon product:** **pending**.

Local unit tolerances: spherical projection cardinals ±1e−7 m, lat/lon roundtrip ±1e−10°, analytical depression angle ±1e−10°, synthetic ridge angle ±1e−8°. Real-DEM height agreement is **not** established by these tolerances.

Lunar DEM Vertical Datum and Reference-Frame Evidence

Record the following information:
| Property | Value |
|---|---|
| Product | `LDEM_80S_80MPP_ADJ.TIF` |
| Source | NASA GSFC Planetary Geodesy Data Archive |
| Instrument | LRO LOLA |
| Projection | South polar stereographic |
| Reference sphere | 1,737,400 m |
| Height interpretation | Metres relative to reference sphere |
| Source frame | DE421-associated MOON_ME |
| Astronomy frame | `MOON_ME_DE440_ME421` |
| Frame alignment uncertainty | Not independently quantified |
| Source DOI | `10.60903/gsfcpgda-lola-spole` |
| Publication DOI | `10.3847/PSJ/acf3e1` |


Use the NASA product documentation and USGS lunar data standards as references.