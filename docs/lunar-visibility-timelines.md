# BE-013 — UTC visibility timelines and estimated windows

## Scope

Deterministic sampled UTC analysis of the existing NASA SPICE + DE421/DE440
lunar geometry and BE-011/012 terrain-aware Sun/Earth center visibility.
No frontend or FastAPI dependencies. Not a mission-certified planner.

## Public API

```python
from lunar_engine.analysis import analyze_visibility_timeline

# `dem` must be an OPEN existing LunarDEM in terrain_aware mode.
result = analyze_visibility_timeline(
    latitude_deg=-89.5, longitude_deg=45,
    start_utc="2027-11-15T00:00:00Z",
    end_utc="2027-11-16T00:00:00Z",
    sampling_seconds=3600,
    observer_height_m=2.0,
    mode="terrain_aware", dem=dem,
    max_distance_km=2.0, step_m=80.0, interpolation="bilinear",
    repository_root=repo_root,
)
```

`mode="geometric"` works without a DEM; the observer is then positioned
relative to the reference sphere with elevation equal to observer height.
Supplying a DEM in geometric mode uses its measured surface elevation for
topocentric geometry but still compares target elevations with the local
**spherical tangent plane (0 degrees)**, not the terrain horizon.

A caller-owned DEM is opened/closed **outside** this function. The verified
SPICE adapter is invoked once per timestamp and provides Sun and Earth together.

### Time grid

- Timezone: UTC strictly in ISO-8601 `Z` form, canonicalized to microseconds.
- Mission interval is **[start,end)**: start included, end excluded.
- Sampling step: strictly positive **integer seconds**; no floating-point date stepping.
- The final sample can represent a shortened cell ending exactly at `end`.
- Bound: <= 90 days and <= 2,048 samples. Callers may lower `max_samples`,
  but cannot raise the hard cap. Invalid workloads fail before SPICE operations.
- UTC strings use the existing core parser. Leap-second representation is not
  supported by that parser; UTC-to-ET is performed by the existing SPICE engine.
- The requested ephemeris dates are checked by the real SPICE provider at each
  sample; unsupported epochs produce an explicit error. Continuous coverage
  between samples is **not independently established**.

### Result structure

`VisibilityTimeline` reports normalized interval timestamps, observer
coordinates/height, mode, frame, DEM dataset id (if used), SPICE kernel
manifest id, terrain settings, samples, windows, aggregate metrics, and
processing seconds (non-deterministic runtime metadata, excluded from equality).

Each `VisibilitySample` retains:
- Separate point-center **geometric** Sun and Earth states (`elevation > 0`),
  even in terrain-aware mode.
- Requested-mode Sun, Earth, and simultaneous visibility states.
- Actual SPICE-derived Sun/Earth azimuths and elevations, terrain horizons
  when relevant, and calculation fidelity/kernel provenance.

`UNKNOWN` indicates insufficient terrain evidence, for example an incomplete
DEM horizon or undefined azimuth. No `UNKNOWN` cell is counted as confirmed
visible or dark/outage. For intersection, three-state logic is:

- Any known `OBSTRUCTED` => simultaneous `OBSTRUCTED`.
- Otherwise, any `UNKNOWN` => simultaneous `UNKNOWN`.
- Otherwise, simultaneous `VISIBLE`.

### Window extraction

For each category `sunlight`, `earth_visible`, `simultaneous`, `darkness`,
and `earth_outage`, contiguous sample cells that confirm the category are
merged into `VisibilityWindow` instances. Darkness means confirmed solar
`OBSTRUCTED`; Earth outage means confirmed Earth `OBSTRUCTED`.

An active cell is **[sample_time, next_sample_time)**, and the last cell ends
at mission end. A window's start/end and duration are therefore **estimated
sample-bin boundaries**, not observed physical crossing times. Each window
reports the sampling interval, count, resolution-based boundary uncertainty,
and flags if it touches mission start/end (left/right censored). Transitions
can occur anywhere between samples, up to one sampling interval away from a
reported boundary; durations may also be biased by coarse sampling.

### Aggregate statistics

- Sample fractions use **all sampled instants** as the denominator, so UNKNOWN
  reduces the confirmed fraction rather than being counted as obstruction.
- Confirmed visible durations sum their associated cell widths; the short
  last cell is weighted by its actual duration.
