"""Acquire legacy NAIF DE421 lunar orientation kernels and lock local hashes.

Run from repository root. Requires no dependency except Python stdlib.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

KERNELS = (
    (
        "moon_pa_de421_1900-2050.bpc",
        "PCK",
        "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de421_1900-2050.bpc",
    ),
    (
        "moon_080317.tf",
        "FK",
        "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_080317.tf",
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    directory = root / "data" / "spice" / "kernels"
    directory.mkdir(parents=True, exist_ok=True)
    entries = []
    for filename, kind, url in KERNELS:
        destination = directory / filename
        if not destination.is_file():
            partial = directory / (filename + ".part")
            print("Downloading", url, flush=True)
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            partial.replace(destination)
        digest = sha256(destination)
        print(f"VERIFIED LOCAL HASH: {filename}: {digest}")
        entries.append(
            {
                "filename": filename,
                "url": url,
                "kind": kind,
                "sha256": digest,
                "coverage_note": "DE421 lunar orientation source; verify ET against binary PCK",
            }
        )
    manifest = {"id": "de421-lunar-frame-2026-v1", "entries": entries}
    lock = root / "data" / "spice" / "de421-frame-lock.json"
    if lock.exists():
        previous = json.loads(lock.read_text(encoding="utf-8"))
        if previous != manifest:
            raise ValueError("Existing DE421 lock differs; refusing to overwrite pinned hashes")
        print("Existing lock matches downloaded files:", lock)
        return
    lock.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Created:", lock)
    print("IMPORTANT: hashes above are locally recorded, not publisher-signed hashes.")


if __name__ == "__main__":
    main()
