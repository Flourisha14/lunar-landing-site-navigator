"""Epoch-dependent, explicit lunar frame conversion using NAIF SPICE.

DE421 and DE440 lunar mean-Earth frames have the same NAIF center (301).
This module NEVER approximates missing kernels or silently changes frames.
The SPICE kernel pool is process-global: do not use concurrently with other
independent SPICE kernel managers.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Literal

from lunar_engine.astronomy.ephemeris import canonical_utc
from lunar_engine.astronomy.kernels import loaded_kernels, read_manifest
from lunar_engine.core.conventions import LunarFrame, MoonFixedVector

SUPPORTED = frozenset({LunarFrame.ME, LunarFrame.ME_DE421})


@dataclass(frozen=True, slots=True)
class FrameTransformResult:
    vector: MoonFixedVector
    source_frame: LunarFrame
    target_frame: LunarFrame
    timestamp_utc: str
    et_seconds: float
    vector_kind: Literal["position", "direction"]
    origin: str
    distance_unit: str
    kernel_bundle_ids: tuple[str, str]
    method: str = "SPICE pxform, same-center Moon rotation"


def rotate_components(
    rotation: Sequence[Sequence[float]], vector: Sequence[float]
) -> tuple[float, float, float]:
    """Pure numerical matrix-vector product; accepts SPICE's 3x3 matrix."""
    if len(vector) != 3 or len(rotation) != 3 or any(len(row) != 3 for row in rotation):
        raise ValueError("Expected a 3x3 rotation and a three-component vector")
    if not all(isfinite(float(v)) for row in rotation for v in row) or not all(
        isfinite(float(v)) for v in vector
    ):
        raise ValueError("Nonfinite rotation or vector")
    return (
        sum(float(rotation[0][j]) * float(vector[j]) for j in range(3)),
        sum(float(rotation[1][j]) * float(vector[j]) for j in range(3)),
        sum(float(rotation[2][j]) * float(vector[j]) for j in range(3)),
    )


class LunarFrameTransformer:
    """Load checksum-verified DE421 and DE440 kernels in a scoped context."""

    def __init__(self, repository_root: Path) -> None:
        self.root = Path(repository_root)
        self.directory = self.root / "data" / "spice" / "kernels"
        self.de421_manifest = read_manifest(self.root / "data" / "spice" / "de421-frame-lock.json")
        self.de440_manifest = read_manifest(self.root / "data" / "spice" / "kernel-lock.json")
        self._stack: ExitStack | None = None
        self._spice: Any = None

    def __enter__(self) -> LunarFrameTransformer:
        if self._stack is not None:
            raise RuntimeError("Frame transformer already active")
        spice = importlib.import_module("spiceypy")
        stack = ExitStack()
        try:
            # Load historical FK first. Current FK loaded second ensures generic
            # MOON_ME/MOON_PA aliases retain the DE440 definitions. We use only
            # explicit frame identifiers in this adapter.
            stack.enter_context(loaded_kernels(self.de421_manifest, self.directory))
            stack.enter_context(loaded_kernels(self.de440_manifest, self.directory))
            for frame, expected_id in ((LunarFrame.ME_DE421, 31007), (LunarFrame.ME, 31009)):
                actual_id = int(spice.namfrm(frame.value))
                if actual_id != expected_id:
                    raise ValueError(f"Unexpected NAIF frame ID {frame.value}: {actual_id}")

                center, _frame_class, _class_id = spice.frinfo(actual_id)

                if center != 301:
                    raise ValueError(
                        f"Frame {frame.value} must be Moon-centered "
                        f"(NAIF 301); received center {center}"
                    )
            self._spice = spice
            self._stack = stack
        except BaseException:
            stack.close()
            raise
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        try:
            if self._stack is not None:
                self._stack.close()
        finally:
            self._stack = None
            self._spice = None

    def matrix(
        self, source: LunarFrame, target: LunarFrame, timestamp_utc: str
    ) -> tuple[tuple[float, ...], ...]:
        if self._stack is None:
            raise RuntimeError("Use LunarFrameTransformer within a with statement")
        if not isinstance(source, LunarFrame) or not isinstance(target, LunarFrame):
            raise TypeError("Source and destination must be explicit LunarFrame values")
        if source not in SUPPORTED or target not in SUPPORTED:
            raise ValueError("Only explicitly supported lunar ME realizations are permitted")
        canonical = canonical_utc(timestamp_utc)
        utc_text = canonical.removesuffix("Z").replace("T", " ") + " UTC"
        et = float(self._spice.str2et(utc_text))
        result = self._spice.pxform(source.value, target.value, et)
        return tuple(tuple(float(result[i][j]) for j in range(3)) for i in range(3))

    def transform(
        self,
        vector: MoonFixedVector,
        target: LunarFrame,
        timestamp_utc: str,
        *,
        kind: Literal["position", "direction"] = "position",
    ) -> FrameTransformResult:
        if kind not in {"position", "direction"}:
            raise ValueError("Unsupported vector kind")
        if vector.frame not in SUPPORTED or target not in SUPPORTED:
            raise ValueError("Unknown or unsupported lunar frame")
        if self._stack is None:
            raise RuntimeError("Use LunarFrameTransformer within a with statement")
        canonical = canonical_utc(timestamp_utc)
        et = float(self._spice.str2et(canonical.removesuffix("Z").replace("T", " ") + " UTC"))
        # Same-origin guarantee checked in __enter__. A free direction cannot
        # be translated; a Moon-centered position needs rotation only.
        matrix = self._spice.pxform(vector.frame.value, target.value, et)
        xyz = rotate_components(matrix, (vector.x_km, vector.y_km, vector.z_km))
        return FrameTransformResult(
            vector=MoonFixedVector(xyz[0], xyz[1], xyz[2], target),
            source_frame=vector.frame,
            target_frame=target,
            timestamp_utc=canonical,
            et_seconds=et,
            vector_kind=kind,
            origin="MOON (NAIF 301)",
            distance_unit="km" if kind == "position" else "input vector units",
            kernel_bundle_ids=(self.de421_manifest["id"], self.de440_manifest["id"]),
        )


