"""Fetch the complete matching Qt/PySide sources as separate release assets.

Pins were checked against the official .sha256 and .meta4 endpoints. Source
archives are never executed or unpacked by this downloader.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 1_500_000_000


def source_index(root: Path = ROOT) -> dict:
    index = json.loads((root / "packaging/source-archives.json").read_text(encoding="utf-8"))
    lock = (root / "requirements-build-lock.txt").read_text(encoding="utf-8")
    for name in ("PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6"):
        if not re.search(rf"(?mi)^{re.escape(name)}=={re.escape(index['qt_version'])}$", lock):
            raise ValueError("Qt source pins do not match the dependency lock")
    for item in index["archives"]:
        if (Path(item["name"]).name != item["name"] or "/" in item["name"] or "\\" in item["name"]
                or not item["url"].startswith(("https://download.qt.io/official_releases/",
                    "https://codeload.github.com/AppImage/type2-runtime/",
                    "https://codeload.github.com/vasi/squashfuse/",
                    "https://github.com/libfuse/libfuse/releases/download/"))
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                or not 0 < item["size"] <= MAX_SOURCE_BYTES):
            raise ValueError("Invalid source archive pin")
    return index


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(item: dict, destination: Path) -> Path:
    target = destination / item["name"]
    if target.is_symlink():
        raise ValueError("Refusing symlink source target")
    if target.is_file() and target.stat().st_size == item["size"] and digest(target) == item["sha256"]:
        return target
    destination.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        request = urllib.request.Request(item["url"], headers={"User-Agent": "Steady-State-Studio-source-mirror"})
        with urllib.request.urlopen(request, timeout=120) as response:
            if not response.geturl().startswith("https://"):
                raise RuntimeError("Refusing insecure source redirect")
            with tempfile.NamedTemporaryFile(dir=destination, suffix=".download", delete=False) as stream:
                temporary = Path(stream.name)
                count = 0
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > item["size"]:
                        raise RuntimeError("Source exceeds pinned size")
                    stream.write(chunk)
        if temporary.stat().st_size != item["size"] or digest(temporary) != item["sha256"]:
            raise RuntimeError("Source checksum mismatch; review upstream before changing pins")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/release-sources")
    args = parser.parse_args(argv)
    index = source_index()
    for item in index["archives"]:
        download(item, args.output_dir)
        print(f"Verified {item['name']}")
    (args.output_dir / "SOURCE-INDEX.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
