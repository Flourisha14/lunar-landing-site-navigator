"""BE-011/BE-012 real NASA LOLA + verified DE421/DE440 SPICE integration.

CI normally skips because the large LOLA raster is not part of the repository.
Set LUNAR_REQUIRE_REAL_VISIBILITY=1 to require this test rather than skip.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from lunar_engine.analysis.visibility import VisibilityStatus, evaluate_terrain_visibility
from lunar_engine.core.conventions import LunarFrame
from lunar_engine.terrain.dem import DEFAULT_LOLA_METADATA, LunarDEM

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.integration
@pytest.mark.requires_dem
@pytest.mark.requires_spice
def test_real_lola_sun_earth_visibility() -> None:
    raw = os.environ.get("LUNAR_DEM_FILE")
    available = (
        bool(raw)
        and Path(raw).is_file()
        and os.environ.get("LUNAR_DEM_DATUM_CONFIRMED") == "1"
        and (ROOT / "data/spice/kernel-lock.json").is_file()
        and (ROOT / "data/spice/de421-frame-lock.json").is_file()
    )
    if not available:
        message = "Verified LOLA DEM + DE421/DE440 kernel locks required"
        if os.environ.get("LUNAR_REQUIRE_REAL_VISIBILITY") == "1":
            pytest.fail(message)
        pytest.skip(message)
    assert raw is not None
    path = Path(raw)
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    metadata = replace(DEFAULT_LOLA_METADATA, datum_confirmed=True)
    with LunarDEM(path, metadata=metadata) as dem:
        kwargs = dict(
            dem=dem,
            latitude_deg=-89.5,
            longitude_deg=45.0,
            timestamp_utc="2027-11-15T12:00:00Z",
            observer_height_m=2.0,
            max_distance_km=2.0,
            step_m=80.0,
            interpolation="bilinear",
            repository_root=ROOT,
        )
        result = evaluate_terrain_visibility(**kwargs)
        again = evaluate_terrain_visibility(**kwargs)
        assert result == again
        assert result.frame is LunarFrame.ME_DE421
        assert result.terrain_dataset_id == metadata.dataset_id
        assert result.ephemeris_aberration == "NONE"
        assert result.observer_height_m == 2.0
        # Known NASA LOLA demonstration location:
        # both directions have complete 2 km DEM coverage.
        assert result.sun.status is not VisibilityStatus.UNKNOWN
        assert result.earth.status is not VisibilityStatus.UNKNOWN

        for body in (result.sun, result.earth):
            assert body.horizon is not None
            assert body.horizon.complete
            assert body.horizon.coverage == "complete"
            assert body.terrain_horizon_deg is not None
            assert body.clearance_deg is not None
            assert -90.0 <= body.elevation_deg <= 90.0
            assert body.status in tuple(VisibilityStatus)
            if body.status is VisibilityStatus.UNKNOWN:
                assert body.visible is None
            else:
                assert body.visible is not None
                assert body.horizon is not None and body.horizon.complete
                assert body.clearance_deg is not None
                expected = (
                    VisibilityStatus.VISIBLE
                    if body.clearance_deg > 0
                    else VisibilityStatus.OBSTRUCTED
                )
                assert body.status is expected

        # QA: Increasing terrain search distance with an identical
        # sampling grid must not decrease maximum obstruction.
        results_by_distance = []

        for search_distance in (2.0, 5.0, 10.0):
            distance_kwargs = {
                **kwargs,
                "max_distance_km": search_distance,
            }

            distance_result = evaluate_terrain_visibility(**distance_kwargs)

            results_by_distance.append(distance_result)

        for body_name in ("sun", "earth"):
            body_results = [getattr(item, body_name) for item in results_by_distance]

            assert all(body.status is not VisibilityStatus.UNKNOWN for body in body_results)

            assert all(body.horizon is not None and body.horizon.complete for body in body_results)

            clearances = [body.clearance_deg for body in body_results]

            assert all(value is not None for value in clearances)

            assert clearances[0] >= clearances[1] - 1e-9
            assert clearances[1] >= clearances[2] - 1e-9
    assert (path.stat().st_size, path.stat().st_mtime_ns) == before
