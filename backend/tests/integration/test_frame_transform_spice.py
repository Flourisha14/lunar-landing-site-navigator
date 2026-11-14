"""Real-NAIF transformation checks. Explicit skip if extra kernels absent."""

from __future__ import annotations

import os
from math import acos, isclose, sqrt
from pathlib import Path

import pytest

from lunar_engine.coordinates.frame_transform import (
    LunarFrameTransformer,
    analyze_geometry_in_dem_frame,
)
from lunar_engine.core.conventions import LunarFrame, MoonFixedVector

ROOT = Path(__file__).resolve().parents[3]


def _require_assets() -> None:
    for name in (
        "data/spice/de421-frame-lock.json",
        "data/spice/kernels/moon_080317.tf",
        "data/spice/kernels/moon_pa_de421_1900-2050.bpc",
    ):
        if not (ROOT / name).is_file():
            message = f"BUG-001 real-kernel dependency unavailable: {name}"

            if os.environ.get("LUNAR_REQUIRE_FRAME_KERNELS") == "1":
                pytest.fail(message)

            pytest.skip(message)


def _norm(v: MoonFixedVector) -> float:
    return sqrt(v.x_km**2 + v.y_km**2 + v.z_km**2)


def test_de421_de440_matrix_properties() -> None:
    _require_assets()
    at = "2027-11-15T12:00:00Z"
    with LunarFrameTransformer(ROOT) as p:
        matrix = p.matrix(LunarFrame.ME_DE421, LunarFrame.ME, at)
        reverse = p.matrix(LunarFrame.ME, LunarFrame.ME_DE421, at)
        for i in range(3):
            for j in range(3):
                dot = sum(matrix[i][k] * matrix[j][k] for k in range(3))
                assert abs(dot - (1.0 if i == j else 0.0)) < 2e-12
                assert abs(matrix[i][j] - reverse[j][i]) < 2e-12
        a, b, c = matrix
        determinant = (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        )
        assert abs(determinant - 1.0) < 2e-12
        source = MoonFixedVector(10.718, 10.718, -1736.929, LunarFrame.ME_DE421)
        forward = p.transform(source, LunarFrame.ME, at)
        backward = p.transform(forward.vector, LunarFrame.ME_DE421, at)
        assert forward.target_frame == LunarFrame.ME
        assert backward.target_frame == LunarFrame.ME_DE421
        assert abs(_norm(source) - _norm(forward.vector)) < 1e-9
        for original, restored in zip(
            (source.x_km, source.y_km, source.z_km),
            (backward.vector.x_km, backward.vector.y_km, backward.vector.z_km),
            strict=True,
        ):
            assert abs(original - restored) < 1e-9


def test_naif_published_de421_de440_alignment_bound() -> None:
    """Independent NAIF FK comparison: 2000-2040 maximum 3.070984e-7 rad.

    This tests an externally published bound, NOT an independent pointwise
    numerical reference and NOT claimed mission-level accuracy.
    """
    _require_assets()
    with LunarFrameTransformer(ROOT) as p:
        rotation = p.matrix(LunarFrame.ME_DE421, LunarFrame.ME, "2027-11-15T12:00:00Z")
        cosine = max(-1.0, min(1.0, (sum(rotation[i][i] for i in range(3)) - 1.0) / 2))
        assert acos(cosine) <= 3.0709840342771e-7 + 1e-8


def test_geometry_uses_dem_frame() -> None:
    _require_assets()
    result = analyze_geometry_in_dem_frame(
        -89.5,
        45.0,
        "2027-11-15T12:00:00Z",
        terrain_elevation_km=-0.40532254028320314,
        repository_root=ROOT,
    )
    assert result.frame == LunarFrame.ME_DE421
    assert result.site.frame == result.sun.position_moon_fixed.frame
    assert result.site.frame == result.earth.position_moon_fixed.frame
    assert isclose(
        result.sun.east_unit**2 + result.sun.north_unit**2 + result.sun.up_unit**2,
        1.0,
        abs_tol=1e-12,
    )


def test_epoch_dependence_and_coverage_boundary() -> None:
    _require_assets()
    with LunarFrameTransformer(ROOT) as p:
        first = p.matrix(LunarFrame.ME_DE421, LunarFrame.ME, "2026-11-15T12:00:00Z")
        second = p.matrix(LunarFrame.ME_DE421, LunarFrame.ME, "2027-11-15T12:00:00Z")
        assert any(abs(first[i][j] - second[i][j]) > 1e-13 for i in range(3) for j in range(3))
        with pytest.raises(Exception, match="SPICE|coverage|PCK|pck|time|TIME"):
            p.matrix(LunarFrame.ME_DE421, LunarFrame.ME, "2100-11-15T12:00:00Z")


def test_unsupported_frame_and_inactive_context() -> None:
    _require_assets()
    transformer = LunarFrameTransformer(ROOT)
    with pytest.raises(RuntimeError):
        transformer.matrix(LunarFrame.ME, LunarFrame.ME_DE421, "2027-11-15T12:00:00Z")
    with transformer as active:
        with pytest.raises(ValueError):
            active.matrix(LunarFrame.IAU, LunarFrame.ME, "2027-11-15T12:00:00Z")
