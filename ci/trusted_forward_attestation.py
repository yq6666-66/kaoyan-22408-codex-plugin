#!/usr/bin/env python3
"""Verify signed forward evidence without executing candidate-owned Python.

This verifier lives outside ``evals/`` so the v1.1 evaluator hash remains
stable during the protected transition.  The protected workflow always runs
this file and the imported legacy verifier from the protected base checkout;
the candidate checkout is treated only as data.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


TRUSTED_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRUSTED_ROOT / "evals"))

import forward_attestation as legacy  # noqa: E402


PROFILE_COUNTS = {
    "1.1": (36, 12),
    "1.2": (60, 24),
    "1.3": (60, 36),
}
SCHEMA_PATHS = {
    version: TRUSTED_ROOT / "ci" / "schemas" / f"evidence-{version}.schema.json"
    for version in PROFILE_COUNTS
}
# Teach the immutable legacy helpers how to build/validate a 1.3 response
# manifest without modifying evals/ and invalidating the current 1.2 evidence.
legacy.EVIDENCE_PROFILES["1.3"] = (
    60,
    36,
    SCHEMA_PATHS["1.3"],
)
RELEVANT_INPUTS = (
    "plugins/kaoyan-22408",
    "tests/forward-cases.json",
    "tests/behavior-cases.json",
    "evals",
)
BINDING_MODE = "pr"
EXPECTED_HEAD: str | None = None


def profile(evidence: dict[str, Any]) -> tuple[str, int, int]:
    version = evidence.get("schema_version")
    legacy.require(version in PROFILE_COUNTS, f"unsupported evidence schema: {version!r}")
    route_total, behavior_total = PROFILE_COUNTS[version]
    return version, route_total, behavior_total


def validate_evidence(repo: Path, evidence: dict[str, Any]) -> None:
    version, route_total, behavior_total = profile(evidence)
    schema, _ = legacy.load_json_file(
        SCHEMA_PATHS[version],
        f"trusted forward-evidence {version} schema",
    )
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(evidence),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise legacy.AuthenticationError(
            f"evidence schema violation at {location}: {first.message}"
        )

    route_cases, _ = legacy.load_json_file(
        repo / "tests" / "forward-cases.json",
        "route cases",
    )
    behavior_cases, _ = legacy.load_json_file(
        repo / "tests" / "behavior-cases.json",
        "behavior cases",
    )
    legacy.require(isinstance(route_cases, dict), "route case set must be an object")
    legacy.require(
        route_cases.get("schemaVersion") == version,
        f"route case set must use schemaVersion {version}",
    )
    legacy.require(
        isinstance(route_cases.get("cases"), list)
        and len(route_cases["cases"]) == route_total,
        f"route case set must contain exactly {route_total} cases",
    )
    legacy.require(
        isinstance(behavior_cases, dict),
        "behavior case set must be an object",
    )
    legacy.require(
        behavior_cases.get("schemaVersion") == version,
        f"behavior case set must use schemaVersion {version}",
    )
    legacy.require(
        isinstance(behavior_cases.get("cases"), list)
        and len(behavior_cases["cases"]) == behavior_total,
        f"behavior case set must contain exactly {behavior_total} cases",
    )

    expected_routes = {
        case["id"]: case["expectedPrimary"] for case in route_cases["cases"]
    }
    legacy.require(
        len(expected_routes) == route_total,
        "route case IDs must be unique",
    )
    route_results = {item["id"]: item for item in evidence["route_results"]}
    legacy.require(
        len(route_results) == route_total,
        "route evidence IDs must be unique",
    )
    legacy.require(
        set(route_results) == set(expected_routes),
        "route evidence IDs do not match route cases",
    )
    for case_id, expected in expected_routes.items():
        result = route_results[case_id]
        legacy.require(result["expected_primary"] == expected, f"{case_id}: altered route")
        legacy.require(result["actual_primary"] == expected, f"{case_id}: wrong primary Skill")
        legacy.require(result["passed"] is True, f"{case_id}: route did not pass")

    expected_behaviors = {case["id"]: case for case in behavior_cases["cases"]}
    legacy.require(
        len(expected_behaviors) == behavior_total,
        "behavior case IDs must be unique",
    )
    behavior_results = {item["id"]: item for item in evidence["behavior_results"]}
    legacy.require(
        len(behavior_results) == behavior_total,
        "behavior evidence IDs must be unique",
    )
    legacy.require(
        set(behavior_results) == set(expected_behaviors),
        "behavior evidence IDs do not match behavior cases",
    )
    for case_id, case in expected_behaviors.items():
        result = behavior_results[case_id]
        legacy.require(
            result["expected_primary"] == case["expectedPrimary"],
            f"{case_id}: altered behavior route",
        )
        legacy.require(
            result["actual_primary"] == case["expectedPrimary"],
            f"{case_id}: wrong behavior primary Skill",
        )
        judge = result["judge"]
        criteria = judge.get("criteria")
        legacy.require(isinstance(criteria, list), f"{case_id}: missing judge criteria")
        legacy.require(
            [item.get("criterion") for item in criteria] == case["rubric"],
            f"{case_id}: judge rubric text/order mismatch",
        )
        legacy.require(
            all(item.get("passed") is True for item in criteria),
            f"{case_id}: rubric failure",
        )
        legacy.require(
            judge.get("primarySkillPassed") is True
            and judge.get("passed") is True
            and result["passed"] is True,
            f"{case_id}: behavior did not pass",
        )

    legacy.require(
        evidence["route_summary"] == {"passed": route_total, "total": route_total},
        f"route summary must be {route_total}/{route_total}",
    )
    legacy.require(
        evidence["behavior_summary"]
        == {"passed": behavior_total, "total": behavior_total},
        f"behavior summary must be {behavior_total}/{behavior_total}",
    )
    manifest_entries = legacy.structured_response_manifest(evidence)["entries"]
    expected_entries = route_total + (2 * behavior_total)
    legacy.require(
        len(manifest_entries) == expected_entries,
        f"response manifest must contain exactly {expected_entries} entries",
    )


def validate_candidate_binding(repo: Path, evidence: dict[str, Any]) -> None:
    version, _, _ = profile(evidence)
    if version == "1.1":
        legacy_validate_candidate_binding(repo, evidence)
        return

    repo = repo.resolve()
    legacy.require(
        evidence["plugin_tree_sha256"] == legacy.plugin_tree_sha256(repo),
        "evidence does not match the candidate plugin tree",
    )
    legacy.require(
        evidence["cases_sha256"] == legacy.cases_sha256(repo),
        "evidence does not match the candidate case set",
    )
    legacy.require(
        evidence["evaluator_sha256"] == legacy.evaluator_sha256(repo),
        "evidence does not match the candidate evaluator",
    )
    status = legacy.run_git(repo, "status", "--porcelain", "--", *RELEVANT_INPUTS)
    legacy.require(not status, "candidate evaluation inputs must be clean")
    if BINDING_MODE == "protected-main":
        return

    source_revision = evidence["source_revision"]
    legacy.run_git(repo, "cat-file", "-e", f"{source_revision}^{{commit}}")
    candidate_head = legacy.run_git(repo, "rev-parse", "HEAD")
    if EXPECTED_HEAD is not None:
        legacy.require(
            candidate_head == EXPECTED_HEAD,
            "candidate HEAD does not match the protected workflow event",
        )
    legacy.require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_revision, candidate_head],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "evidence source revision must be an ancestor of the candidate HEAD",
    )
    legacy.require(
        subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                source_revision,
                candidate_head,
                "--",
                *RELEVANT_INPUTS,
            ],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "candidate evaluation inputs differ from the evaluated source revision",
    )


legacy_validate_candidate_binding = legacy.validate_candidate_binding
legacy.validate_evidence = validate_evidence
legacy.validate_candidate_binding = validate_candidate_binding


def main() -> int:
    global BINDING_MODE, EXPECTED_HEAD
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--repo", type=Path, default=Path.cwd())
        subparser.add_argument("--evidence", type=Path)
        subparser.add_argument("--response-manifest", type=Path)
        subparser.add_argument("--statement", type=Path)
        subparser.add_argument("--max-age-days", type=int, default=30)
        subparser.add_argument(
            "--binding-mode",
            choices=("pr", "protected-main"),
            default="pr",
            help="Use protected-main only after the workflow proves the tag is on protected main.",
        )
        subparser.add_argument(
            "--expected-head",
            help="Exact candidate HEAD from the pull_request_target event.",
        )
        if command == "verify":
            subparser.add_argument("--signature", type=Path)
            subparser.add_argument("--allowed-signers", type=Path, required=True)
    args = parser.parse_args()
    BINDING_MODE = args.binding_mode
    EXPECTED_HEAD = args.expected_head
    if BINDING_MODE == "protected-main" and EXPECTED_HEAD is not None:
        parser.error("--expected-head is only valid with --binding-mode pr")
    repo = args.repo.resolve()
    defaults = legacy.bundle_paths(repo)
    evidence_path = args.evidence or defaults["evidence"]
    response_manifest = args.response_manifest or defaults["response_manifest"]
    statement = args.statement or defaults["statement"]
    try:
        if args.command == "prepare":
            prepared = legacy.prepare_statement(
                repo,
                evidence_path,
                response_manifest,
                statement,
                max_age_days=args.max_age_days,
            )
            print(f"[OK] unsigned statement: {statement}")
            print(f"[OK] expires_at: {prepared['expires_at']}")
            print(
                "[NEXT] sign with: ssh-keygen -Y sign -f <private-key> "
                f"-n {legacy.SIGNATURE_NAMESPACE} {statement}"
            )
        else:
            signature = args.signature or defaults["signature"]
            evidence = legacy.verify_authenticated_bundle(
                repo,
                evidence_path,
                response_manifest,
                statement,
                signature,
                args.allowed_signers,
                max_age_days=args.max_age_days,
            )
            routes = evidence["route_summary"]
            behaviors = evidence["behavior_summary"]
            print(
                "[OK] authenticated forward evidence: "
                f"{routes['passed']}/{routes['total']} routes, "
                f"{behaviors['passed']}/{behaviors['total']} behaviors"
            )
    except (legacy.AuthenticationError, OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
