#!/usr/bin/env python3
"""Build a deterministic release archive from the strict plugin allowlist."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

from validate_repository import ALLOWED_PLUGIN_ROOTS, validate_repo


def release_files(plugin: Path) -> list[Path]:
    files: list[Path] = []
    for path in plugin.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(plugin)
        if relative.parts[0] in ALLOWED_PLUGIN_ROOTS:
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(plugin).as_posix())


def build_archive(repo: Path, output: Path) -> tuple[Path, str, list[str]]:
    validate_repo(repo)
    plugin = repo / "plugins" / "kaoyan-22408"
    files = release_files(plugin)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    names: list[str] = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            name = path.relative_to(plugin).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
            names.append(name)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest, names


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=repo / "dist" / "kaoyan-22408-1.0.0.zip",
        help="发布压缩包路径",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else repo / args.output
    archive, digest, names = build_archive(repo, output)
    print(f"[OK] release: {archive}")
    print(f"[OK] files: {len(names)}")
    print(f"[OK] sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
