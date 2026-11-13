"""Smoke tests for the lunar_engine package."""

import lunar_engine


def test_package_version() -> None:
    """Verify the scientific backend package exposes its expected version."""
    assert lunar_engine.__version__ == "0.1.0"


def test_package_name() -> None:
    """Verify that the backend can be imported independently."""
    assert lunar_engine.__name__ == "lunar_engine"
