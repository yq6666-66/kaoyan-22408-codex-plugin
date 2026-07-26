#!/usr/bin/env python3
"""Run the forward evaluator from immutable Git blobs before importing it.

This entrypoint intentionally uses only the Python standard library.  It
materializes the committed evaluator tree with ``git cat-file`` and executes
that copy in a fresh module namespace, while the evaluator's output and Git
checks continue to point at the original checkout.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
import runpy


PREFIXES = ("plugins/kaoyan-22408", "tests/forward-cases.json", "tests/behavior-cases.json", "evals")


def _run(command: list[str], *, cwd: Path, capture: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _snapshot(repo: Path, revision: str, destination: Path) -> None:
    listing = _run(["git", "ls-tree", "-r", "-z", revision, "--", *PREFIXES], cwd=repo)
    if listing.returncode != 0:
        raise RuntimeError(listing.stderr.decode("utf-8", "replace").strip())
    entries = [item for item in listing.stdout.split(b"\0") if item]
    if not entries:
        raise RuntimeError("Git blob snapshot is empty")
    for entry in entries:
        metadata, raw_path = entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        relative = PurePosixPath(raw_path.decode("utf-8"))
        if (
            object_type != "blob"
            or mode not in {"100644", "100755"}
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise RuntimeError(f"unsupported Git snapshot entry: {relative}")
        blob = _run(["git", "cat-file", "blob", object_id], cwd=repo)
        if blob.returncode != 0:
            raise RuntimeError(blob.stderr.decode("utf-8", "replace").strip())
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob.stdout)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    revision_result = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    if revision_result.returncode != 0:
        raise RuntimeError("cannot resolve the evaluator source revision")
    revision = revision_result.stdout.decode("ascii").strip()
    with tempfile.TemporaryDirectory(prefix="kaoyan-22408-trusted-eval-") as temporary:
        snapshot = Path(temporary) / "input-snapshot"
        _snapshot(repo, revision, snapshot)
        # The snapshot module must resolve all shared paths back to the clean
        # checkout so it can perform Git cleanliness and TOCTOU checks.
        os.environ["K22408_FORWARD_EVAL_REPO"] = str(repo)
        evals_path = str(snapshot / "evals")
        sys.path.insert(0, evals_path)
        try:
            runpy.run_path(evals_path + "/run_forward_eval.py", run_name="__main__")
        except SystemExit as exc:
            return int(exc.code or 0)
        finally:
            if sys.path and sys.path[0] == evals_path:
                sys.path.pop(0)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
