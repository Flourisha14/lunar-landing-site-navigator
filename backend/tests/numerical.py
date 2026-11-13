"""Shared test-only floating point comparison rules."""

from math import isclose, isfinite

DEFAULT_REL_TOL = 1e-12
DEFAULT_ABS_TOL = 1e-9


def numerically_close(
    actual: float,
    expected: float,
    *,
    rel_tol: float = DEFAULT_REL_TOL,
    abs_tol: float = DEFAULT_ABS_TOL,
) -> bool:
    """Reject non-finite values; caller specifies units for absolute tolerance."""
    if not all(isfinite(x) for x in (actual, expected, rel_tol, abs_tol)):
        return False
    if rel_tol < 0 or abs_tol < 0:
        raise ValueError("Tolerances must be nonnegative")
    return isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol)
