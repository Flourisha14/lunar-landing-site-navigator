"""Real-kernel integration checks: physically sensible, NOT independent reference values."""

from datetime import datetime
from pathlib import Path

import pytest

from lunar_engine.astronomy import analyze_celestial_geometry
from lunar_engine.astronomy.ephemeris import default_provider
from lunar_engine.astronomy.kernels import verify_kernels
from lunar_engine.core.conventions import LunarFrame

ROOT = Path(__file__).resolve().parents[3]


def _require_kernels() -> None:
    pytest.importorskip("spiceypy")
    lock = ROOT / "data/spice/kernel-lock.json"
    binaries = ROOT / "data/spice/kernels"
    if not lock.is_file():
        pytest.skip("NASA SPICE kernel lock unavailable")
    if not binaries.is_dir():
        pytest.skip("NASA SPICE kernel binaries unavailable")
    provider = default_provider(ROOT)
    missing = [
        item["filename"]
        for item in provider.manifest["entries"]
        if not (binaries / item["filename"]).is_file()
    ]
    if missing:
        pytest.skip(f"NASA SPICE kernel binaries unavailable: {missing}")
    # A downloaded but corrupt kernel must FAIL rather than be skipped.
    verify_kernels(provider.manifest, binaries)


@pytest.mark.integration
@pytest.mark.requires_spice
def test_utc_et_roundtrip_and_frame_rotation() -> None:
    _require_kernels()
    with default_provider(ROOT) as provider:
        utc = "2027-11-15T12:00:00.000000Z"
        et = provider.utc_to_et(utc)
        recovered = provider.et_to_utc(et)
        delta = datetime.fromisoformat(recovered.replace("Z", "+00:00")) - datetime.fromisoformat(
            utc.replace("Z", "+00:00")
        )
        assert abs(delta.total_seconds()) <= 2e-6
        for body in ("SUN", "EARTH"):
            me = provider.position(body, utc, LunarFrame.ME)
            pa = provider.position(body, utc, LunarFrame.PA)
            assert me.position.frame == LunarFrame.ME
            assert pa.position.frame == LunarFrame.PA
            assert me.kernel_manifest_id == provider.kernel_manifest_id
            assert me.distance_unit == "km"
            # Independent invariant: orthogonal frame rotations preserve Euclidean norm.
            n_me = sum(v * v for v in (me.position.x_km, me.position.y_km, me.position.z_km))
            n_pa = sum(v * v for v in (pa.position.x_km, pa.position.y_km, pa.position.z_km))
            assert n_me == pytest.approx(n_pa, rel=1e-12)
        provider.check_epochs(("2026-11-14T00:00:00Z", "2027-11-15T12:00:00Z"))


@pytest.mark.integration
@pytest.mark.requires_spice
def test_real_south_pole_geometry_is_deterministic() -> None:
    _require_kernels()
    kwargs = dict(latitude_deg=-89.5, longitude_deg=45.0, timestamp_utc="2027-11-15T12:00:00Z")
    result = analyze_celestial_geometry(**kwargs, repository_root=ROOT)
    again = analyze_celestial_geometry(**kwargs, repository_root=ROOT)
    assert result == again
    for target in (result.sun, result.earth):
        assert -90 <= target.elevation_deg <= 90
        assert target.azimuth_deg is None or 0 <= target.azimuth_deg < 360
        assert target.range_km > 0
        norm_sq = sum(v * v for v in (target.east_unit, target.north_unit, target.up_unit))
        assert norm_sq == pytest.approx(1, abs=1e-12)
