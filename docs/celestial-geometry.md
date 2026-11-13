# Lunar Sun and Earth geometry (Sprint 3)

## Model scope

The engine computes **geometric** positions of the **centers** of the Sun and Earth relative to the **Moon center**, transforms those vectors into a selected SPICE Moon-fixed frame, and subtracts the observer's spherical Moon-fixed site position. The resulting line of sight is rotated into local ENU.

The SPICE call is `spkpos(target, ET, frame, 'NONE', 'MOON')`: `NONE` means **no light-time or stellar-aberration correction**. The engine therefore does *not* claim apparent optical pointing accuracy. It does not account for the angular extent of the Sun or Earth, terrain obstruction, lunar DEM elevation, Earth radio antennas, occultation by local relief, relay satellites, link budget, pointing constraints, or atmosphere.

`geometric_visible` is `elevation_deg > 0` relative to the spherical radial local tangent plane. At exactly 0 degrees the point-source center is considered **not visible**. Apparent rise/set and partial solar-disk illumination differ from this definition.

## Reference frames, datum and units

- Default frame `MOON_ME_DE440_ME421`; optional `MOON_PA_DE440` and `IAU_MOON` are *distinct* frames. SPICE performs the inertial-to-body-fixed transformation; callers must never relabel vectors between frames.
- Planetocentric latitude (north positive), east-positive longitude normalized to `[-180, 180)` and canonical zero longitude at exact poles, according to BE-002.
- Reference sphere radius `1737.4 km`; heights are radial **kilometres above that sphere** (not a terrain DEM datum).
- SPICE position vectors and topocentric ranges in kilometres; azimuth and elevation in degrees; ET is seconds past J2000 on the SPICE time scale.
- Azimuth clockwise from north through east `[0, 360)`; `None` at exact or numerically indistinguishable zenith/nadir (horizontal norm <= 1e-14 times range). Elevation `[-90, +90]`.
- Local ENU vector components are *unitless unit vectors*, the target position is in km. Data contracts keep the Moon-fixed frame, UTC epoch, ET and locked kernel manifest ID.

## Kernels and temporal accuracy

This sprint reuses BE-003's `data/spice/kernel-lock.json` and its checksum-verified binaries (`naif0012.tls`, `de440s.bsp`, `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`). Missing or corrupt kernels cause the computation to fail; no fallback ephemeris values are synthesized. SPICE kernels are loaded through a scoped provider and unloaded on exit. CSPICE has a **process-global kernel pool**: avoid concurrent independent bundle contexts. Timestamp parsing requires explicit UTC `Z`, and ET conversion uses the loaded leap-second kernel. Leap seconds require special SPICE handling; the simple input parser does not accept a `:60` timestamp.

`EphemerisProvider.check_epochs()` probes requested epochs for available Sun/Earth positions in a selected frame. It **does not establish uninterrupted coverage** over an interval. Strict coverage analysis using SPK/PCK coverage windows is future work.

## Python usage

From `backend/` in the existing Python 3.12 virtual environment:

```python
from lunar_engine.astronomy import analyze_celestial_geometry

result = analyze_celestial_geometry(-89.5, 45.0, "2027-11-15T12:00:00Z")
print(result.sun.azimuth_deg, result.sun.elevation_deg, result.sun.geometric_visible)
print(result.earth.azimuth_deg, result.earth.elevation_deg, result.earth.geometric_visible)
print(result.kernel_manifest_id, result.frame, result.et_seconds)
```

For multiple timestamps, keep the kernel pool loaded with `EphemerisProvider` and call `provider.position('SUN', iso_utc)` or `provider.position('EARTH', iso_utc)` directly. One-shot convenience API prioritizes correctness and a simple public interface rather than repeated-call performance.

## Validation strategy and numerical limitations

Tests cover synthetic independent ENU cardinal directions, polar geometry, exact horizon rules, unit-vector norms and frame mismatch. Real-kernel tests check SPICE UTC/ET consistency, frame-rotation norm invariance and deterministic results. **Those properties do not independently validate the absolute NASA ephemeris positions**. The fixture `tests/scientific/ephemeris_reference_pending.json` explicitly records that a sourced, independent numerical reference remains unavailable; the corresponding scientific test is intentionally skipped.

Unit-case angle tolerances: `1e-10 degree` near the analytic 1:100 horizon ray; geometric axes `1e-12 degree`; vector norms `1e-12`; ET/UTC roundtrip `2 microseconds` (microsecond formatting plus floating-point ET). These are algorithmic tolerances, **not** physical errors, DEM accuracy or spacecraft-grade error budgets. Full ephemeris accuracy depends on the locked kernels and model assumptions.

## Follow-up science tasks

- Obtain independently published SPICE/Horizons values specifying epoch, observer, target, frame, aberration, kernel set, units, source and numerical tolerance; add actual golden reference tests.
- Audit continuous SPK/PCK coverage and leap-second kernel freshness.
- Model finite solar/terrestrial disks and apparent (light-time-corrected) topocentric directions when scientifically appropriate.
- Use DEM-derived horizon profiles before labeling output as terrain-aware illumination or direct-to-Earth communications windows.
