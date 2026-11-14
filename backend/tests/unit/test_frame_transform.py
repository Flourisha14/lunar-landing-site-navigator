"""Kernel-independent checks for the frame transformation's arithmetic contract."""

import pytest

from lunar_engine.coordinates.frame_transform import rotate_components
from lunar_engine.core.conventions import LunarFrame, LunarLocation


def test_identity_rotation() -> None:
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert rotate_components(identity, (1.0, -2.0, 3.0)) == (1.0, -2.0, 3.0)


def test_known_quarter_turn() -> None:
    rotation = ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert rotate_components(rotation, (1.0, 0.0, 0.0)) == (0.0, 1.0, 0.0)


def test_invalid_matrix_rejected() -> None:
    with pytest.raises(ValueError):
        rotate_components(((1.0,),), (1.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        rotate_components(((1.0, 0.0, 0.0),) * 3, (float("nan"), 0.0, 0.0))


def test_dem_frame_is_distinct_from_de440() -> None:
    assert LunarFrame.ME_DE421.value == "MOON_ME_DE421"
    assert LunarFrame.ME_DE421 != LunarFrame.ME
    site = LunarLocation(-89.5, 45.0, 0.0, LunarFrame.ME_DE421)
    assert site.frame == LunarFrame.ME_DE421
