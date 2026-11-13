"""Manifest-driven, hash-verified NASA SPICE kernel loading.

Importing this module does not require SpiceyPy. Load only after installing
scientific extras and verifying the local manifest and binaries.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict


class KernelEntry(TypedDict):
    filename: str
    url: str
    kind: str
    sha256: str | None
    coverage_note: str


class KernelManifest(TypedDict):
    id: str
    entries: list[KernelEntry]


def read_manifest(path: Path) -> KernelManifest:
    """Read an explicit manifest; no network operations."""
    manifest: KernelManifest = json.loads(path.read_text(encoding="utf-8"))
    return manifest


def sha256_file(path: Path) -> str:
    """Stream SHA-256 without storing large binary kernels in RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_kernels(manifest: KernelManifest, directory: Path) -> list[Path]:
    """Fail closed if a checksum is not locked or does not match."""
    paths: list[Path] = []
    for entry in manifest["entries"]:
        filename = entry["filename"]
        if Path(filename).name != filename:
            raise ValueError("Kernel filename must be a basename")
        expected = entry["sha256"]
        if not expected or len(expected) != 64:
            raise ValueError(f"SHA-256 not yet pinned for {filename}")
        path = directory / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256_file(path) != expected.lower():
            raise ValueError(f"SHA-256 mismatch: {filename}")
        paths.append(path)
    return paths


@contextmanager
def loaded_kernels(manifest: KernelManifest, directory: Path) -> Iterator[None]:
    """Load verified kernels; unload only files loaded by this context.

    CSPICE's kernel pool is process-global. Avoid concurrently managing kernels.
    """
    spice = importlib.import_module("spiceypy")  # optional dependency; intentionally lazy

    paths = verify_kernels(manifest, directory)
    loaded: list[Path] = []
    try:
        for path in paths:
            spice.furnsh(str(path))
            loaded.append(path)
        yield
    finally:
        for path in reversed(loaded):
            spice.unload(str(path))


def verify_spice_coverage(manifest: KernelManifest, directory: Path) -> dict[str, str]:
    """Check selected simulation epochs and DE440 frame availability."""
    spice = importlib.import_module("spiceypy")

    with loaded_kernels(manifest, directory):
        epochs = [spice.str2et(x) for x in ("2026-11-14T00:00:00", "2027-11-14T00:00:00")]
        for epoch in epochs:
            # BOTH target and observer resolve from the SPK at each requested epoch.
            for target in ("SUN", "EARTH"):
                spice.spkpos(target, epoch, "J2000", "NONE", "MOON")
            spice.pxform("J2000", "MOON_ME_DE440_ME421", epoch)
            spice.pxform("J2000", "MOON_PA_DE440", epoch)
        return {"epochs_utc": "2026-11-14 to 2027-11-14", "frames": "ME and PA resolved"}
