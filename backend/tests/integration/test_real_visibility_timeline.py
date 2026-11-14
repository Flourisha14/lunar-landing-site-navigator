"""Real LRO LOLA and hash-verified DE421/DE440 SPICE temporal integration.

Requires user-provisioned assets. Set LUNAR_REQUIRE_REAL_TIMELINE=1 for hard fail.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from lunar_engine.analysis.timeline import analyze_visibility_timeline
from lunar_engine.analysis.visibility import VisibilityStatus
from lunar_engine.core.conventions import LunarFrame
from lunar_engine.terrain.dem import DEFAULT_LOLA_METADATA, LunarDEM

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
@pytest.mark.requires_dem
@pytest.mark.requires_spice
def test_real_spice_lola_timeline() -> None:
    raw = os.environ.get("LUNAR_DEM_FILE")
    ready = (
        bool(raw)
        and Path(raw).is_file()
        and os.environ.get("LUNAR_DEM_DATUM_CONFIRMED") == "1"
        and (ROOT / "data/spice/kernel-lock.json").is_file()
        and (ROOT / "data/spice/de421-frame-lock.json").is_file()
    )
    if not ready:
        msg = "NASA LOLA and verified DE421/DE440 kernel locks required"
        if os.environ.get("LUNAR_REQUIRE_REAL_TIMELINE") == "1":
            pytest.fail(msg)
        pytest.skip(msg)
    assert raw is not None
    with LunarDEM(raw, metadata=replace(DEFAULT_LOLA_METADATA, datum_confirmed=True)) as dem:
        args = dict(
            latitude_deg=-89.5,
            longitude_deg=45.0,
            start_utc="2027-11-15T12:00:00Z",
            end_utc="2027-11-15T15:00:00Z",
            sampling_seconds=3600,
            observer_height_m=2,
            mode="terrain_aware",
            dem=dem,
            max_distance_km=2,
            step_m=80,
            interpolation="bilinear",
            repository_root=ROOT,
        )
        first = analyze_visibility_timeline(**args)
        second = analyze_visibility_timeline(**args)
        assert first == second
        assert first.frame is LunarFrame.ME_DE421
        assert first.terrain_dataset_id == dem.metadata.dataset_id
        assert len(first.samples) == 3
        assert first.kernel_manifest_id
        assert first.terrain_cache_hits > 0
        for sample in first.samples:
            assert sample.kernel_manifest_id == first.kernel_manifest_id
            assert sample.sun in tuple(VisibilityStatus)
            assert sample.earth in tuple(VisibilityStatus)
            assert sample.sun_geometric in (VisibilityStatus.VISIBLE, VisibilityStatus.OBSTRUCTED)
        assert first.metrics.sun_unknown_samples == 0
        assert first.metrics.earth_unknown_samples == 0
        assert first.metrics.illuminated_duration_seconds <= 3 * 3600
