"""Golden positions calculated analytically, stored separately from production code."""

import json
from pathlib import Path

import pytest

from lunar_engine.coordinates.spherical import enu_basis, geographic_to_cartesian
from lunar_engine.core.conventions import LunarLocation


@pytest.mark.scientific
def test_analytical_reference_points() -> None:
    data = json.loads(
        Path(__file__).with_name("coordinate_golden.json").read_text(encoding="utf-8")
    )
    for case in data["cases"]:
        site = LunarLocation(case["latitude_deg"], case["longitude_deg"], case["elevation_km"])
        got = geographic_to_cartesian(site)
        assert (got.x_km, got.y_km, got.z_km) == pytest.approx(
            case["xyz_km"], abs=data["position_absolute_tolerance_km"], rel=0
        ), case["name"]


@pytest.mark.scientific
def test_analytical_enu_at_prime_meridian() -> None:
    data = json.loads(
        Path(__file__).with_name("coordinate_golden.json").read_text(encoding="utf-8")
    )
    ref = data["enu_reference"]
    axes = enu_basis(LunarLocation(ref["site_latitude_deg"], ref["site_longitude_deg"], 0))
    for axis, label in zip(axes, ("east", "north", "up"), strict=True):
        assert axis == pytest.approx(ref[label], abs=1e-14)
