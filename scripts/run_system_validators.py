#!/usr/bin/env python3
"""Run official plugin/Skill validators or verify their bound evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from build_release import plugin_tree_digest
from validate_repository import ALLOWED_RELEASE_FILES, EXPECTED_SKILLS, ValidationError


SCHEMA_VERSION = "1.1"
Runner = Callable[[list[str], Path, dict[str, str]], subprocess.CompletedProcess[str]]


class EvidenceError(RuntimeError):
    """Raised when validator execution or evidence verification fails."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_plugin_payloads(repo: Path) -> dict[str, bytes]:
    plugin = repo / "plugins" / "kaoyan-22408"
    payloads: dict[str, bytes] = {}
    for relative in sorted(ALLOWED_RELEASE_FILES):
        path = plugin.joinpath(*relative.split("/"))
        if not path.is_file() or path.is_symlink():
            raise EvidenceError(f"plugin allowlist file is missing or unsafe: {relative}")
        payloads[relative] = path.read_bytes()
    actual = {
        path.relative_to(plugin).as_posix()
        for path in plugin.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != set(ALLOWED_RELEASE_FILES):
        raise EvidenceError("plugin tree does not match the exact release allowlist")
    return payloads


def current_plugin_tree_hash(repo: Path) -> str:
    return plugin_tree_digest(current_plugin_payloads(repo))


def run_command(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _run_validator(
    label: str,
    command: list[str],
    repo: Path,
    env: dict[str, str],
    runner: Runner,
) -> dict[str, Any]:
    result = runner(command, repo, env)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise EvidenceError(f"{label} failed with exit {result.returncode}: {detail}")
    return {"passed": True, "exitCode": 0}


def locate_validators(system_root: Path) -> tuple[Path | None, Path, Path]:
    plugin_validator = system_root / "plugin-creator" / "scripts" / "validate_plugin.py"
    plugin_spec = system_root / "plugin-creator" / "references" / "plugin-json-spec.md"
    skill_validator = system_root / "skill-creator" / "scripts" / "quick_validate.py"
    if not plugin_validator.is_file() and not plugin_spec.is_file():
        raise EvidenceError(
            f"neither the standalone plugin validator nor the official plugin spec exists under {system_root}"
        )
    if not skill_validator.is_file():
        raise EvidenceError(f"official Skill validator not found under {system_root}")
    return plugin_validator if plugin_validator.is_file() else None, skill_validator, plugin_spec


def generate_evidence(
    repo: Path,
    system_root: Path,
    *,
    runner: Runner = run_command,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = repo.resolve()
    plugin = repo / "plugins" / "kaoyan-22408"
    plugin_validator, skill_validator, plugin_spec = locate_validators(system_root.resolve())
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    if plugin_validator is not None:
        plugin_result = _run_validator(
            "official plugin validator",
            [sys.executable, str(plugin_validator), str(plugin)],
            repo,
            env,
            runner,
        )
        plugin_evidence = {
            "mode": "official-script",
            "source": "plugin-creator/scripts/validate_plugin.py",
            "sha256": _sha256(plugin_validator),
        }
    else:
        repository_validator = repo / "scripts" / "validate_repository.py"
        plugin_result = _run_validator(
            "spec-backed repository plugin validator",
            [sys.executable, str(repository_validator)],
            repo,
            env,
            runner,
        )
        plugin_evidence = {
            "mode": "spec-backed-repository",
            "source": "scripts/validate_repository.py",
            "sha256": _sha256(repository_validator),
            "specSource": "plugin-creator/references/plugin-json-spec.md",
            "specSha256": _sha256(plugin_spec),
            "standaloneOfficialValidatorAvailable": False,
        }
    skill_results: dict[str, dict[str, Any]] = {}
    for name in sorted(EXPECTED_SKILLS):
        skill_results[name] = _run_validator(
            f"quick_validate {name}",
            [sys.executable, str(skill_validator), str(plugin / "skills" / name)],
            repo,
            env,
            runner,
        )

    manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated.isoformat().replace("+00:00", "Z"),
        "plugin": {
            "name": "kaoyan-22408",
            "version": manifest["version"],
            "treeSha256": current_plugin_tree_hash(repo),
        },
        "runtime": {"pythonVersion": platform.python_version()},
        "validators": {
            "plugin": plugin_evidence,
            "skill": {
                "source": "skill-creator/scripts/quick_validate.py",
                "sha256": _sha256(skill_validator),
            },
        },
        "results": {
            "plugin": plugin_result,
            "skills": skill_results,
        },
    }


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_bytes(payload.encode("utf-8"))


def load_evidence(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read validator evidence: {exc}") from exc
    if not isinstance(document, dict):
        raise EvidenceError("validator evidence root must be an object")
    return document


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError("generatedAt must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError("generatedAt is not a valid ISO-8601 timestamp") from exc
    return parsed.astimezone(timezone.utc)


def verify_evidence(
    repo: Path,
    evidence_path: Path,
    *,
    max_age_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    document = load_evidence(evidence_path)
    if document.get("schemaVersion") != SCHEMA_VERSION:
        raise EvidenceError("unsupported validator evidence schemaVersion")
    generated = _parse_timestamp(document.get("generatedAt"))
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if generated > current_time + timedelta(minutes=5):
        raise EvidenceError("validator evidence timestamp is in the future")
    if current_time - generated > timedelta(days=max_age_days):
        raise EvidenceError(f"validator evidence is older than {max_age_days} days")

    plugin = document.get("plugin")
    if not isinstance(plugin, dict) or plugin.get("name") != "kaoyan-22408":
        raise EvidenceError("validator evidence plugin identity is invalid")
    manifest = json.loads(
        (repo / "plugins" / "kaoyan-22408" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    if plugin.get("version") != manifest.get("version"):
        raise EvidenceError("validator evidence plugin version does not match the manifest")
    if plugin.get("treeSha256") != current_plugin_tree_hash(repo):
        raise EvidenceError("validator evidence plugin tree hash is stale or tampered")

    validators = document.get("validators")
    if not isinstance(validators, dict) or set(validators) != {"plugin", "skill"}:
        raise EvidenceError("validator source evidence is incomplete")
    plugin_validator = validators.get("plugin")
    if not isinstance(plugin_validator, dict):
        raise EvidenceError("plugin validator source evidence is invalid")
    mode = plugin_validator.get("mode")
    if mode == "official-script":
        if set(plugin_validator) != {"mode", "source", "sha256"}:
            raise EvidenceError("official plugin validator evidence shape is invalid")
        if plugin_validator.get("source") != "plugin-creator/scripts/validate_plugin.py":
            raise EvidenceError("official plugin validator source identifier is invalid")
    elif mode == "spec-backed-repository":
        required = {
            "mode",
            "source",
            "sha256",
            "specSource",
            "specSha256",
            "standaloneOfficialValidatorAvailable",
        }
        if set(plugin_validator) != required:
            raise EvidenceError("spec-backed plugin validator evidence shape is invalid")
        if (
            plugin_validator.get("source") != "scripts/validate_repository.py"
            or plugin_validator.get("specSource") != "plugin-creator/references/plugin-json-spec.md"
            or plugin_validator.get("standaloneOfficialValidatorAvailable") is not False
        ):
            raise EvidenceError("spec-backed plugin validator provenance is invalid")
        if plugin_validator.get("sha256") != _sha256(repo / "scripts" / "validate_repository.py"):
            raise EvidenceError("spec-backed repository validator hash is stale or tampered")
        if not re_full_sha256(plugin_validator.get("specSha256", "")):
            raise EvidenceError("official plugin spec SHA-256 is invalid")
    else:
        raise EvidenceError("plugin validator mode is invalid")
    if not re_full_sha256(plugin_validator.get("sha256", "")):
        raise EvidenceError("plugin validator SHA-256 is invalid")

    skill_validator = validators.get("skill")
    if not isinstance(skill_validator, dict) or set(skill_validator) != {"source", "sha256"}:
        raise EvidenceError("Skill validator source evidence is invalid")
    if skill_validator.get("source") != "skill-creator/scripts/quick_validate.py":
        raise EvidenceError("Skill validator source identifier is invalid")
    if not re_full_sha256(skill_validator.get("sha256", "")):
        raise EvidenceError("Skill validator SHA-256 is invalid")

    results = document.get("results")
    if not isinstance(results, dict) or results.get("plugin") != {"passed": True, "exitCode": 0}:
        raise EvidenceError("plugin validation did not pass")
    skills = results.get("skills")
    if not isinstance(skills, dict) or set(skills) != EXPECTED_SKILLS:
        raise EvidenceError("quick_validate evidence does not cover exactly 12 Skills")
    if any(result != {"passed": True, "exitCode": 0} for result in skills.values()):
        raise EvidenceError("one or more quick_validate results did not pass")
    return document


def re_full_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", type=Path, metavar="PATH")
    mode.add_argument("--verify-evidence", type=Path, metavar="PATH")
    parser.add_argument(
        "--system-root",
        type=Path,
        default=Path.home() / ".codex" / "skills" / ".system",
    )
    parser.add_argument("--max-age-days", type=int, default=30)
    args = parser.parse_args()
    target = args.write or args.verify_evidence
    if target is not None and not target.is_absolute():
        target = repo / target
    try:
        if args.write is not None:
            evidence = generate_evidence(repo, args.system_root)
            write_evidence(target, evidence)
            mode = evidence["validators"]["plugin"]["mode"]
            print(f"[OK] plugin validation mode: {mode}")
            print(f"[OK] official Skill validators: {len(EXPECTED_SKILLS)}/{len(EXPECTED_SKILLS)}")
            print(f"[OK] evidence: {target}")
        else:
            verify_evidence(repo, target, max_age_days=args.max_age_days)
            print(f"[OK] validator evidence matches the current plugin tree: {target}")
    except (EvidenceError, OSError, ValidationError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
