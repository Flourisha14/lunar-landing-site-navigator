# BE-003 + BE-005 + QA-002 — Scientific implementation notes

## Scope and frame semantics

This sprint implements **reference-sphere** geometry only. The `MOON_ME_DE440_ME421` spherical latitude/longitude conventions established by BE-002 remain authoritative. The `MOON_PA_DE440` frame is separate: **no implicit PA→ME conversion** is performed. For site-attached local ENU coordinates, Up is *radial* rather than a DEM-derived terrain normal. Position transforms include translation; free-vector transforms are rotations only. Moon-fixed vectors carry frame metadata; ENU vectors carry their reference site. Cartesian distances, heights, and components are in km, latitude/longitude in degrees.

The exact north/south pole is canonicalized to longitude 0 degrees; ENU is then based on that reference meridian, even if a different longitude was originally supplied. A tiny but nonzero distance from the pole does not trigger canonicalization. At the origin, spherical longitude and latitude are undefined and conversion raises `ValueError`. Floating-point tolerance is not terrain/mission accuracy.

## BE-003: Minimal NAIF kernel bundle

1. `naif0012.tls`: leap seconds for UTC→ET (`str2et`); leap-second updates must be monitored.
2. `de440s.bsp`: planetary/lunar ephemeris, contains Sun/Earth/Moon barycentric ephemeris chains; geometric `spkpos` queries will verify target/observer availability at selected dates.
3. `moon_pa_de440_200625.bpc`: high-accuracy lunar PA orientation.
4. `moon_de440_250416.tf`: definitions of `MOON_PA_DE440` and `MOON_ME_DE440_ME421`, and constant PA/ME relation.

Authoritative source: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/ . Lunar frame documentation: https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/Tutorials/pdf/individual_docs/23_lunar-earth_pck-fk.pdf . A text planetary constants kernel (`pck00011.tpc`) is not required for the two chosen high-accuracy lunar frames; it can be added explicitly later if needed for IAU frame or radii queries. Earth orientation PCK is *not* required for Earth-center DTE line-of-sight; terrestrial station geometry will require additional kernels.

`data/spice/kernel-manifest.json` lists exact source filenames and URLs but **does not contain verified hashes yet**. Run `python scripts/download_spice_kernels.py` from the repository root. This downloads to `data/spice/kernels/` (ignored), computes SHA-256, and creates `data/spice/kernel-lock.json`. **Review** resulting hashes and source provenance, then commit only the small lock JSON. Subsequent downloads verify the locked hashes and refuse a silently changed lock. Initial acquisition is trust-on-first-use (HTTPS), not independently authenticated; no pinned hashes were fabricated. Until lock creation and real SPICE coverage verification, BE-003's download/coverage acceptance criteria remain open.

Install SpiceyPy explicitly when ready: `backend/.venv/Scripts/python.exe -m pip install "spiceypy>=6,<9"`. Then execute `backend/.venv/Scripts/python.exe -m pytest backend/tests/integration/test_spice_kernel_bundle.py -rs` **from `backend`**, using the test path `tests/integration/test_spice_kernel_bundle.py`. This test checks local SHA-256 values and loads the kernels, evaluates Sun/Earth geometrical positions relative to Moon, and checks PA and ME frame transformations at 2026-11-14 and 2027-11-14 UTC. It is NOT a substitute for full SPK/PCK interval coverage inspection. If all data are absent it explicitly skips; if present but malformed/invalid it fails.

**Kernel coverage caveat:** broad DE440s SPK coverage is about 1849–2150, while high-accuracy lunar binary PCK coverage must be checked independently with SPICE for the desired epoch interval. The verification checks endpoints only, not continuous interval coverage; characterize exact coverage via `spkcov` and `pckcov` in a follow-on step. The `str2et` demonstration assumes the LSK has been loaded; use explicit UTC time scales in external contracts.

## BE-005: Public module

`lunar_engine.coordinates.spherical` exports `geographic_to_cartesian`, `cartesian_to_geographic`, `enu_basis`, `surface_normal`, `fixed_to_enu`, `enu_to_fixed`, `fixed_position_to_enu`, and `LocalENUVector`. ENU basis is ordered East/North/Up, forms a right-handed orthonormal triad (`E × N = U`) and is expressed in the site's lunar body-fixed axes. These functions implement sphere geometry and never convert between NAIF frames or DEM vertical datums.

## QA-002 reference provenance

`backend/tests/scientific/coordinate_golden.json` is **independent mathematical truth** for axis-aligned coordinates. Source equations: spherical Cartesian mapping `x=r cos(phi) cos(lambda)`, `y=r cos(phi) sin(lambda)`, `z=r sin(phi)` using radian arguments, from standard Euclidean geometry. At 0°, 90°, 180° and ±90°, values follow from exact unit-circle trigonometry, with radius 1737.4 km. The prime-meridian ENU vectors follow directly from East=(0,1,0), North=(0,0,1), Up=(1,0,0). The reference file is manually written and is not generated by production functions. Absolute Cartesian tolerance: 1e-9 km (1 micron) for axis-aligned cases; basis: 1e-14 dimensionless. These tolerances quantify floating-point implementation error, not measurement precision.

No independent externally sourced SPICE numerical golden references are provided at this stage. Do not mark the SPICE scientific validation requirement complete. A later QA-002 extension should record independent producer, UTC epoch, ET conversion source, frame, observer, aberration convention, NAIF kernel filenames and SHA-256 digests, units, independent expected values, and tolerances. Only then add SPICE golden tests.

## CI and data hygiene

Existing Python 3.12 CI discovers all new unit/property/scientific tests automatically. Real-kernel integration is marked `integration` and `requires_spice`; in a clean CI environment without kernels it is explicitly skipped. No rendering dependencies are introduced. Large SPICE data are excluded via `data/spice/kernels/.gitignore`; confirm root `.gitignore` also excludes binary SPICE extensions before commit.
