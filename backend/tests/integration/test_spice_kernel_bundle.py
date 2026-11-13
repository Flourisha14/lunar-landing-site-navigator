"""Optional real-kernel validation; CI without kernels skips explicitly."""

from pathlib import Path

import pytest

from lunar_engine.astronomy.kernels import read_manifest, verify_kernels, verify_spice_coverage


@pytest.mark.integration
@pytest.mark.requires_spice
def test_real_spice_bundle() -> None:
    root = Path(__file__).resolve().parents[3]
    manifest_file = root / "data" / "spice" / "kernel-lock.json"
    kernel_dir = root / "data" / "spice" / "kernels"
    if not manifest_file.exists() or not kernel_dir.exists():
        pytest.skip("Verified SPICE kernel lock or local binaries unavailable")
    pytest.importorskip("spiceypy")
    manifest = read_manifest(manifest_file)
    verify_kernels(manifest, kernel_dir)
    assert verify_spice_coverage(manifest, kernel_dir)["frames"] == "ME and PA resolved"
