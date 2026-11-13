"""Kernel checksum verification tests use synthetic files, not fake SPICE data."""

import hashlib
from pathlib import Path

import pytest

from lunar_engine.astronomy.kernels import KernelManifest, verify_kernels


@pytest.mark.unit
def test_hash_verification_and_corruption(tmp_path: Path) -> None:
    content = b"synthetic integrity fixture, not a SPICE kernel"
    kernel = tmp_path / "fixture.bsp"
    kernel.write_bytes(content)
    manifest: KernelManifest = {
        "id": "synthetic",
        "entries": [
            {
                "filename": kernel.name,
                "url": "https://example.invalid/fixture.bsp",
                "kind": "SPK",
                "sha256": hashlib.sha256(content).hexdigest(),
                "coverage_note": "not a scientific case",
            }
        ],
    }
    assert verify_kernels(manifest, tmp_path) == [kernel]
    kernel.write_bytes(content + b"corrupt")
    with pytest.raises(ValueError, match="mismatch"):
        verify_kernels(manifest, tmp_path)
