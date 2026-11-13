"""Download named NAIF kernels; record a reviewed lock separately from source manifest.

First acquisition is trust-on-first-use via HTTPS, not independently authenticated.
Review and commit the generated SHA-256 lock ONLY after checking provenance.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "backend" / "src"))
    from lunar_engine.astronomy.kernels import read_manifest, sha256_file

    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=root / "data" / "spice" / "kernels")
    parser.add_argument("--manifest", type=Path, default=root / "data" / "spice" / "kernel-manifest.json")
    parser.add_argument("--lock-output", type=Path, default=root / "data" / "spice" / "kernel-lock.json")
    args = parser.parse_args()
    manifest = read_manifest(args.manifest)
    args.directory.mkdir(parents=True, exist_ok=True)
    for entry in manifest["entries"]:
        filename = entry["filename"]
        if Path(filename).name != filename:
            raise ValueError(f"Invalid filename {filename}")
        target = args.directory / filename
        if not target.exists():
            temp = target.with_suffix(target.suffix + ".part")
            try:
                with urllib.request.urlopen(entry["url"], timeout=120) as response:
                    with temp.open("wb") as dst:
                        while chunk := response.read(1024 * 1024):
                            dst.write(chunk)
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
        actual = sha256_file(target)
        if entry["sha256"] and actual != entry["sha256"].lower():
            raise ValueError(f"Checksum mismatch for {filename}")
        entry["sha256"] = actual
        print(f"{filename}: sha256={actual}")
    # Never silently replace an existing lock. Subsequent runs verify locked hashes.
    if args.lock_output.exists():
        locked = read_manifest(args.lock_output)
        if locked != manifest:
            raise ValueError("Existing lock differs; investigate before changing it")
    else:
        args.lock_output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Created lock: {args.lock_output}. REVIEW before committing.")


if __name__ == "__main__":
    main()
