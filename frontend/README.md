# Lunasolum Frontend (FE-001 + FE-004)

Scientific mission-control UI built with React, TypeScript and Vite. No astronomical or DEM calculations occur in React. The FastAPI backend is authoritative.

## Requirements

- Node.js 20.19+ or 22.12+ (Vite 7)
- Python scientific backend configured separately: see `../docs/scientific-api-v1.md`

## Start (PowerShell)

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173` (or the local URL Vite prints). The backend URL comes from `VITE_LUNAR_API_URL` and defaults to `http://127.0.0.1:8000`. The backend's default CORS allows `http://localhost:5173` (and `http://localhost:3000`). Use the **localhost** URL, not the `127.0.0.1` frontend origin, unless you extend backend CORS.

## Checks

```powershell
npm run typecheck
npm test
npm run build
```

## Actual API v1 contract

- `GET /api/v1/health` shows connection + resource readiness; it does not verify kernel epoch coverage.
- `GET /api/v1/metadata` supplies available modes, dataset information and limitations.
- `POST /api/v1/geometry` calculates geometric Sun/Earth center directions relative to **explicit reference-surface elevation 0 m** (reference sphere, **not** DEM).
- `POST /api/v1/site-analysis` calculates requested geometric or terrain-aware states, with three distinct visibility states: `visible`, `obstructed`, `unknown`.

The UI requests geometry and analysis independently. If site analysis fails, reference-sphere geometry may remain visible, but it is explicitly identified and **never silently substituted** for terrain-aware results. When terrain is unknown or unavailable, no zero horizon is invented. The terrain dataset is read from backend metadata; no south-polar dataset ID is hardcoded into components.

Dates are entered as **UTC**, not local time. Default form values are an *editable documentation example*, not live results. Longitude is east-positive, and the backend is responsible for canonical normalization. Direction azimuth can be `null` at zenith/nadir.

**Limitations:** Geometric visibility is not a verified radio link; no link budget or solar-disc fraction is modeled. `/timeline` exists in backend but is out of this sprint's frontend scope. UI coverage is a descriptive summary of the returned per-target statuses, not a global DEM coverage proof. Full integration requires local SPICE binaries and DEM assets; unit tests do not simulate real NASA scientific values.

## Continuous Integration

Frontend validation is automated through GitHub Actions.

Workflow: `.github/workflows/frontend-ci.yml`

The workflow runs on pull requests targeting `main` and pushes to `main` when frontend files or the frontend CI workflow change.

### Automated checks

- Node.js 24 setup.
- Reproducible installation using `npm ci`.
- TypeScript validation using `npm run typecheck`.
- ESLint validation using `npm run lint`.
- Existing Vitest tests using `npm test`.
- Vite production build using `npm run build`.

### Local verification

From the `frontend/` directory:

    npm.cmd ci
    npm.cmd run typecheck
    npm.cmd run lint
    npm.cmd test
    npm.cmd run build
    npm.cmd audit

The frontend workflow operates independently of the scientific backend CI.

No NASA SPICE kernels or LOLA DEM files are required for frontend validation.

## FE-002 � Interactive Lunar Globe

The frontend includes a CesiumJS lunar reference globe integrated with Mission Control.

### Features

- Moon-sized reference sphere with a radius of 1,737,400 metres.
- Interactive globe rotation and zoom.
- Latitude/longitude coordinate grid.
- Lunar surface selection.
- Selected-site marker.
- Synchronization with Mission Controls.
- UTC timestamp preservation.
- Scientific API integration using the existing FastAPI client.
- Regional terrain coverage limitations.

The globe is a visualization and interaction interface. It does not independently calculate astronomical positions, illumination, or terrain visibility.

The current globe is a smooth reference sphere rather than a lunar elevation model.

### Automated Regression Tests

Frontend testing includes:

- Vitest unit tests for lunar coordinate transformations and request validation.
- Playwright browser tests for Cesium rendering and camera navigation.
- Surface selection and Mission Controls synchronization.
- UTC preservation and scientific API request integration.
- Polar camera stability.

Run locally from the frontend directory:

    npm.cmd ci
    npm.cmd run typecheck
    npm.cmd run lint
    npm.cmd test
    npm.cmd run build
    npm.cmd run test:e2e

Playwright browser tests run in Chromium and use isolated scientific API fixtures.

The existing scientific backend tests remain responsible for validating actual NASA SPICE and LOLA calculations.

The frontend GitHub Actions workflow executes the browser regression tests automatically.

## FE-003 — Babylon Local Lunar Surface

Open **Local surface · Babylon** from Mission Control. The Cesium and Babylon
viewers are mutually exclusive: switching views releases the previous canvas
and GPU engine. The local scene offers orbit and zoom controls and recreates
its renderer after switching back.

### Scientific lighting contract

The frontend reuses the existing FastAPI `/api/v1/geometry` response from
`useLunarAnalysis`. The backend-provided `sun.east_unit`, `north_unit` and
`up_unit` form the observer-to-Sun unit vector in lunar local East/North/Up.
The local Babylon world is **+X=East, +Y=Up, +Z=North** (left-handed).
Babylon's `DirectionalLight.direction` describes *travel direction of rays*,
so its vector is `(-east_unit, -up_unit, -north_unit)` after normalization.

`sunToBabylon` validates the Sun target, frame (`MOON_ME_*`), planetocentric
and east-positive conventions, direction norm, and the backend azimuth and
elevation. The local view never calculates solar ephemerides. Results are
applied only if both the UTC timestamp and selected site match the current
mission input; stale, missing, or inconsistent results disable directional
sunlight. Backend visibility and terrain-aware assessment remain separate
from display lighting. Timestamp changes request fresh geometry automatically.

### Illustrative rendering limitations

The ground and demo rocks are synthetically constructed. They **are not**
sampled NASA LOLA elevations. The small non-scientific fill light is for
interface legibility and does not prove local daylight. Directional-light
intensity is artistic, not calibrated irradiance. No terrain-accurate shadows
or solar power predictions are provided. FE-005 will address actual DEM mesh
rendering; the configured regional LOLA DEM remains backend-only for now.

### Testing and CI

Install dependencies from `frontend` with `npm install @babylonjs/core` and
`npm install -D @testing-library/react jsdom`. Execute:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
npm.cmd run test:e2e
```

Vitest tests cover cardinal directions, below-horizon behavior, invalid
geometry, stale data, component lifecycle, failure fallback, and resource
cleanup using a mock scene (no GPU). Chromium Playwright tests cover view
switching, local canvas startup, UTC changes, API fixture responses, and
returning to Cesium. The existing frontend GitHub Actions workflow already
runs `npm test` and `npm run test:e2e`, so it discovers these new suites.
Scientific numerical accuracy remains in the independent Python backend QA.
