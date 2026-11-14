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
