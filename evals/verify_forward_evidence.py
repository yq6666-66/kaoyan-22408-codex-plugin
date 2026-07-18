#!/usr/bin/env python3
"""Verify internal consistency of forward evidence without authenticating its origin."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from common import (
    BEHAVIOR_CASES,
    EVIDENCE,
    EVIDENCE_SCHEMA,
    REPO,
    ROUTE_CASES,
    cases_sha256,
    evaluator_sha256,
    load_json,
    plugin_tree_sha256,
)


class EvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def parse_utc(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    require(parsed.tzinfo is not None, "generated_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def source_revision_matches_inputs(
    revision: str,
    schema_version: str,
    binding_mode: str = "pr",
) -> bool:
    relevant = [
        "plugins/kaoyan-22408",
        "tests/forward-cases.json",
        "tests/behavior-cases.json",
        "evals",
    ]
    if not (schema_version == "1.2" and binding_mode == "protected-main"):
        checks = [
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
            ["git", "diff", "--quiet", revision, "HEAD", "--", *relevant],
        ]
        for command in checks:
            if subprocess.run(
                command,
                cwd=REPO,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode != 0:
                return False
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *relevant],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return status.returncode == 0 and not status.stdout.strip()


def verify_evidence(
    evidence_path: Path = EVIDENCE,
    max_age_days: int = 30,
    *,
    check_source_revision: bool = True,
    binding_mode: str = "pr",
) -> dict:
    require(binding_mode in {"pr", "protected-main"}, "invalid evidence binding mode")
    evidence = load_json(evidence_path)
    schema = load_json(EVIDENCE_SCHEMA)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(evidence),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise EvidenceError(f"evidence schema violation at {location}: {first.message}")

    route_cases = load_json(ROUTE_CASES)["cases"]
    behavior_cases = load_json(BEHAVIOR_CASES)["cases"]
    require(len(route_cases) == 60, "route case set must contain exactly 60 cases")
    require(len(behavior_cases) == 24, "behavior case set must contain exactly 24 cases")
    require(
        evidence["plugin_tree_sha256"] == plugin_tree_sha256(),
        "evaluation evidence does not match the current plugin tree",
    )
    require(
        evidence["cases_sha256"] == cases_sha256(),
        "evaluation evidence does not match the current route/behavior cases",
    )
    require(
        evidence["evaluator_sha256"] == evaluator_sha256(),
        "evaluation evidence does not match the current evaluator harness",
    )
    if check_source_revision:
        require(
            source_revision_matches_inputs(
                evidence["source_revision"],
                evidence["schema_version"],
                binding_mode,
            ),
            "evaluation inputs are dirty or do not satisfy the evidence binding profile",
        )

    now = datetime.now(timezone.utc)
    generated_at = parse_utc(evidence["generated_at"])
    require(generated_at <= now + timedelta(minutes=5), "evaluation evidence is dated in the future")
    require(
        now - generated_at <= timedelta(days=max_age_days),
        f"evaluation evidence is older than {max_age_days} days",
    )

    expected_routes = {case["id"]: case["expectedPrimary"] for case in route_cases}
    route_results = {item["id"]: item for item in evidence["route_results"]}
    require(set(route_results) == set(expected_routes), "route evidence IDs do not match route cases")
    for case_id, expected in expected_routes.items():
        result = route_results[case_id]
        require(result["expected_primary"] == expected, f"{case_id}: expected route was altered")
        require(result["actual_primary"] == expected, f"{case_id}: wrong primary Skill")
        require(result["passed"] is True, f"{case_id}: route did not pass")

    expected_behaviors = {case["id"]: case for case in behavior_cases}
    behavior_results = {item["id"]: item for item in evidence["behavior_results"]}
    require(set(behavior_results) == set(expected_behaviors), "behavior evidence IDs do not match cases")
    for case_id, case in expected_behaviors.items():
        result = behavior_results[case_id]
        require(
            result["expected_primary"] == case["expectedPrimary"],
            f"{case_id}: expected behavior route was altered",
        )
        require(result["actual_primary"] == case["expectedPrimary"], f"{case_id}: wrong primary Skill")
        judge = result["judge"]
        require(judge.get("primarySkillPassed") is True, f"{case_id}: judge rejected primary Skill")
        criteria = judge.get("criteria")
        require(isinstance(criteria, list), f"{case_id}: missing judge criteria")
        require(len(criteria) == len(case["rubric"]), f"{case_id}: judge criterion count mismatch")
        require(
            [item.get("criterion") for item in criteria] == case["rubric"],
            f"{case_id}: judge rubric text/order mismatch",
        )
        require(all(item.get("passed") is True for item in criteria), f"{case_id}: rubric failure")
        require(judge.get("passed") is True and result["passed"] is True, f"{case_id}: behavior failed")

    require(evidence["route_summary"] == {"passed": 60, "total": 60}, "route gate must be 60/60")
    require(
        evidence["behavior_summary"] == {"passed": 24, "total": 24},
        "behavior gate must be 24/24",
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--max-age-days", type=int, default=30)
    parser.add_argument(
        "--binding-mode",
        choices=("pr", "protected-main"),
        default="pr",
    )
    args = parser.parse_args()
    try:
        evidence = verify_evidence(
            args.evidence.resolve(),
            args.max_age_days,
            binding_mode=args.binding_mode,
        )
    except (EvidenceError, OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print("[NOTICE] consistency only; this command does not authenticate the model run")
    print(f"[CONSISTENT] route claims: {evidence['route_summary']['passed']}/60")
    print(f"[CONSISTENT] behavior claims: {evidence['behavior_summary']['passed']}/24")
    print(
        "[CONSISTENT] runtime claim: "
        f"{evidence['codex_version']} / {evidence['model']} / {evidence['service_tier']}"
    )
    print(f"[CONSISTENT] plugin tree: {evidence['plugin_tree_sha256']}")
    print(f"[CONSISTENT] cases: {evidence['cases_sha256']}")
    print(f"[CONSISTENT] evaluator: {evidence['evaluator_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
