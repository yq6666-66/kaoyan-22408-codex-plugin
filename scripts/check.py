#!/usr/bin/env python3
"""Run repository tests and any locally available official validators."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-system-validators", action="store_true")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    plugin = repo / "plugins" / "kaoyan-22408"
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    run([sys.executable, "scripts/validate_repository.py"], repo, env)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], repo, env)

    semgrep = shutil.which("semgrep")
    if semgrep:
        env.setdefault(
            "SEMGREP_SETTINGS_FILE",
            str(Path(tempfile.gettempdir()) / "kaoyan-22408-semgrep-settings.yml"),
        )
        run(
            [semgrep, "scan", "--config", ".semgrep.yml", "--error", "--metrics=off", "--exclude", "dist", "."],
            repo,
            env,
        )
    else:
        print("[SKIP] Semgrep not found")

    if args.skip_system_validators:
        print("[SKIP] system validators")
        return 0

    system_root = Path.home() / ".codex" / "skills" / ".system"
    plugin_validator = system_root / "plugin-creator" / "scripts" / "validate_plugin.py"
    skill_validator = system_root / "skill-creator" / "scripts" / "quick_validate.py"
    if plugin_validator.is_file():
        run([sys.executable, str(plugin_validator), str(plugin)], repo, env)
    else:
        print("[SKIP] official plugin validator not found")
    if skill_validator.is_file():
        for skill in sorted((plugin / "skills").iterdir()):
            if skill.is_dir():
                run([sys.executable, str(skill_validator), str(skill)], repo, env)
    else:
        print("[SKIP] official Skill validator not found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
