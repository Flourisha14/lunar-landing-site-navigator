# Lunasolum — Scientific REST API v1

Sprint 8: BE-015, BE-016, QA-005. This service *adapts* existing Python scientific
routines; it does not contain independent SPICE, DEM, terrain horizon or visibility
algorithms. `lunar_engine` does not depend on FastAPI, Pydantic or any renderer.

## Installation and launch (Windows PowerShell)

From `backend` in a Python 3.12 virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,science,api]"
$env:LUNAR_REPOSITORY_ROOT = (Resolve-Path ..).Path
$env:LUNAR_DEM_FILE = (Resolve-Path "..\data\dem\LDEM_80S_80MPP_ADJ_southpole_demo_80km.TIF").Path
$env:LUNAR_DEM_DATUM_CONFIRMED = "1"
.\.venv\Scripts\python.exe -m uvicorn lunar_api.app:app --host 127.0.0.1 --port 8000
```

`LUNAR_DEM_DATUM_CONFIRMED=1` is **an explicit acknowledgement of the existing
terrain-datum interpretation**, not independent publisher verification.
No external datasets are downloaded and no mock scientific values are returned.
SPICE requires both verified kernel lock files and their downloaded binaries.

Interactive docs: `http://127.0.0.1:8000/docs`; OpenAPI JSON:
`http://127.0.0.1:8000/openapi.json`.

## Endpoints

| Method/path | Contract | Behavior |
|---|---|---|
| GET `/api/v1/health` | `HealthResponse` | Reports presence of kernel manifests; does not prove kernel coverage. |
| GET `/api/v1/metadata` | `MetadataResponse` | Modes, units, datasets, frame, bounds, limitations. |
| POST `/api/v1/geometry` | `GeometryRequest` -> `GeometryResponse` | Geometric center directions in `MOON_ME_DE421`, including local ENU unit vector, Moon-centered target position in km, range, azimuth, elevation. |
| POST `/api/v1/site-analysis` | `SiteAnalysisRequest` -> `SiteAnalysisResponse` | Geometric or DEM-aware visibility of Sun/Earth, three states and metadata. |
| POST `/api/v1/timeline` | `TimelineRequest` -> `TimelineResponse` | Sampled visibility states, windows, aggregate metrics and temporal caveats. |

### Geometry example

```json
{
  "latitude_deg": -89.5,
  "longitude_deg": 45.0,
  "timestamp_utc": "2027-11-15T12:00:00Z",
  "observer_height_m": 2.0,
  "reference_surface_elevation_m": 0.0
}
```

In `/geometry`, reference-surface elevation is **an explicit user-supplied
radial height above the 1737.4 km reference sphere**. Default zero represents
the reference sphere; it is **not** a measurement from a DEM. To place the
instrument at a physical terrain height, explicitly supply the site's DEM
radial elevation. `/site-analysis` with `terrain_aware` derives this from DEM.

### Site analysis example

```json
{
  "latitude_deg": -89.5,
  "longitude_deg": 45.0,
  "timestamp_utc": "2027-11-15T12:00:00Z",
  "observer_height_m": 2.0,
  "mode": "terrain_aware",
  "terrain": {
    "max_distance_km": 10.0,
    "step_m": 80.0,
    "interpolation": "bilinear"
  }
}
```

Mode `geometric` uses the lunar reference sphere and does not require DEM.
It reports no terrain-horizon angle. No silent fallback is permitted from
`terrain_aware` to `geometric`. UNKNOWN is distinct from OBSTRUCTED and
VISIBLE, and null horizon fields remain null when terrain is unavailable.

### Timeline example

```json
{
  "latitude_deg": -89.5,
  "longitude_deg": 45.0,
  "start_utc": "2027-11-15T00:00:00Z",
  "end_utc": "2027-11-16T00:00:00Z",
  "sampling_seconds": 3600,
  "observer_height_m": 2.0,
  "mode": "terrain_aware",
  "terrain": {
    "max_distance_km": 10.0,
    "step_m": 80.0,
    "interpolation": "bilinear"
  }
}
```

