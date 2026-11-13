# BE-002: Lunar scientific conventions (version 1)

**Status:** adopted for the scientific engine interface, not yet a validated
navigation solution. All choices below are explicit and must accompany outputs.

## 1. Frames and lunar geography

- Default cartographic body-fixed frame: **`MOON_ME_DE440_ME421`**, using the
  NASA/JPL NAIF DE440 lunar frame kernel and matching binary orientation PCK.
  The generic alias `MOON_ME` must not be persisted as the only frame identifier:
  its target can depend on the loaded frame kernel.
- `MOON_PA_DE440` is a separate lunar **principal-axis** frame. Transformation
  requires NAIF kernels and a SPICE frame transformation; never relabel a PA
  vector as ME. `IAU_MOON` is also distinct, and is not the default.
- Frame origin: lunar center of mass; +Z nominal north polar direction, +X
  nominal prime meridian / mean Earth direction, +Y completes right-handed axes.
  These are conventions of the selected ME frame, not an exact assertion that
  the instantaneous Earth direction is +X.
- Latitude: **planetocentric**, north positive, range [-90,+90] degrees.
  Longitude: **east positive**, normalize to **[-180,+180)** degrees. +180 maps
  to -180, and signed zero maps to +0. Exact geographic pole positions have
  canonical longitude 0 because longitude is not physically unique there.
- Surface coordinates are radial relative to the lunar mass center, *not*
  geodetic normals to an ellipsoid. Cartesian vectors use **km**, right-handed
  axes, and must carry their frame. No cross-frame calculations without a
  declared transform and applicable SPICE kernels.

## 2. Reference sphere and terrain

- Reference radius: **1737.4 km** (USGS lunar map conventional sphere).
- Internal radial elevation is **km above a 1737.4 km reference sphere**,
  with explicit datum identifier `MOON_ME_REFERENCE_SPHERE_1737_4_KM`.
- This is NOT the lunar geoid, an ellipsoid, the actual physical surface, or
  an arbitrary DEM vertical datum. Every DEM must provide its source,
  projection, horizontal frame, positive-height convention, vertical reference,
  nodata value, and processing version before use. Reproject or convert when
  source metadata differ; never assume a 1737.4-km sphere matches all datasets.

## 3. Local East-North-Up (ENU)

- Local origin: a declared `LunarLocation`; axes right-handed.
- In the Moon-fixed Cartesian basis, latitude phi and longitude lambda:
  `Up=(cos(phi)cos(lambda),cos(phi)sin(lambda),sin(phi))`,
  `East=(-sin(lambda),cos(lambda),0)`,
  `North=(-sin(phi)cos(lambda),-sin(phi)sin(lambda),cos(phi))`.
- This spherical **radial Up** does not mean ellipsoid-normal Up or an actual
  terrain-slope normal. At an exact pole we select lambda=0 by convention:
  East=(0,1,0), North=(-1,0,0) at north pole and (1,0,0) at south pole.
  These directions are *conventional*, not uniquely physical at the pole.
- Azimuth: degrees clockwise from local North toward East, normalized [0,360).
  Elevation: degrees above local tangent plane, [-90,+90]. At zenith/nadir,
  azimuth is undefined: future APIs must return `None`, not a fabricated 0.

## 4. Units and time

- Spatial positions, distances, radii, and terrain elevations: **km**.
- Public geographic angles, solar/terrestrial azimuth and elevation: **degrees**.
  Trigonometric internals may use radians but must convert explicitly.
- Durations: **seconds**. Windows: UTC start inclusive / end exclusive `[a,b)`.
- API timestamp inputs: ISO-8601 UTC with explicit **`Z`**, e.g.
  `2026-11-14T12:00:00Z` or fractional seconds. No naive timestamps, local
  offsets, or ambiguous time zones. Python's standard datetime parser cannot
  represent `23:59:60`; this module rejects leap-second input pending a SPICE
  time-handling implementation.
- SPICE ephemeris time (ET): **TDB-compatible seconds past J2000**, determined
  through SPICE conversion using a pinned leap-second kernel (LSK). ET is NOT
  UTC seconds and ET-UTC is NOT a fixed constant. Record kernel identity and
  coverage. SPICE integration belongs to a later ticket.

## 5. Precision, uncertainty, and contracts

- Use IEEE-754 binary64 (`float`) for numerical calculations where appropriate.
  Reject NaN and infinities at user-data boundaries. This precision does not
  imply metre-level physical accuracy or validated uncertainty.
- Default test-only numeric comparison is `rel_tol=1e-12` and
  `abs_tol=1e-9` **in the quantity's declared unit**. These are software
  regression defaults, not scientific acceptance tolerances. QA-002 must set
  source-dependent tolerances separately for angles, geometry, times, DEMs.
- Renderer-independent contracts: `LunarLocation` (planetocentric lat/lon,
  radial elevation, frame and datum); `MoonFixedVector` (x/y/z km and frame);
  `ScientificMetadata` (frame, datum, units, conventions, optional dataset IDs).
  No backend scientific result may silently omit its reference frame or swap
  vertical datums. JSON adapters must serialize enums to their string values;
  serialization and mathematical transformations are future ticket scope.
- Determinism means same inputs, pinned kernels/datasets and numerical
  environment yield reproducible outputs within *declared numerical tolerance*;
  bitwise identity across all platforms is not promised.

## 6. Tests and independent verification

- `unit`: local contracts and invariants.
- `property`: Hypothesis-generated invariants, reproducible test profile.
- `scientific`: comparisons with independent published or independently
  derived reference results (none supplied in QA-001).
- `integration`: external assets/dependencies. `requires_spice` and
  `requires_dem` tests skip with clear reasons if paths aren't configured.
- QA-002 should pin NASA/NAIF SPK, LSK, lunar PCK and FK kernel versions,
  their SHA-256 hashes and valid epochs; DEM provenance and raster metadata;
  and published numerical checks on frame transformations and look angles.
  A functioning import or a self-consistency test alone is NOT validation.

## References

- NAIF, *Lunar Frames Kernel* tutorial:
  https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/Tutorials/pdf/individual_docs/23_lunar-earth_pck-fk.pdf
- NAIF DE440 FK (verify selected file and checksums at integration time):
  https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/
- USGS I-2769, adopted 1737.4 km spherical datum, ME frame, east longitude:
  https://pubs.usgs.gov/publication/i2769
