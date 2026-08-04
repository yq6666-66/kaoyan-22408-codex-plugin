#!/usr/bin/env python3
"""Require Windows and Ubuntu release artifacts to be byte-identical."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def release_pair(directory: Path) -> tuple[Path, Path, str]:
    archives = list(directory.rglob("kaoyan-408-*.zip"))
    if len(archives) != 1:
        raise ValueError(f"expected one ZIP below {directory}, found {len(archives)}")
    archive = archives[0]
    checksum = archive.with_name(archive.name + ".sha256")
    if not checksum.is_file():
        raise ValueError(f"missing checksum for {archive}")
    line = checksum.read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"([0-9a-f]{64})\s{2}(.+)", line)
    if not match or match.group(2) != archive.name:
        raise ValueError(f"invalid checksum file: {checksum}")
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != match.group(1):
        raise ValueError(f"checksum mismatch: {archive}")
    return archive, checksum, actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ubuntu", type=Path)
    parser.add_argument("windows", type=Path)
    args = parser.parse_args()
    ubuntu_archive, _, ubuntu_hash = release_pair(args.ubuntu)
    windows_archive, _, windows_hash = release_pair(args.windows)
    if ubuntu_archive.name != windows_archive.name:
        raise SystemExit("Windows and Ubuntu archive names differ")
    if ubuntu_hash != windows_hash:
        raise SystemExit(f"release archives differ: ubuntu={ubuntu_hash} windows={windows_hash}")
    print(f"[OK] reproducible archive: {ubuntu_archive.name}")
    print(f"[OK] sha256: {ubuntu_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