Timeline samples are start-inclusive, end-exclusive. The state at the left
edge controls the subsequent time cell, including any shortened final cell.
Window boundaries and durations are **sample-resolution estimates** and do not
establish exact physical transition instants. The endpoint is not separately
sampled. `UNKNOWN` is not counted as confirmed visible or obstructed.

## Scientific units and frames

- Latitude: planetocentric degrees in [-90, 90].
- Longitude: east-positive degrees, normalized to [-180, 180); at exact poles,
  canonical longitude is zero.
- UTC: strict ISO 8601 timestamp ending `Z` (no non-UTC offsets).
- Azimuth: degrees clockwise from local north; null at zenith/nadir.
- Elevation / horizon / clearance: degrees.
- East/north/up components: dimensionless topocentric direction cosines.
- `position_moon_fixed_km`: Moon-centered target coordinates, kilometres.
- Range: kilometres.
- Observer height: metres above DEM terrain for terrain-aware mode; metres
  above explicitly supplied reference surface in geometric mode.
- Frame: MOON_ME_DE421 for terrain-aligned scientific geometry.
- SPICE correction: `NONE` (geometric target centers, not apparent discs).
- Terrain provenance: `terrain_dataset_id`, `reference_frame`, kernel manifest.

## Error contract

- `422` Pydantic validation: coordinates, timestamps, invalid period, sampling
  workload or mode/terrain conflict; no scientific call performed.
- `422` scientific coverage: unsupported SPICE epoch, DEM origin outside
  coverage or unsupported terrain geometry.
- `503` resources unavailable: required kernel manifests/binaries or DEM
  missing; checksums and external scientific dependencies are never bypassed.
- `500` unexpected server failure: sanitized, no fabricated science values.

Kernel files are cryptographically verified by existing kernel manager during
scientific calls. JSON clients receive normalized `detail` and `code` for
scientific exceptions, and FastAPI standard 422 validation payloads for
request/schema errors.

## Performance, concurrency, and CORS

The API uses synchronous handlers (FastAPI's thread pool). Scientific requests
are serialized using a service-scoped reentrant lock because CSPICE uses a
process-global kernel pool. Run **one Uvicorn worker per process**. Multiple
worker processes manage separate kernel pools; rate limiting and global
resource capacity management are deployment concerns.

The DEM opens in a request-scoped context and always closes, including on
exceptions. Timeline caching stays internal to BE-013 and does not permit
scientifically unsafe horizon reuse across different azimuths.

Development CORS defaults to `http://localhost:3000` and
`http://localhost:5173`; override the comma-separated allowlist with
`LUNAR_API_CORS_ORIGINS`. Do not use unrestricted `*` in production.

Maximum timeline duration is 90 days; at most 2048 time samples. Terrain
queries are also limited to 2048 raster steps per sightline. Workload remains
potentially substantial for combined maximal settings: deploy resource/timeout
limits for real web exposure.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_contracts.py tests/api/test_adapter_unit.py -v
$env:LUNAR_REQUIRE_REAL_API = "1"
.\.venv\Scripts\python.exe -m pytest tests/api/test_real_api.py -v -rs
.\.venv\Scripts\python.exe -m pytest --cov=lunar_engine --cov-report=term-missing -v -rs
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
```

The real scientific API test compares HTTP results to **direct calls** to the
existing engine under exactly the same DEM/SPICE configuration. It is not an
independent ephemeris or terrain ground truth. Normal CI skips this test when
the large NASA LOLA raster is unavailable; local strict mode requires it.
Synthetic HTTP tests use explicitly labeled fixtures only to verify contracts.

### Limitations

No exact transition-time extraction, solar-disc illumination, apparent Earth
disc, link budget, live telemetry, guaranteed Earth communications, DEM error
model, or mission-certified ephemeris/datum validation is provided.