def transform_lunar_vector(
    vector: MoonFixedVector,
    target_frame: LunarFrame,
    timestamp_utc: str,
    *,
    repository_root: Path,
    kind: Literal["position", "direction"] = "position",
) -> FrameTransformResult:
    """Convenience wrapper. For many vectors, reuse a single transformer context."""
    with LunarFrameTransformer(repository_root) as transformer:
        return transformer.transform(vector, target_frame, timestamp_utc, kind=kind)


def analyze_geometry_in_dem_frame(
    latitude_deg: float,
    longitude_deg: float,
    timestamp_utc: str,
    *,
    terrain_elevation_km: float,
    repository_root: Path,
) -> Any:
    """Geometric Sun/Earth directions in the DEM's *DE421* lunar ME frame.

    Returned horizon model remains spherical; this does not calculate terrain
    obstruction. The caller must use independently validated terrain data.
    """
    from lunar_engine.astronomy.ephemeris import EphemerisPosition
    from lunar_engine.astronomy.geometry import CelestialGeometry, local_direction
    from lunar_engine.core.conventions import LunarLocation

    site = LunarLocation(latitude_deg, longitude_deg, terrain_elevation_km, LunarFrame.ME_DE421)
    with LunarFrameTransformer(repository_root) as transformer:
        spice = transformer._spice
        canonical = canonical_utc(timestamp_utc)
        et = float(spice.str2et(canonical.removesuffix("Z").replace("T", " ") + " UTC"))
        results = {}
        for body in ("SUN", "EARTH"):
            components, _ = spice.spkpos(body, et, LunarFrame.ME.value, "NONE", "MOON")
            original = MoonFixedVector(
                float(components[0]), float(components[1]), float(components[2]), LunarFrame.ME
            )
            converted = transformer.transform(original, LunarFrame.ME_DE421, canonical)
            position = EphemerisPosition(
                body, canonical, et, converted.vector, transformer.de440_manifest["id"]
            )
            results[body] = local_direction(position, site)
        return CelestialGeometry(
            site=site,
            timestamp_utc=canonical,
            et_seconds=et,
            frame=LunarFrame.ME_DE421,
            kernel_manifest_id=(
                transformer.de421_manifest["id"] + "+" + transformer.de440_manifest["id"]
            ),
            sun=results["SUN"],
            earth=results["EARTH"],
        )
