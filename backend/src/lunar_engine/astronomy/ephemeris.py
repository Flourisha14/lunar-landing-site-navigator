"""Deterministic SPICE ephemerides with explicit kernel, time, and frame metadata.

SPICE state is process-global: do not concurrently use independent kernel bundles.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import UTC
from math import isfinite
from pathlib import Path
from typing import Any

from lunar_engine.astronomy.kernels import loaded_kernels, read_manifest
from lunar_engine.core.conventions import LunarFrame, MoonFixedVector, parse_utc_timestamp


@dataclass(frozen=True, slots=True)
class EphemerisPosition:
    """Moon-centred target position in km, geometric (no aberration)."""

    body: str
    timestamp_utc: str
    et_seconds: float
    position: MoonFixedVector
    kernel_manifest_id: str
    aberration: str = "NONE"
    origin: str = "MOON"
    distance_unit: str = "km"


def _spice() -> Any:
    """Import SpiceyPy only at execution time (never when importing lunar_engine)."""
    try:
        return importlib.import_module("spiceypy")
    except ImportError as exc:
        raise RuntimeError('SpiceyPy is required; install backend with ".[dev]"') from exc


def canonical_utc(value: str) -> str:
    """Validate strict UTC-Z input and return canonical microsecond ISO UTC."""
    parsed = parse_utc_timestamp(value)
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class EphemerisProvider:
    """Scoped, hash-verified SPICE provider; no implicit downloads or approximations."""

    def __init__(self, lock_file: Path, kernel_directory: Path) -> None:
        self.lock_file = lock_file
        self.kernel_directory = kernel_directory
        self.manifest = read_manifest(lock_file)
        self.kernel_manifest_id: str = self.manifest["id"]
        self._active = False
        self._kernel_context: Any = None

    def __enter__(self) -> EphemerisProvider:
        if self._active:
            raise RuntimeError("Ephemeris provider already active")
        _spice()
        self._kernel_context = loaded_kernels(self.manifest, self.kernel_directory)
        self._kernel_context.__enter__()
        self._active = True
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        try:
            if self._active:
                self._kernel_context.__exit__(exc_type, exc_value, traceback)
        finally:
            self._active = False
            self._kernel_context = None

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("EphemerisProvider must be used inside a with statement")

    def utc_to_et(self, timestamp_utc: str) -> float:
        """Use loaded leap-second kernel for UTC -> TDB-compatible SPICE ET."""
        self._require_active()
        canonical = canonical_utc(timestamp_utc)
        utc_text = canonical.removesuffix("Z").replace("T", " ") + " UTC"
        et: float = float(_spice().str2et(utc_text))
        if not isfinite(et):
            raise ValueError("SPICE returned nonfinite ephemeris time")
        return et

    def et_to_utc(self, et_seconds: float) -> str:
        """Convert ET to UTC at microsecond output precision (not leap-second roundtrip safe)."""
        self._require_active()
        if not isfinite(et_seconds):
            raise ValueError("ET must be finite")
        converted: str = str(_spice().et2utc(et_seconds, "ISOC", 6))
        # SPICE ISOC renders UTC by contract; the suffix is required by public API.
        return canonical_utc(converted + "Z")

    def position(
        self, body: str, timestamp_utc: str, frame: LunarFrame = LunarFrame.ME
    ) -> EphemerisPosition:
        """Geometric position of SUN/EARTH relative to MOON in explicit Moon-fixed frame."""
        self._require_active()
        if body not in {"SUN", "EARTH"}:
            raise ValueError("Supported targets are SUN and EARTH")
        if not isinstance(frame, LunarFrame):
            raise TypeError("frame must be LunarFrame")
        canonical = canonical_utc(timestamp_utc)
        et = self.utc_to_et(canonical)
        # NONE returns geometric positions at simultaneous ET; no light-time correction.
        components, _light_time = _spice().spkpos(body, et, frame.value, "NONE", "MOON")
        position = MoonFixedVector(
            float(components[0]), float(components[1]), float(components[2]), frame
        )
        return EphemerisPosition(body, canonical, et, position, self.kernel_manifest_id)

    def check_epochs(
        self, timestamps_utc: tuple[str, ...], frame: LunarFrame = LunarFrame.ME
    ) -> None:
        """Raise on unsupported sample epochs; does not prove continuous kernel coverage."""
        for instant in timestamps_utc:
            self.position("SUN", instant, frame)
            self.position("EARTH", instant, frame)


def default_provider(repository_root: Path | None = None) -> EphemerisProvider:
    """Use versioned lock and user-downloaded binaries; never fetch automatically."""
    root = repository_root or Path(__file__).resolve().parents[4]
    return EphemerisProvider(root / "data/spice/kernel-lock.json", root / "data/spice/kernels")
