#!/usr/bin/env python3
"""Run repository tests, Semgrep, and official-validator release gates."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def pinned_requirement_version(requirements: Path, package: str) -> str:
    prefix = package.casefold() + "=="
    for raw_line in requirements.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.casefold().startswith(prefix):
            return line.split("==", 1)[1].strip()
    raise RuntimeError(f"{package} must be exactly pinned in {requirements}")


def verify_semgrep_version(executable: str, expected: str, cwd: Path, env: dict[str, str]) -> None:
    result = subprocess.run(
        [executable, "--version"],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"(?m)^\s*(?:semgrep\s+)?(\d+\.\d+\.\d+)\s*$", output)
    if result.returncode != 0 or match is None:
        raise RuntimeError(f"cannot determine Semgrep version: {output.strip()}")
    actual = match.group(1)
    if actual != expected:
        raise RuntimeError(
            f"Semgrep version mismatch: expected {expected} from requirements-dev.txt, found {actual}"
        )


def verify_python_dependency_versions(requirements: Path, packages: tuple[str, ...]) -> None:
    for package in packages:
        expected = pinned_requirement_version(requirements, package)
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"required development dependency is missing: {package}") from exc
        if actual != expected:
            raise RuntimeError(
                f"{package} version mismatch: expected {expected} from requirements-dev.txt, found {actual}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    validators = parser.add_mutually_exclusive_group()
    validators.add_argument("--skip-system-validators", action="store_true")
    validators.add_argument("--verify-system-evidence", action="store_true")
    parser.add_argument(
        "--system-evidence",
        type=Path,
        default=Path("tests/system-validator-evidence.json"),
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    evidence = args.system_evidence if args.system_evidence.is_absolute() else repo / args.system_evidence
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    requirements = repo / "requirements-dev.txt"
    try:
        verify_python_dependency_versions(requirements, ("PyYAML", "jsonschema"))
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    run([sys.executable, "scripts/validate_repository.py"], repo, env)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"], repo, env)

    semgrep = shutil.which("semgrep")
    if os.name == "nt":
        print("[SKIP] Semgrep on Windows; pinned Linux CI is the authoritative Semgrep gate")
    elif semgrep:
        env.setdefault(
            "SEMGREP_SETTINGS_FILE",
            str(Path(tempfile.gettempdir()) / "kaoyan-22408-semgrep-settings.yml"),
        )
        env.setdefault("SEMGREP_SEND_METRICS", "off")
        expected_semgrep = pinned_requirement_version(requirements, "semgrep")
        try:
            verify_semgrep_version(semgrep, expected_semgrep, repo, env)
        except RuntimeError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        run(
            [
                semgrep,
                "scan",
                "--config",
                ".semgrep.yml",
                "--error",
                "--metrics=off",
                "--no-git-ignore",
                "--exclude",
                ".git",
                "--exclude",
                ".venv",
                "--exclude",
                "venv",
                "--exclude",
                "__pycache__",
                "--exclude",
                ".pytest_cache",
                "--exclude",
                ".cache",
                "--exclude",
                ".codex-security",
                "--exclude",
                "dist",
                ".",
            ],
            repo,
            env,
        )
    else:
        print("[FAIL] Semgrep is required; install the pinned requirements-dev.txt", file=sys.stderr)
        return 1

    if args.skip_system_validators:
        print("[SKIP] official validators (development-only override)")
    elif args.verify_system_evidence:
        run(
            [
                sys.executable,
                "scripts/run_system_validators.py",
                "--verify-evidence",
                str(evidence),
            ],
            repo,
            env,
        )
    else:
        run(
            [
                sys.executable,
                "scripts/run_system_validators.py",
                "--write",
                str(evidence),
            ],
            repo,
            env,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
