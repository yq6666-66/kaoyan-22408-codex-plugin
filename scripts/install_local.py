#!/usr/bin/env python3
"""Validate and install the local repository marketplace when Codex supports plugins."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, TextIO


PLUGIN_NAME = "kaoyan-22408"
MARKETPLACE_NAME = "kaoyan-22408"
Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def _relay(result: subprocess.CompletedProcess[str], stream: TextIO) -> None:
    if result.stdout:
        print(result.stdout.rstrip(), file=stream)
    if result.stderr:
        print(result.stderr.rstrip(), file=stream)


def _marketplace_present(output: str) -> bool:
    return re.search(
        rf"(?m)(?:^|[\s\"']){re.escape(MARKETPLACE_NAME)}(?:$|[\s\"'])",
        output,
    ) is not None


def _normalized_path_text(value: str) -> str:
    normalized = value.casefold().replace("\\", "/")
    return re.sub(r"/+", "/", normalized).rstrip("/")


def _marketplace_points_to_repo(output: str, repo: Path) -> bool:
    expected = _normalized_path_text(str(repo.resolve()))
    return expected in _normalized_path_text(output)


def install_local(
    repo: Path,
    *,
    validate_only: bool = False,
    runner: Runner = run_command,
    which: Which = shutil.which,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Return 0 for success, 1 for failure, and 2 for an unsupported host."""

    repo = repo.resolve()
    validation = runner(
        [
            sys.executable,
            str(repo / "scripts" / "check.py"),
            "--verify-system-evidence",
        ],
        repo,
    )
    _relay(validation, stdout if validation.returncode == 0 else stderr)
    if validation.returncode != 0:
        print("Validation failed; installation was not attempted.", file=stderr)
        return 1
    if validate_only:
        print("Validation completed.", file=stdout)
        return 0

    codex = which("codex")
    if not codex:
        print(
            "This Codex CLI cannot install plugins. Restart ChatGPT/Codex Desktop and install "
            "kaoyan-22408 from this repository marketplace.",
            file=stderr,
        )
        return 2

    plugin_help = runner([codex, "plugin", "--help"], repo)
    help_text = f"{plugin_help.stdout}\n{plugin_help.stderr}".lower()
    if plugin_help.returncode != 0 or "plugin" not in help_text:
        print(
            "This Codex CLI has no usable plugin subcommand. Restart ChatGPT/Codex Desktop and "
            "install kaoyan-22408 from this repository marketplace.",
            file=stderr,
        )
        return 2

    marketplaces = runner([codex, "plugin", "marketplace", "list"], repo)
    if marketplaces.returncode != 0:
        _relay(marketplaces, stderr)
        print("Unable to list Codex marketplaces.", file=stderr)
        return 1

    marketplace_output = f"{marketplaces.stdout}\n{marketplaces.stderr}"
    if _marketplace_present(marketplace_output):
        if not _marketplace_points_to_repo(marketplace_output, repo):
            print(
                "A marketplace named kaoyan-22408 already exists, but its source cannot be verified "
                "as this repository. Refusing to install from an ambiguous source.",
                file=stderr,
            )
            return 1
    else:
        add_marketplace = runner(
            [codex, "plugin", "marketplace", "add", str(repo)],
            repo,
        )
        if add_marketplace.returncode != 0:
            _relay(add_marketplace, stderr)
            print("Unable to add the local repository marketplace.", file=stderr)
            return 1

    install = runner(
        [codex, "plugin", "add", f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"],
        repo,
    )
    if install.returncode != 0:
        _relay(install, stderr)
        print("Unable to install the local plugin.", file=stderr)
        return 1

    print(f"Installed {PLUGIN_NAME}. Start a new task before testing the Skills.", file=stdout)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    return install_local(repo, validate_only=args.validate_only)


if __name__ == "__main__":
    raise SystemExit(main())
