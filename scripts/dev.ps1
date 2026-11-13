param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "setup",
        "test",
        "scientific",
        "lint",
        "format",
        "typecheck",
        "check",
        "api"
    )]
    [string]$Command
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$VenvDir = Join-Path $BackendDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"

function Invoke-BackendPython {
    param(
        [string[]]$Arguments
    )

    if (-not (Test-Path $Python)) {
        throw "Python virtual environment not found. Run setup first."
    }

    Push-Location $BackendDir

    try {
        & $Python @Arguments

        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

switch ($Command) {

    "setup" {
        if (-not (Test-Path $Python)) {
            Write-Host "Creating Python 3.12 environment..."

            & py -3.12 -m venv $VenvDir

            if ($LASTEXITCODE -ne 0) {
                throw "Virtual environment creation failed."
            }
        }

        Write-Host "Installing pinned dependencies..."

        Invoke-BackendPython -Arguments @(
            "-m", "pip", "install",
            "-r", "requirements-dev.txt"
        )

        Write-Host "Installing backend package..."

        Invoke-BackendPython -Arguments @(
            "-m", "pip", "install",
            "--no-deps", "-e", "."
        )

        Invoke-BackendPython -Arguments @(
            "-m", "pip", "check"
        )

        Write-Host "Development environment ready."
    }

    "test" {
        Invoke-BackendPython -Arguments @(
            "-m", "pytest",
            "--cov=lunar_engine",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml",
            "-v"
        )
    }

    "scientific" {
        Invoke-BackendPython -Arguments @(
            "-m", "pytest",
            "-m", "scientific",
            "-v"
        )
    }

    "lint" {
        Invoke-BackendPython -Arguments @(
            "-m", "ruff", "check", "."
        )
    }

    "format" {
        Invoke-BackendPython -Arguments @(
            "-m", "ruff", "format",
            "--check", "."
        )
    }

    "typecheck" {
        Invoke-BackendPython -Arguments @(
            "-m", "mypy", "src"
        )
    }

    "check" {
        Invoke-BackendPython -Arguments @(
            "-m", "ruff", "check", "."
        )

        Invoke-BackendPython -Arguments @(
            "-m", "ruff", "format",
            "--check", "."
        )

        Invoke-BackendPython -Arguments @(
            "-m", "mypy", "src"
        )

        Invoke-BackendPython -Arguments @(
            "-m", "pytest",
            "--cov=lunar_engine",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml",
            "-v"
        )

        Write-Host "All local checks passed."
    }

    "api" {
        Write-Host "Starting FastAPI development server..."

        Invoke-BackendPython -Arguments @(
            "-m", "uvicorn",
            "lunar_engine.api:app",
            "--reload",
            "--host", "127.0.0.1",
            "--port", "8000"
        )
    }
}