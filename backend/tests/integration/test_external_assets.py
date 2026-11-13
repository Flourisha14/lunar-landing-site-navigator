"""Optional data availability checks, NOT scientific reference comparisons."""

from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.requires_spice
def test_configured_spice_kernel_exists(spice_kernel_file: Path) -> None:
    assert spice_kernel_file.stat().st_size > 0


@pytest.mark.integration
@pytest.mark.requires_dem
def test_configured_dem_exists(dem_file: Path) -> None:
    assert dem_file.stat().st_size > 0
