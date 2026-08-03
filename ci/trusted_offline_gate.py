#!/usr/bin/env python3
"""Validate untrusted plugin data without executing candidate code."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


SKILLS = {
    "kaoyan-22408-planner",
    "kaoyan-408-tutor",
    "kaoyan-english2-coach",
    "kaoyan-error-loop-coach",
    "kaoyan-material-study-assistant",
    "kaoyan-math2-coach",
    "kaoyan-mock-exam-coach",
    "kaoyan-official-info-researcher",
    "kaoyan-past-paper-analyst",
    "kaoyan-politics-coach",
    "kaoyan-progress-diagnostician",
    "kaoyan-review-executor",
}
REFERENCES = {
    "capability-routing-contract.md",
    "evidence-copyright-contract.md",
    "notion-brain-contract.md",
    "obsidian-brain-contract.md",
    "portable-learning-records.md",
    "portable-learning-records.schema.json",
}
ALLOWED = {
    ".codex-plugin/plugin.json",
    "assets/kaoyan-22408.svg",
    *(f"references/{name}" for name in REFERENCES),
    *(f"skills/{name}/SKILL.md" for name in SKILLS),
    *(f"skills/{name}/agents/openai.yaml" for name in SKILLS),
}
REMOVED = {
    "evals/run_forward_eval.py",
    "evals/trusted_forward_eval.py",
    "evals/verify_forward_evidence.py",
    "ci/trusted_forward_attestation.py",
    "tests/forward-eval-evidence.json",
    "tests/forward-eval-attestation.json",
    "tests/forward-eval-attestation.json.sig",
}


class GateError(RuntimeError):
    pass


def tree_digest(payloads: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(payloads):
        encoded = name.encode("utf-8")
        payload = payloads[name]
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(f"invalid JSON data: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError(f"JSON root must be an object: {path}")
    return value


def verify(repo: Path) -> None:
    repo = repo.resolve()
    if not repo.is_dir():
        raise GateError("candidate repository is missing")
    if any(path.is_symlink() for path in repo.rglob("*")):
        raise GateError("candidate contains a symbolic link")
    if any((repo / path).exists() for path in REMOVED):
        raise GateError("candidate contains retired model-evaluation artifacts")

    workflow = (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    required = "python scripts/check.py --verify-system-evidence"
    if required not in workflow:
        raise GateError("CI does not invoke the offline quality gate")
    forbidden = ("codex exec", "run_forward_eval.py", "forward-eval-evidence")
    if any(marker in workflow for marker in forbidden):
        raise GateError("CI still invokes retired model-evaluation machinery")

    plugin = repo / "plugins/kaoyan-22408"
    actual = {
        path.relative_to(plugin).as_posix()
        for path in plugin.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != ALLOWED:
        raise GateError("plugin tree does not match the exact release allowlist")
    payloads: dict[str, bytes] = {}
    for relative in sorted(ALLOWED):
        payload = (plugin / relative).read_bytes()
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GateError(f"release file is not UTF-8: {relative}") from exc
        if b"\r" in payload:
            raise GateError(f"release file is not LF-only: {relative}")
        payloads[relative] = payload

    manifest = load_json(plugin / ".codex-plugin/plugin.json")
    if manifest.get("name") != "kaoyan-22408" or not isinstance(manifest.get("version"), str):
        raise GateError("plugin manifest identity or version is invalid")
    skill_dirs = {path.name for path in (plugin / "skills").iterdir() if path.is_dir()}
    if skill_dirs != SKILLS:
        raise GateError("candidate does not contain exactly the 12 approved Skills")

    evidence = load_json(repo / "tests/system-validator-evidence.json")
    plugin_evidence = evidence.get("plugin")
    if not isinstance(plugin_evidence, dict):
        raise GateError("validator evidence plugin section is invalid")
    if plugin_evidence.get("version") != manifest["version"]:
        raise GateError("validator evidence version is stale")
    if plugin_evidence.get("treeSha256") != tree_digest(payloads):
        raise GateError("validator evidence tree hash is stale or tampered")
    results = evidence.get("results")
    if not isinstance(results, dict) or results.get("plugin") != {"passed": True, "exitCode": 0}:
        raise GateError("plugin validator evidence did not pass")
    skills = results.get("skills")
    expected = {"passed": True, "exitCode": 0}
    if not isinstance(skills, dict) or set(skills) != SKILLS:
        raise GateError("Skill validator evidence coverage is incomplete")
    if any(result != expected for result in skills.values()):
        raise GateError("one or more Skill validator results did not pass")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.repo)
    except (GateError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print("[OK] trusted offline candidate gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
