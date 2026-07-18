from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def run_git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def copy_as_committed_repo(destination: Path) -> Path:
    ignored = shutil.ignore_patterns(
        ".git",
        "dist",
        "__pycache__",
        ".pytest_cache",
        ".codex-security",
        "*.pyc",
        # Generated release evidence belongs to the real repository history.
        # Tests that exercise evidence create their own isolated bundle; copying
        # the production bundle would retain its signature and source revision.
        "forward-eval-evidence.json",
        "forward-eval-response-manifest.json",
        "forward-eval-attestation.json",
        "forward-eval-attestation.json.sig",
    )
    shutil.copytree(REPO, destination, ignore=ignored)
    submission = destination / "submission"
    if submission.exists() and not any(submission.rglob("*")):
        submission.rmdir()
    run_git(destination, "init", "-b", "main")
    run_git(destination, "config", "user.name", "Test Runner")
    run_git(destination, "config", "user.email", "tests@example.invalid")
    run_git(destination, "config", "core.autocrlf", "false")
    run_git(destination, "add", "--all")
    run_git(destination, "commit", "-m", "test fixture")
    return destination


def commit_all(repo: Path, message: str = "mutation") -> None:
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", message)
