# Lunasolum — DEM-scoped visibility-based landing-site screening

## Scope

This is a deterministic *candidate screening* and recommendation function for the
loaded NASA LOLA south-polar DEM. It is **not** a landing safety assessment or
an exhaustive survey of the Moon. The frontend can plot the returned
`recommendations` coordinates and show the per-candidate `checks` and score.

## API

`POST /api/v1/recommend-sites` — versioned, Pydantic-validated JSON.

```json
{
  "start_utc": "2027-11-15T00:00:00Z",
  "duration_hours": 6,
  "sampling_seconds": 3600,
  "candidate_count": 8,
  "max_recommendations": 5,
  "observer_height_m": 2,
  "terrain": {
    "max_distance_km": 2,
    "step_m": 160,
    "interpolation": "bilinear"
  },
  "constraints": {
    "min_sun_fraction": 0.5,
    "min_earth_fraction": 0.5,
    "min_simultaneous_fraction": 0.25,
    "max_darkness_seconds": null,
    "max_earth_outage_seconds": null
  }
}
```

Instead of `duration_hours`, clients can supply `end_utc`. All timestamps are
canonical UTC-Z. Constraints are **user-configurable preferences** and are not
NASA universal landing thresholds. Unspecified outage maximums are not
constraints.

Response fields include `candidates` (all attempted evaluated locations),
`recommendations` (only suitable, sorted), counts, `resolution`, the normalized
0–1 score, score weights, per-constraint booleans, terrain dataset and SPICE
manifest identifiers, Moon-fixed reference frame and scientific limitations.

If no candidates pass constraints, `recommendations` is empty. `resolution` is
`no_suitable_candidates` when the evaluated candidates fail constraints, or
`insufficient_data` when no candidate is evaluable. Missing kernels or DEM are
explicit HTTP 503; invalid mission requests are HTTP 422.

## Geographic candidate selection

The generator samples the **actual opened DEM footprint** in stereographic
projected metres via base-2/base-3 Halton sampling, not uniform longitude.
It insets the raster bounds by the terrain ray's radius plus a buffer, maps
projected coordinates back to lunar planetocentric latitude/east-positive
longitude, calls `LunarDEM.sample`, and rejects nodata/invalid points.
This is deterministic and finite, not randomized and not exhaustive. Candidate
centers are guaranteed to sample valid terrain, while ray completeness is
established independently by the BE-013 evaluation; any gaps lead to
`INSUFFICIENT_DATA` rather than a fabricated score.

## Scientific evaluation and suitability

Each candidate is passed to BE-013 `analyze_visibility_timeline` in
`terrain_aware` mode, using **the same open DEM handle**, the validated
DE421/DE440 SPICE transformation path, and the existing BE-010 horizon engine.
There is no new ephemeris sweep or independent lunar physics. The metric
fractions include all sampled timestamps and UNKNOWN samples are reported.

Only a candidate with **zero UNKNOWN samples and consistent reference frame,
DEM provenance** can receive a definitive score:

```
score = 0.40 * sampled_sun_fraction
      + 0.35 * sampled_earth_fraction
      + 0.25 * sampled_simultaneous_fraction
```

The weights are **illustrative mission preferences, not calibrated NASA
landing-safety factors**. Apply all specified hard constraints first; high
score cannot make a failing candidate suitable. Unspecified maximum outage
constraints are ignored. For equal scores, sort by planetocentric latitude,
then east-positive longitude for reproducible ranking.

The highest visible-duration fractions do not imply safest landing geometry.

## Workload and reproducibility

- Maximum 12 candidates, 24 time samples per candidate, 120,000 approximate
  horizon-ray samples across both celestial targets.
- Current recommendation search radius capped at 20 km; actual valid footprint
  may force a smaller radius and may yield fewer candidates.
- The route serializes the scientific batch under the existing SPICE lock.
- The DEM is opened only once per recommendation request and closed afterward.
- BE-013's existing exact DEM sampling cache remains per-site and per-run.
- Visibility intervals are `[start,end)` with each left-edge sample representing
  the following time cell, including a potentially shortened final cell.
- `processing_seconds` is measured, not a performance guarantee.

## Explicit limitations

The model excludes slope/roughness safety certification, large rocks/craters,
regolith bearing strength, landing dynamics, thermal survival, radiation,
realistic power storage, and actual communication link budgets. Sun and Earth
are treated as geometric centers (`SPICE NONE`), NOT full discs. Terrain
horizons are finite search-radius DEM samples with unverified absolute
mission-grade height datum. Direct-to-Earth geometric visibility does not
certify a radio link. Window durations are sample-resolution approximations.
A site listed as `SUITABLE` **only satisfies the requested illumination and
Earth-visibility screening criteria** and needs further investigation.

## Validation

Run the new unit/API tests and all pre-existing scientific backend tests.
For real NASA validation, configure the official LOLA DEM and both verified
SPICE kernel locks as in previous sprints. Standard CI may skip the real-data
integration if these external assets are not provisioned. Do not weaken older
tests, invent coverage, or treat API/engine consistency as independent
scientific accuracy certification.
