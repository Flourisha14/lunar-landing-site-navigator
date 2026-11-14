# BUG-001 — Explicit DE421 ↔ DE440 lunar frame alignment

## Source evidence

- Terrain source: NASA GSFC PGDA `LDEM_80S_80MPP_ADJ.TIF`; `MOON_ME` associated with DE421. Source GeoTIFF's polar stereographic CRS is not itself a NAIF orientation kernel.
- Astronomy: `MOON_ME_DE440_ME421` (NAIF 31009), defined relative to `MOON_PA_DE440` (31008).
- Historical frame: `MOON_ME_DE421` (NAIF 31007), defined relative to `MOON_PA_DE421` (31006).
- Both frames' NAIF center is 301 (Moon), as verified during adapter initialization. For lunar-center positions and free vectors, SPICE `pxform` supplies the epoch-dependent orientation rotation. No origin translation is required **only for these two frames**. Generic `MOON_ME` aliases are intentionally not used.
- Existing frame aliases in the 2008 and 2025 FK overlap; loading the old frame kernel first, and the latest second, preserves the latest generic aliases, but all computation uses explicit frame names.

## Kernel dependencies

Existing pinned kernels: `naif0012.tls`, `de440s.bsp`, `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`.

New pinned-on-acquisition kernels: `moon_pa_de421_1900-2050.bpc` and `moon_080317.tf`, fetched directly from NAIF. The first is historical lunar PA orientation; the latter defines `MOON_ME_DE421`. Download by `python scripts/acquire_de421_frame_kernels.py`, review and commit `data/spice/de421-frame-lock.json`. Both binaries stay ignored in `data/spice/kernels/`.

Kernel existence is not temporal coverage: test the requested epochs using actual `pxform` and, before broad mission-window operations, inspect binary PCK coverage with `pckcov` for each frame class ID.

## API and usage

```python
from pathlib import Path
from lunar_engine.coordinates.frame_transform import LunarFrameTransformer
from lunar_engine.core.conventions import LunarFrame, MoonFixedVector

root = Path(r"D:\my_files\nasa_space_apps\lunar-landing-site-navigator")
with LunarFrameTransformer(root) as frames:
    result = frames.transform(
        MoonFixedVector(1.0, 0.0, 0.0, LunarFrame.ME_DE421),
        LunarFrame.ME,
        "2027-11-15T12:00:00Z",
        kind="direction",
    )
    print(result.vector, result.kernel_bundle_ids)
```

For terrain/astronomy integration, `analyze_geometry_in_dem_frame()` computes Sun/Earth celestial directions in `MOON_ME_DE421`, suitable for comparison with a DEM observer **only after the DEM's vertical datum is independently confirmed**. This routine still uses a spherical horizon and makes no claim of terrain-aware visibility.

## Independent evidence and numerical tolerances

NAIF `moon_de440_250416.tf` states maximum rotation between `MOON_ME_DE421` and `MOON_ME_DE440_ME421` over ~1 million samples during 2000–2040 of 3.0709840342771×10^-7 rad (surface displacement ~0.534 m). This is a documented source *bound*, not an independent ephemeris sample. Test numerics: orthogonality and determinant within 2×10^-12, roundtrip Cartesian components within 10^-9 km for tested points, norm preservation within 10^-9 km. These are floating-point numerical thresholds, not physical accuracy.

The ~0.534 m historical published bound is a sampled interval observation, **not a guaranteed maximum for every future date or an accuracy certification**. Unknown DEM registration, datum, and LOLA vertical accuracy add uncertainty not captured by these tests.

References:
- https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_de440_250416.tf
- https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_080317.tf
- https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de421_1900-2050.bpc
