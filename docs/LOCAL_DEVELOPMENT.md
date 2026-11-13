# Local Development Environment

## NASA Space Apps Challenge 2026
### Lunar Landing Site Navigator

This document describes the reproducible development
environment for the independent Python scientific backend.

## 1. Supported Platform

Primary development environment:

- Windows 10/11
- Windows PowerShell
- Python 3.12.x
- Git

Verified development version:

Python 3.12.10

The backend currently supports Python 3.12 only.

GitHub Actions uses Python 3.12 on Ubuntu.

## 2. Repository

Clone the repository:

```powershell
git clone https://github.com/Flourisha14/lunar-landing-site-navigator.git
```

Navigate into the project:

```powershell
cd lunar-landing-site-navigator
```

## 3. Python Installation

Verify Python 3.12:

```powershell
py -3.12 --version
```

If Python 3.12 is unavailable, install it:

```powershell
winget install --id Python.Python.3.12 -e
```

Restart PowerShell after installation.

## 4. Environment Initialization

The project provides a development script:

scripts/dev.ps1

Initialize the backend environment:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command setup
```

The script:

1. Creates backend/.venv if it does not exist.
2. Installs pinned development dependencies.
3. Installs the backend package in editable mode.
4. Verifies dependency consistency.

No system-wide Python packages are required.

## 5. Manual Installation

The environment can also be created manually.

Navigate to:

```powershell
cd backend
```

Create the environment:

```powershell
py -3.12 -m venv .venv
```

Install pinned dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Install the backend:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Verify:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Expected:

No broken requirements found.

## 6. Virtual Environment Activation

Activation is optional.

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, invoke
the virtual environment's Python executable directly.

Example:

```powershell
.\.venv\Scripts\python.exe --version
```

Do not modify system-wide execution policies unnecessarily.

## 7. Dependency Management

The project uses:

- backend/pyproject.toml
- backend/requirements-dev.txt

pyproject.toml defines package requirements.

requirements-dev.txt contains pinned development
dependency versions.

The pinned requirements file is generated using
pip-tools with Python 3.12.

To regenerate it when dependencies change:

```powershell
cd backend

.\.venv\Scripts\python.exe -m pip install "pip-tools>=7,<8"

.\.venv\Scripts\python.exe -m piptools compile --extra dev --strip-extras --output-file requirements-dev.txt pyproject.toml
```

Regenerate dependency pins deliberately.

Test generated requirements on Windows and Ubuntu CI.

Do not manually change package versions in the
generated requirements file.

Scientific and API dependencies are declared as
optional dependency groups.

They are not installed by the default development setup.

## 8. Running Automated Tests

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command test
```

This runs Pytest and generates coverage reports.

## 9. Ruff Linting

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command lint
```

## 10. Ruff Formatting

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command format
```

## 11. Mypy Type Checking

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command typecheck
```

## 12. Complete Local Validation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command check
```

This executes:

1. Ruff lint
2. Ruff formatting
3. Mypy
4. Pytest with coverage

## 13. Scientific Validation Tests

Scientific tests will be identified using:

```python
@pytest.mark.scientific
```

Run scientific validation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command scientific
```

Scientific tests have not yet been implemented.

Until such tests exist, this command may return
Pytest exit code 5 because no matching tests
were collected.

Scientific validation is not yet a separate
mandatory CI gate.

## 14. Environment Variables

A safe example configuration is provided:

.env.example

Create local configuration:

```powershell
Copy-Item .env.example .env
```

Supported conventions:

| Variable | Purpose |
|---|---|
| LUNAR_ENV | Application environment |
| LUNAR_DATA_DIR | Scientific data root |
| LUNAR_SPICE_KERNEL_DIR | SPICE kernels |
| LUNAR_DEM_DIR | Lunar elevation data |
| LUNAR_IMAGERY_DIR | Lunar imagery |
| LUNAR_API_HOST | Future API host |
| LUNAR_API_PORT | Future API port |

Relative paths are intended to resolve from
the repository root.

Runtime environment loading is not yet implemented.

Do not commit .env files, API keys, or credentials.

## 15. Scientific Datasets

Local scientific data directories:

data/kernels/
data/dem/
data/imagery/
data/raw/
data/processed/
data/cache/

These directories are excluded from Git.

NASA SPICE kernels and lunar terrain datasets
must be acquired separately.

Dataset sources, versions, units, coordinate
reference systems, and checksums should be documented.

See:

data/README.md

## 16. FastAPI Development Server

The API dependency group can be installed when
the HTTP backend is implemented.

The development script reserves:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Command api
```

This command is not operational yet.

FastAPI dependencies and the API application
entry point have not been implemented.

## 17. GitHub Actions

The repository uses:

.github/workflows/backend-ci.yml

CI validates:

- Python 3.12 environment
- Backend dependency installation
- Ruff
- Mypy
- Pytest
- Coverage generation

CI runs on pull requests and pushes to main.

The development environment should pass the
same checks locally before opening pull requests.

## 18. Known Limitations

- Scientific computations are not yet implemented.
- SPICE kernels are not included in Git.
- Lunar DEM datasets are not included in Git.
- Scientific validation tests are pending.
- FastAPI is not yet implemented.
- Windows is the primary local development platform.
- Dependency versions are pinned but not hash-locked.
- Build-system dependencies are not fully locked.
- Cross-platform compatibility must be verified by CI.
- Runtime .env loading is not yet implemented.

## 19. Development Workflow

Use:

main → feature branch → pull request → CI → squash merge

No mandatory human approval is required.

See:

docs/DEVELOPMENT.md