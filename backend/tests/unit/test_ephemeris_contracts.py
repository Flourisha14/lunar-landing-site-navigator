"""Tests for time parsing and fail-closed provider behavior without real kernels."""

from pathlib import Path

import pytest

from lunar_engine.astronomy.ephemeris import EphemerisProvider, canonical_utc


@pytest.mark.unit
def test_canonical_utc() -> None:
    assert canonical_utc("2027-11-15T12:00:00Z") == "2027-11-15T12:00:00.000000Z"
    assert canonical_utc("2027-11-15T12:00:00.001Z") == "2027-11-15T12:00:00.001000Z"
    for invalid in ("2027-11-15T12:00:00", "2027-11-15T12:00:00+05:30", "invalid"):
        with pytest.raises(ValueError):
            canonical_utc(invalid)


@pytest.mark.unit
def test_provider_requires_explicit_kernel_context(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    lock.write_text('{"id":"test","entries":[]}', encoding="utf-8")
    provider = EphemerisProvider(lock, tmp_path)
    with pytest.raises(RuntimeError, match="with statement"):
        provider.utc_to_et("2027-11-15T12:00:00Z")
    with pytest.raises(RuntimeError, match="with statement"):
        provider.et_to_utc(123.0)
    with pytest.raises(RuntimeError, match="with statement"):
        provider.position("SUN", "2027-11-15T12:00:00Z")
