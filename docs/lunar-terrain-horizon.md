# Lunar terrain horizon

## Model and assumptions

The observer and all terrain samples are expressed in the **native** `MOON_ME_DE421`
frame, verified by BE-009 metadata and BUG-001. No unrecorded DE421↔DE440
relabeling is performed. Astronomical Sun/Earth directions must be transformed
into the same frame using the epoch-aware BUG-001 adapter **before** any
comparison. BE-011 and BE-012 are deliberately outside this sprint.

The reference sphere has radius **1737.4 km**, and DEM elevations are treated as
**radial metres above that sphere**. The implementation assumes that DEM elevations represent radial metres relative to the documented 1,737.4 km lunar reference sphere. Setting datum_confirmed=True explicitly acknowledges this interpretation but does not independently validate the DEM's vertical datum or absolute registration.
A topographic or ellipsoidal surface normal is **not** substituted for the radial
reference normal. This is a geometrical visibility model, not photometric
illumination or a spacecraft navigation model.

For a requested azimuth, the algorithm follows the spherical great circle
specified by the observer's **local radial ENU basis** (bearing clockwise from
north). Surface points are sampled at reference-sphere arc distances `s` up to
`max_distance_km`, using intervals no larger than `step_m`. Every target is
represented as a 3-D radial Moon-fixed position. A line-of-sight vector is
computed by subtracting the observer position (DEM elevation plus observer
height), and its signed elevation relative to the observer's radial tangent
plane is calculated by `atan2(up_component, horizontal_magnitude)`. The
controlling terrain is the maximum of those signed angles. Negative horizons
are meaningful and are *not* clipped to zero.

For a constant-radius sphere, the independently derived reference expression is
`angle = -(s/R)/2` radians (for observer height zero, provided s<R*pi).
For nonzero radial heights, an analytical cross-check is:

```text
R_o = R + (h_observer_terrain + h_observer_above_terrain)/1000
R_t = R + h_target/1000
θ = s/R
angle = atan2(R_t*cos(θ) - R_o, R_t*sin(θ))
```

This spherical method accounts for lunar curvature and radial terrain height.
**DEM sampling is discrete:** narrow ridges between sample locations may be
missed. Bilinear interpolation smooths extreme heights; finer step sizes do
not recover spatial frequencies absent from an 80-m raster. Search distance
is finite: the horizon is only established for the requested radius, not the
entire lunar hemisphere. No atmospheric refraction is applied (vacuum model).

## Coverage and returned scientific metadata

A `HorizonRay` contains the observer position and sampled terrain elevation,
observer height, DEM dataset identifier, source frame, azimuth, signed maximum
angle, distance/geographic position of the controlling feature, sampling step,
search limit, interpolation method, sample counts, reference radius and coverage
status. A missing/nodata raster sample yields `coverage="incomplete"` and
`horizon_elevation_deg=None` with first missing distance; an incomplete ray
**must not** be interpreted as clear. The observer must itself be within DEM
coverage. Invalid frames or mismatched sample metadata raise errors.

A profile consists of deterministic azimuth rays in `[0,360)`, excluding a
duplicated 360-degree endpoint. Large configurations are rejected to cap
resource consumption.

## Reproduction

From the repository root, create a feature branch, apply the bundle, and run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit/test_terrain_horizon.py -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest --cov=lunar_engine --cov-report=term-missing -v -rs
```

To perform mandatory **real NASA LOLA** data integration locally, set the
absolute path to either the verified source DEM or the verified regional subset
and acknowledge the product's radial-datum assumption:

```powershell
$env:LUNAR_DEM_FILE = "D:\\...\\your_verified_LOLA_subset.tif"
$env:LUNAR_DEM_DATUM_CONFIRMED = "1"
$env:LUNAR_REQUIRE_REAL_DEM = "1"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_real_lunar_horizon.py -v -rs
```

The real integration test expects the documented source point elevation
`-405.3225402832031 m` at `(latitude=-89.5°, longitude=45°E)` under nearest
sampling. It checks deterministic repeatability, reference-frame consistency, dataset provenance, controlling-point geometric consistency, and unchanged raster file size and modification time. Independent analytical validation is provided by the separate synthetic and closed-form reference tests. This is **not** independent external benchmarking of a measured
terrain-horizon profile. The DEM's absolute registration/vertical datum and
interpolation/finite-radius uncertainties remain relevant.

## Validation categories

- **Analytical:** closed-form spherical curvature, law-of-cosines ridge case,
  height effects, poles, wrapping, missing-data and resolution sensitivity.
- **Synthetic numerical:** controlled elevation sources (testing only).
- **Real data:** NASA LOLA GeoTIFF, if locally available and explicitly enabled.
- **Independent external terrain horizon:** not yet established. Do **not** claim
  mission-grade validation based solely on these tests.

The large LOLA raster is never committed to Git. CI can run analytical tests
without the original NASA DEM; the real-data integration test skips unless its
required inputs are provided. Do not mark QA-004 fully verified until a real
DEM run has passed in the project's actual environment.

## Real LOLA DEM Numerical Sensitivity — QA-004

Dataset: NASA LRO LOLA, LDEM_80S_80MPP_ADJ regional subset.

Observer:
- Latitude: -89.5 degrees
- Longitude: 45.0 degrees east
- Height above sampled terrain: 2 m
- Terrain reference frame: MOON_ME_DE421

### Interpolation sensitivity

At azimuth 180 degrees, using a 2 km search distance:

| Sampling | Interpolation | Horizon elevation |
|---|---|---|
| 160 m | Nearest | 16.428639 degrees |
| 80 m | Nearest | 16.776116 degrees |
| 160 m | Bilinear | 12.335393 degrees |
| 40 m | Bilinear | 12.375945 degrees |

The results demonstrate sensitivity to DEM interpolation.

Bilinear interpolation produces a continuous interpolated surface
but may smooth local terrain extrema.

Subpixel sampling does not increase the native spatial resolution
of the underlying DEM.

### Observer-height sensitivity

At azimuth 180 degrees, using bilinear interpolation
and an 80 m sampling interval:

| Observer height | Horizon elevation |
|---|---|
| 2 m | 12.375945 degrees |
| 5 m | 12.083899 degrees |
| 10 m | 11.702862 degrees |

The maximum terrain obstruction decreases as observer height increases.

### Search-distance sensitivity

At azimuth 90 degrees, using bilinear interpolation
and an 80 m sampling interval:

| Search distance | Horizon elevation |
|---|---|
| 2 km | 1.255133 degrees |
| 5 km | 2.203018 degrees |
| 10 km | 2.203018 degrees |

Increasing the search distance revealed a more obstructive
terrain feature approximately 3.68 km from the observer.

### Interpretation

These results demonstrate analytical and real-data numerical
consistency under the tested configurations.

They do not establish mission-certified horizon accuracy.

The calculated horizon remains dependent on:

- DEM spatial resolution and registration accuracy.
- Elevation measurement uncertainty.
- Interpolation method.
- Sampling interval.
- Search distance.
- Observer location and height.
- Reference-frame assumptions.
- Completeness of DEM coverage.

The maximum sampled obstruction angle is not necessarily the
global maximum obstruction angle along a continuous sightline.

Additional independent validation against authoritative reference
horizon profiles is required before assigning absolute
scientific accuracy bounds.

The real NASA LOLA integration test passed locally using the verified 80 km regional subset. GitHub Actions does not currently provision this raster; therefore, a green CI result must not be interpreted as successful execution of the real-data integration test. Local real-DEM validation and CI validation are recorded separately.
