# 🌕 Lunar Landing Site Navigator

### NASA Space Apps Challenge 2026

A scientifically grounded, interactive lunar landing-site
assessment application focused on the Moon's south polar region.

## Mission

Enable users to explore and compare candidate lunar landing
sites using physically meaningful lighting, communication,
and terrain constraints.

## Scientific Capabilities

Planned functionality includes:

1. NASA SPICE ephemeris calculations
2. Lunar coordinate transformations
3. Solar azimuth and elevation
4. Earth visibility calculations
5. Lunar terrain and horizon analysis
6. Illumination-window prediction
7. Landing-site comparison

## Architecture

The application consists of two independent components.

### Scientific Backend

Python-based scientific computation engine.

Location: `backend/`

Package: `lunar_engine`

The backend must remain independent of web and
visualization frameworks.

### Interactive Frontend

Web-based visualization and interactive site exploration.

Location: `frontend/`

The frontend consumes results produced by the scientific backend.

## Project Structure

```text
backend/       Scientific Python engine
frontend/      Interactive visualization
data/          Scientific dataset documentation
docs/          Architecture and scientific methodology
scripts/       Development utilities
.github/       Automation and collaboration
```

## Development Environment

- Python 3.12+
- Git
- Node.js for frontend development

## Backend Setup

From the repository root:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Development Workflow

1. Create a feature branch from `main`.
2. Implement changes.
3. Run local validation.
4. Create a pull request.
5. Run automated checks.
6. Obtain review.
7. Merge into `main`.

See [Development Guide](docs/DEVELOPMENT.md).

## Scientific Integrity

Scientific calculations must be reproducible,
testable, and traceable to authoritative references.

Reference values, coordinate conventions,
units, and numerical tolerances must be documented.

## Data Management

Large datasets and SPICE kernels are not committed.

See [Data Management](data/README.md).

## Project Status

Active development for NASA Space Apps Challenge 2026.

## License

MIT License.