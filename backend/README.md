# Lunar Landing Site Navigator — Scientific Engine

Standalone Python scientific computation engine developed for the NASA Space Apps Challenge 2026.

## Overview

The `lunar_engine` package provides the architectural foundation for scientifically validated lunar south pole landing-site analysis.

The engine is independent of frontend visualization frameworks and HTTP API implementations.

## Requirements

- Python 3.12
- pip
- Git

## Installation

Navigate to the backend directory:

```powershell
cd backend
```

Create a virtual environment if one does not already exist:

```powershell
py -3.12 -m venv .venv
```

Install the package in editable mode:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Verify Installation

```powershell
.\.venv\Scripts\python.exe -c "import lunar_engine; print(lunar_engine.__version__)"
```

Expected output:

```text
0.1.0
```

## Package Architecture

| Module | Responsibility |
|---|---|
| core | Units, reference frames, timestamps and configuration |
| astronomy | Solar and terrestrial ephemerides using NASA SPICE |
| coordinates | Lunar geographic coordinate transformations |
| terrain | Lunar terrain elevation and horizon obstruction |
| illumination | Solar elevation and illumination windows |
| communication | Direct-to-Earth visibility calculations |
| analysis | Candidate landing-site evaluation and comparison |

## Development Commands

Run all commands from the backend directory.

### Run Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

### Ruff Lint

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

### Ruff Formatting

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
```

### Mypy

```powershell
.\.venv\Scripts\python.exe -m mypy src
```

### Coverage

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=lunar_engine -v
```

## Scientific Design Principles

1. All scientific calculations must use explicit reference frames.
2. Physical quantities must have documented units.
3. Time-dependent calculations must use explicit UTC timestamps.
4. Ephemeris calculations will use reproducible NASA SPICE kernels.
5. Scientific calculations must be deterministic for identical inputs and datasets.
6. Scientific models must be independently validated.
7. Scientific modules must not depend on frontend rendering technologies.

## Current Implementation Status

BE-001 establishes the standalone Python package architecture.

The following components are intentionally deferred to subsequent tickets:

- SPICE ephemeris integration
- Lunar coordinate transformations
- Solar and Earth azimuth/elevation
- Terrain horizon calculations
- Illumination window analysis
- Direct-to-Earth communication windows
- Landing-site comparison

No astronomical calculations are implemented in BE-001.