- UNKNOWN counts and estimated UNKNOWN durations are reported for Sun, Earth,
  and simultaneous visibility separately.
- Longest continuous durations are maximum confirmed window durations.
- Confirmed fractions are not a statistically inferred physical fraction
  of continuously illuminated mission time.

### Terrain data caching and performance

The provided `LunarDEM` handle is reused across the entire call. A session-local
16,384-entry LRU cache memoizes **exact DEM queries** by full latitude,
longitude and interpolation mode. This reuse is safe because the selected
terrain dataset/handle and observer configuration are fixed during a call.
Cache hits/misses are reported. No DEM samples are cached across calls or
across incompatible locations, heights, frames, datasets, or interpolation
parameters. The terrain horizon itself is recalculated for each actual
Sun/Earth azimuth and epoch, to **avoid unsafe quantized azimuth reuse**.
This is a deliberate correctness/performance trade-off. Each sample still
runs the existing verified SPICE geometry path, which may reload verified
kernel contexts. No parallel SPICE calls are attempted (global kernel state).

### Scientific limitations

- Geometric, center-of-disc only; SPICE aberration setting is `NONE`.
- Visibility uses a strict elevation greater than the sampled horizon; equality
  is obstructed. Elevation zero in geometric mode is obstructed.
- Partial solar-disc illumination, Earth-disc limb, radio link budgets,
  spacecraft masking, and actual operational communication windows excluded.
- Terrain search radius, raster resolution, sampling step, interpolation,
  and source datum assumption constrain horizon estimates. A completed finite
  DEM ray does not establish convergence beyond its maximum distance.
- Elevation datum acknowledgement is not independent certification of DEM
  registration. Independent ephemeris references remain outstanding.
- No sub-sample root finding, transition refinement, adaptive step size, or
  mission-grade uncertainty model in this ticket.

## Testing

`tests/unit/test_visibility_timeline.py` uses hand-authored synthetic state
sequences to verify endpoints, exact expected window lengths, UNKNOWN logic,
intersection, invalid grids, deterministic calls, and geometric/terrain modes.
`tests/integration/test_real_visibility_timeline.py` uses real NASA LOLA and
verified DE421/DE440 SPICE files when configured. On standard CI it skips if
those large private-local assets are absent; set
`LUNAR_REQUIRE_REAL_TIMELINE=1` locally to require a pass instead of a skip.

Use `python -m pytest -v`, `python -m ruff check .`,
`python -m ruff format --check .`, and `python -m mypy src` from `backend/`.

## NASA LOLA + SPICE 24-Hour Demonstration

### Configuration

- Observer: -89.5° latitude, +45.0° longitude
- Observer height: 2 m
- Start: 2027-11-15T00:00:00Z
- End: 2027-11-16T00:00:00Z
- Sampling interval: 3600 seconds
- Mode: terrain_aware
- Terrain search radius: 10 km
- Terrain sampling interval: 80 m
- Interpolation: bilinear
- Reference frame: MOON_ME_DE421
- SPICE aberration correction: NONE

### Results

| Metric | Sun | Earth | Simultaneous |
|---|---:|---:|---:|
| Visible samples | 24/24 | 24/24 | 24/24 |
| Sampled visibility fraction | 100% | 100% | 100% |
| Estimated visible duration | 24 h | 24 h | 24 h |
| Longest continuous window | 24 h | 24 h | 24 h |
| Unknown samples | 0 | 0 | 0 |

All 24 hourly samples classified both celestial centers as visible.

Estimated visibility windows:

- Sunlight: 2027-11-15T00:00:00Z to 2027-11-16T00:00:00Z
- Earth: 2027-11-15T00:00:00Z to 2027-11-16T00:00:00Z
- Simultaneous: 2027-11-15T00:00:00Z to 2027-11-16T00:00:00Z

### Performance

- Total processing time: 3.351 seconds
- Terrain cache hits: 71
- Terrain cache misses: 6001
- Total temporal samples: 24

### Scientific Interpretation

The timeline uses start-inclusive, end-exclusive sampling.

Each sampled visibility state is assigned to its following time cell.

The reported 24-hour windows are sampling-resolution estimates;
they do not establish uninterrupted physical visibility between
samples.

The terrain-horizon assessment is limited to a 10 km search radius.

The Sun and Earth are represented by geometric point centers.

Earth geometric visibility is not equivalent to guaranteed
radio communication availability.
