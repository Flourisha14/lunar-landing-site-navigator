# Point-source terrain visibility

## Scientific scope

`lunar_engine.analysis.visibility.evaluate_terrain_visibility` combines **existing**
BUG-001 epoch-dependent DE440→DE421 SPICE geometry with BE-010 terrain-horizon
rays. It evaluates the centers of the **Sun** and **Earth** at the same lunar
location and UTC epoch, using a single astronomical geometry call.

**This is a geometric, point-center calculation**, not finite-disc sunlight,
photometric irradiance, radio propagation, or guaranteed communications.
The existing SPICE provider uses aberration `NONE` (geometric simultaneous
positions), not light-time/stellar-aberration apparent centers. “Earth visibility”
means visibility of Earth's modeled geometric center in this release.

## Coordinate and radial-height contract

- DEM frame: `MOON_ME_DE421`, NASA LOLA DE421-associated Mean Earth frame.
- Astronomical ephemerides: existing DE440 engine, explicitly rotated into
  `MOON_ME_DE421` using the verified BUG-001 frame-transform adapter.
- The **observer radial height** passed to the astronomical direction calculation
  is `(sampled_dem_elevation_m + observer_height_m)/1000`. BE-010 uses the same
  DEM surface height and observer height for the horizon ray.
- The observer's horizontal plane is the **radial** tangent plane of the
  1,737.4 km reference sphere, not the measured local slope normal.
- Input timestamps must use ISO UTC `Z` format; kernels must cover the epoch.
- Only explicit Moon-centered DE421 astronomy and terrain results are combined.

## Three-state decision

For a celestial elevation `E` and the sampled maximum terrain obstruction
angle `H` along its azimuth:

- **VISIBLE** if `E > H`.
- **OBSTRUCTED** if `E <= H`, including exact tangency.
- **UNKNOWN** if the requested DEM ray is incomplete or the celestial
  azimuth is mathematically undefined (exact zenith/nadir).

A *negative* celestial elevation **does not automatically imply obstruction**:
terrain may fall below the observer's radial tangent plane, yielding a negative
local terrain horizon. A missing DEM sample must never imply a clear sightline.
`BodyVisibility.visible` is a tri-state `bool | None` and returns `None` for
UNKNOWN; callers should prefer the explicit `VisibilityStatus` enum.

The result retains timestamp, DEM dataset identifier, kernel manifest identifier,
DE421 frame, observer position/height, search distance, sampling step,
interpolation, per-target azimuth/elevation/horizon, angular clearance,
controlling terrain metadata, and explicit model fidelity.

## API example

```python
from dataclasses import replace
from pathlib import Path
from lunar_engine.terrain.dem import DEFAULT_LOLA_METADATA, LunarDEM
from lunar_engine.analysis.visibility import evaluate_terrain_visibility

repo = Path("...")  # repository root containing both verified SPICE lock files
raster = Path("...")  # verified LOLA regional raster (not committed to Git)
metadata = replace(DEFAULT_LOLA_METADATA, datum_confirmed=True)
with LunarDEM(raster, metadata=metadata) as dem:
    result = evaluate_terrain_visibility(
        dem, -89.5, 45.0, "2027-11-15T12:00:00Z",
        observer_height_m=2.0, max_distance_km=2.0,
        step_m=80.0, interpolation="bilinear", repository_root=repo,
    )
    print(result.sun.status, result.sun.clearance_deg)
    print(result.earth.status, result.earth.clearance_deg)
```

## Reproducibility

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_terrain_visibility.py -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
```

For the local real LOLA + real SPICE integration test, set:

```powershell
$env:LUNAR_DEM_FILE = "<absolute_path_to_verified_80km_subset>"
$env:LUNAR_DEM_DATUM_CONFIRMED = "1"
$env:LUNAR_REQUIRE_REAL_VISIBILITY = "1"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_real_terrain_visibility.py -v -rs
```

The test skips when external assets are absent unless
`LUNAR_REQUIRE_REAL_VISIBILITY=1`, in which case missing prerequisites fail.
GitHub CI currently downloads SPICE kernels but does not install the large
NASA LOLA GeoTIFF; a green CI run alone does not prove real-DEM execution.

## Validation and limitations

The analytical suite uses synthetic DEM heights and controlled celestial
angles to test visibility states, strict equality, observer height, negative
celestial elevation, missing coverage, epoch/coordinate validation, frame
consistency, and reproducibility. These fixtures do not replace actual NASA
data. The real integration uses the independently downloaded, locally stored
NASA LOLA dataset and checksum-verified SPICE kernel configurations.

The terrain horizon is a **sampled maximum over a finite radius**, not the
continuous/global lunar horizon. DEM 80 m native resolution, interpolation,
vertical datum/registration, sampling step, and search radius affect the answer.
The BE-010 demonstration showed several degrees of nearest/bilinear sensitivity
at some azimuths; this is **not a calibrated error bound**.
No absolute validation against an independently surveyed lunar horizon is claimed.
No refraction, finite solar/terrestrial angular diameter, partial discs,
communications link budget, relay access, antenna mask, lunar rotation dynamics
beyond the underlying SPICE frames, or propagation blockage by non-terrain
structures is modeled.

## Real NASA LOLA Search-Distance Sensitivity

Observer:
- Latitude: -89.5 degrees
- Longitude: 45.0 degrees east
- Timestamp: 2027-11-15T12:00:00Z
- Observer height: 2 m

Scientific configuration:
- Terrain: NASA LOLA 80 m regional subset
- Reference frame: MOON_ME_DE421
- SPICE aberration correction: NONE
- Interpolation: bilinear
- Sampling interval: 80 m

### Sun

| Search distance | Terrain horizon | Clearance | Status |
|---|---:|---:|---|
| 2 km | -4.143150° | +5.833633° | Visible |
| 5 km | -1.815547° | +3.506031° | Visible |
| 10 km | -1.082797° | +2.773281° | Visible |

### Earth

| Search distance | Terrain horizon | Clearance | Status |
|---|---:|---:|---|
| 2 km | -6.408866° | +11.874685° | Visible |
| 5 km | -3.057001° | +8.522820° | Visible |
| 10 km | -1.122442° | +6.588261° | Visible |

### Interpretation

Both geometric celestial centers remain visible above the
sampled terrain horizon for all three tested search distances.

Increasing the search distance raises the maximum sampled
terrain obstruction and reduces celestial clearance.

The controlling terrain features for the 10 km search occur
approximately 7.60 km from the observer for the Sun and
9.44 km for Earth.

Although these controlling features lie within the search
boundary, this does not establish convergence beyond 10 km.

These are finite-distance geometric point-center visibility
results, not predictions of full solar-disc illumination or
guaranteed direct-to-Earth communication availability.

Absolute terrain-horizon accuracy has not been independently
certified.
