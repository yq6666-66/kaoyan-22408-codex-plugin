#!/usr/bin/env python3
"""Expose manifest-derived release metadata to local and GitHub workflows."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "plugins" / "kaoyan-408" / ".codex-plugin" / "plugin.json"


def metadata(suffix: str | None = None) -> dict[str, str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    version = manifest["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError(f"manifest version is not release semver: {version}")
    archive = f"kaoyan-408-{version}.zip"
    result = {
        "version": version,
        "tag": f"v{version}",
        "archive": archive,
        "checksum": f"{archive}.sha256",
        "artifact": f"kaoyan-408-{version}" + (f"-{suffix}" if suffix else ""),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-suffix")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--expect-tag")
    args = parser.parse_args()
    values = metadata(args.artifact_suffix)
    if args.expect_tag and args.expect_tag != values["tag"]:
        raise SystemExit(f"tag {args.expect_tag!r} does not match manifest {values['tag']!r}")
    payload = "".join(f"{key}={value}\n" for key, value in values.items())
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    print(json.dumps(values, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
