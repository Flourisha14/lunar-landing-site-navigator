"""Shared, non-scientific fixtures and externally gated data fixtures."""

import os
from pathlib import Path

import pytest
from hypothesis import settings

from lunar_engine.core.conventions import LUNAR_REFERENCE_RADIUS_KM, LunarFrame

settings.register_profile("reproducible", derandomize=True, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "reproducible"))


@pytest.fixture(scope="session")
def lunar_reference_radius_km() -> float:
    return LUNAR_REFERENCE_RADIUS_KM


@pytest.fixture(scope="session")
def nominal_moon_frame() -> LunarFrame:
    return LunarFrame.ME


def _external_file(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        pytest.skip(f"{variable} not configured; external data unavailable")
    path = Path(value)
    if not path.is_file():
        pytest.skip(f"{variable} is not a readable file: {path}")
    return path


@pytest.fixture(scope="session")
def spice_kernel_file() -> Path:
    return _external_file("LUNAR_SPICE_KERNEL_FILE")


@pytest.fixture(scope="session")
def dem_file() -> Path:
    return _external_file("LUNAR_DEM_FILE")
