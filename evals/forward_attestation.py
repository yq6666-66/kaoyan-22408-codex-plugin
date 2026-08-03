#!/usr/bin/env python3
"""Prepare and verify externally authenticated forward-evaluation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


REPOSITORY = "yq6666-66/kaoyan-22408-codex-plugin"
SIGNER_IDENTITY = "yq6666-66"
SIGNATURE_NAMESPACE = "kaoyan-forward-eval"
STATEMENT_SCHEMA_VERSION = "1.0"
RESPONSE_MANIFEST_SCHEMA_VERSION = "1.0"
EVIDENCE_PROFILES = {
    "1.1": (36, 12, Path(__file__).resolve().parent / "schemas" / "evidence-1.1.schema.json"),
    "1.2": (60, 24, Path(__file__).resolve().parents[1] / "ci" / "schemas" / "evidence-1.2.schema.json"),
    "1.3": (60, 36, Path(__file__).resolve().parent / "schemas" / "evidence.schema.json"),
}


class AuthenticationError(RuntimeError):
    """Raised when evidence consistency or independent authentication fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthenticationError(message)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_regular_bytes(path: Path, label: str) -> bytes:
    require(path.is_file(), f"{label} is missing: {path}")
    require(not path.is_symlink(), f"{label} must not be a symlink: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AuthenticationError(f"cannot read {label}: {exc}") from exc


def load_json_bytes(payload: bytes, label: str) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticationError(f"{label} is not valid UTF-8 JSON: {exc}") from exc


def load_json_file(path: Path, label: str) -> tuple[Any, bytes]:
    payload = read_regular_bytes(path, label)
    return load_json_bytes(payload, label), payload


def hash_named_files(files: Iterable[tuple[str, Path]]) -> str:
    digest = hashlib.sha256()
    items = sorted(files, key=lambda item: item[0])
    require(bool(items), "cannot hash an empty input set")
    for name, path in items:
        payload = read_regular_bytes(path, f"evaluation input {name}")
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def regular_tree_files(root: Path, relative_to: Path) -> list[tuple[str, Path]]:
    require(root.is_dir(), f"required evaluation directory is missing: {root}")
    files: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        require(not path.is_symlink(), f"symlink is not allowed in evaluation input: {path}")
        if path.is_file():
            files.append((path.relative_to(relative_to).as_posix(), path))
    return files


def plugin_tree_sha256(repo: Path) -> str:
    plugin = repo / "plugins" / "kaoyan-22408"
    return hash_named_files(regular_tree_files(plugin, plugin))


def cases_sha256(repo: Path) -> str:
    return hash_named_files(
        [
            ("tests/behavior-cases.json", repo / "tests" / "behavior-cases.json"),
            ("tests/forward-cases.json", repo / "tests" / "forward-cases.json"),
        ]
    )


def evaluator_sha256(repo: Path) -> str:
    evals = repo / "evals"
    files = [
        (name, path)
        for name, path in regular_tree_files(evals, repo)
        if "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    ]
    return hash_named_files(files)


def run_git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AuthenticationError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def parse_utc(value: Any, label: str) -> datetime:
    require(isinstance(value, str), f"{label} must be an ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AuthenticationError(f"{label} is not a valid ISO-8601 timestamp") from exc
    require(parsed.tzinfo is not None, f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def structured_response_manifest(evidence: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for result in evidence["route_results"]:
        payload = canonical_json_bytes(
            {
                "primarySkill": result["actual_primary"],
                "rationale": result["rationale"],
                "responsePreview": result["response_preview"],
            }
        )
        entries.append(
            {
                "case_id": result["id"],
                "role": "route",
                "byte_length": len(payload),
                "sha256": sha256_bytes(payload),
            }
        )
    for result in evidence["behavior_results"]:
        actor_payload = canonical_json_bytes(
            {
                "primarySkill": result["actual_primary"],
                "response": result["actor_response"],
                "recordTypes": result["record_types"],
                "evidenceTags": result["evidence_tags"],
            }
        )
        judge_payload = canonical_json_bytes(result["judge"])
        for role, payload in (("actor", actor_payload), ("judge", judge_payload)):
            entries.append(
                {
                    "case_id": result["id"],
                    "role": role,
                    "byte_length": len(payload),
                    "sha256": sha256_bytes(payload),
                }
            )
    entries.sort(key=lambda item: (item["case_id"], item["role"]))
    return {
        "schema_version": RESPONSE_MANIFEST_SCHEMA_VERSION,
        "source_revision": evidence["source_revision"],
        "entries": entries,
    }


def validate_evidence(repo: Path, evidence: dict[str, Any]) -> None:
    profile = EVIDENCE_PROFILES.get(evidence.get("schema_version"))
    require(profile is not None, "unsupported forward-evidence schema version")
    route_count, behavior_count, schema_path = profile
    schema, _ = load_json_file(
        schema_path,
        "trusted forward-evidence schema",
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
        raise AuthenticationError(
            f"evidence schema violation at {location}: {first.message}"
        )

    route_cases, _ = load_json_file(
        repo / "tests" / "forward-cases.json",
        "route cases",
    )
    behavior_cases, _ = load_json_file(
        repo / "tests" / "behavior-cases.json",
        "behavior cases",
    )
    require(
        isinstance(route_cases, dict)
        and route_cases.get("schemaVersion") == evidence["schema_version"]
        and len(route_cases.get("cases", [])) == route_count,
        f"route case set must use schemaVersion {evidence['schema_version']} and contain exactly {route_count} cases",
    )
    require(
        isinstance(behavior_cases, dict)
        and behavior_cases.get("schemaVersion") == evidence["schema_version"]
        and len(behavior_cases.get("cases", [])) == behavior_count,
        f"behavior case set must use schemaVersion {evidence['schema_version']} and contain exactly {behavior_count} cases",
    )

    expected_routes = {
        case["id"]: case["expectedPrimary"] for case in route_cases["cases"]
    }
    route_results = {item["id"]: item for item in evidence["route_results"]}
    require(
        set(route_results) == set(expected_routes),
        "route evidence IDs do not match route cases",
    )
    for case_id, expected in expected_routes.items():
        result = route_results[case_id]
        require(result["expected_primary"] == expected, f"{case_id}: altered route")
        require(result["actual_primary"] == expected, f"{case_id}: wrong primary Skill")
        require(result["passed"] is True, f"{case_id}: route did not pass")

    expected_behaviors = {
        case["id"]: case for case in behavior_cases["cases"]
    }
    behavior_results = {
        item["id"]: item for item in evidence["behavior_results"]
    }
    require(
        set(behavior_results) == set(expected_behaviors),
        "behavior evidence IDs do not match behavior cases",
    )
    for case_id, case in expected_behaviors.items():
        result = behavior_results[case_id]
        require(
            result["expected_primary"] == case["expectedPrimary"],
            f"{case_id}: altered behavior route",
        )
        require(
            result["actual_primary"] == case["expectedPrimary"],
            f"{case_id}: wrong behavior primary Skill",
        )
        judge = result["judge"]
        criteria = judge.get("criteria")
        require(isinstance(criteria, list), f"{case_id}: missing judge criteria")
        require(
            [item.get("criterion") for item in criteria] == case["rubric"],
            f"{case_id}: judge rubric text/order mismatch",
        )
        require(
            all(item.get("passed") is True for item in criteria),
            f"{case_id}: rubric failure",
        )
        require(
            judge.get("primarySkillPassed") is True
            and judge.get("passed") is True
            and result["passed"] is True,
            f"{case_id}: behavior did not pass",
        )

    require(
        evidence["route_summary"] == {"passed": route_count, "total": route_count},
        f"route summary must be {route_count}/{route_count}",
    )
    require(
        evidence["behavior_summary"] == {"passed": behavior_count, "total": behavior_count},
        f"behavior summary must be {behavior_count}/{behavior_count}",
    )


def validate_candidate_binding(repo: Path, evidence: dict[str, Any]) -> None:
    repo = repo.resolve()
    require(
        evidence["plugin_tree_sha256"] == plugin_tree_sha256(repo),
        "evidence does not match the candidate plugin tree",
    )
    require(
        evidence["cases_sha256"] == cases_sha256(repo),
        "evidence does not match the candidate case set",
    )
    require(
        evidence["evaluator_sha256"] == evaluator_sha256(repo),
        "evidence does not match the candidate evaluator",
    )
    relevant = [
        "plugins/kaoyan-22408",
        "tests/forward-cases.json",
        "tests/behavior-cases.json",
        "evals",
    ]
    source_revision = evidence["source_revision"]
    run_git(repo, "cat-file", "-e", f"{source_revision}^{{commit}}")
    require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_revision, "HEAD"],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "evidence source revision must be an ancestor of the candidate HEAD",
    )
    require(
        subprocess.run(
            ["git", "diff", "--quiet", source_revision, "HEAD", "--", *relevant],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0,
        "candidate evaluation inputs differ from the evaluated source revision",
    )
    status = run_git(
        repo,
        "status",
        "--porcelain",
        "--",
        *relevant,
    )
    require(not status, "candidate evaluation inputs must be clean")


def validate_response_manifest(
    evidence: dict[str, Any],
    manifest: Any,
) -> None:
    route_count, behavior_count, _ = EVIDENCE_PROFILES[evidence["schema_version"]]
    require(
        manifest == structured_response_manifest(evidence),
        "structured-response manifest does not match the exact evidence outputs",
    )
    require(
        len(manifest["entries"]) == route_count + (2 * behavior_count),
        "structured-response manifest does not contain the required response summaries",
    )


def prepare_statement(
    repo: Path,
    evidence_path: Path,
    response_manifest_path: Path,
    statement_path: Path,
    *,
    max_age_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    require(max_age_days > 0, "max_age_days must be positive")
    repo = repo.resolve()
    evidence, evidence_bytes = load_json_file(evidence_path, "forward evidence")
    require(isinstance(evidence, dict), "forward evidence root must be an object")
    validate_evidence(repo, evidence)
    validate_candidate_binding(repo, evidence)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated_at = parse_utc(evidence["generated_at"], "generated_at")
    require(
        generated_at <= current_time + timedelta(minutes=5),
        "evidence generated_at is in the future",
    )
    require(
        current_time - generated_at <= timedelta(days=max_age_days),
        f"evidence is older than {max_age_days} days",
    )

    manifest = structured_response_manifest(evidence)
    manifest_bytes = canonical_json_bytes(manifest)
    response_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    response_manifest_path.write_bytes(manifest_bytes)
    expires_at = generated_at + timedelta(days=max_age_days)
    statement = {
        "schema_version": STATEMENT_SCHEMA_VERSION,
        "namespace": SIGNATURE_NAMESPACE,
        "repository": REPOSITORY,
        "signer": SIGNER_IDENTITY,
        "issued_at": evidence["generated_at"],
        "expires_at": format_utc(expires_at),
        "source_revision": evidence["source_revision"],
        "plugin_tree_sha256": evidence["plugin_tree_sha256"],
        "cases_sha256": evidence["cases_sha256"],
        "evaluator_sha256": evidence["evaluator_sha256"],
        "evidence_sha256": sha256_bytes(evidence_bytes),
        "response_manifest_sha256": sha256_bytes(manifest_bytes),
    }
    statement_path.parent.mkdir(parents=True, exist_ok=True)
    statement_path.write_bytes(canonical_json_bytes(statement))
    return statement


def verify_ssh_signature(
    statement_bytes: bytes,
    signature_path: Path,
    allowed_signers_path: Path,
) -> None:
    ssh_keygen = shutil.which("ssh-keygen")
    require(ssh_keygen is not None, "ssh-keygen is required for sshsig verification")
    signature = read_regular_bytes(signature_path, "attestation signature")
    require(bool(signature.strip()), "attestation signature is empty")
    completed = subprocess.run(
        [
            ssh_keygen,
            "-Y",
            "verify",
            "-f",
            str(allowed_signers_path),
            "-I",
            SIGNER_IDENTITY,
            "-n",
            SIGNATURE_NAMESPACE,
            "-s",
            str(signature_path),
        ],
        input=statement_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).decode("utf-8", "replace").strip()
        raise AuthenticationError(f"OpenSSH evidence signature verification failed: {detail}")


def verify_authenticated_bundle(
    repo: Path,
    evidence_path: Path,
    response_manifest_path: Path,
    statement_path: Path,
    signature_path: Path,
    allowed_signers_path: Path,
    *,
    max_age_days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    require(max_age_days > 0, "max_age_days must be positive")
    repo = repo.resolve()
    require(
        not allowed_signers_path.is_symlink(),
        "trusted allowed_signers must not be a symlink",
    )
    allowed = allowed_signers_path.resolve()
    require(
        not allowed.is_relative_to(repo),
        "trusted allowed_signers must be pinned outside the candidate checkout",
    )
    allowed_signers = read_regular_bytes(allowed, "trusted allowed_signers")
    require(bool(allowed_signers.strip()), "trusted allowed_signers is empty")

    evidence, evidence_bytes = load_json_file(evidence_path, "forward evidence")
    manifest, manifest_bytes = load_json_file(
        response_manifest_path,
        "structured-response manifest",
    )
    statement, statement_bytes = load_json_file(
        statement_path,
        "attestation statement",
    )
    require(isinstance(evidence, dict), "forward evidence root must be an object")
    require(isinstance(statement, dict), "attestation statement root must be an object")
    require(
        statement_bytes == canonical_json_bytes(statement),
        "attestation statement must use canonical JSON encoding",
    )
    require(
        manifest_bytes == canonical_json_bytes(manifest),
        "structured-response manifest must use canonical JSON encoding",
    )
    validate_evidence(repo, evidence)
    validate_candidate_binding(repo, evidence)
    validate_response_manifest(evidence, manifest)

    expected_keys = {
        "schema_version",
        "namespace",
        "repository",
        "signer",
        "issued_at",
        "expires_at",
        "source_revision",
        "plugin_tree_sha256",
        "cases_sha256",
        "evaluator_sha256",
        "evidence_sha256",
        "response_manifest_sha256",
    }
    require(set(statement) == expected_keys, "attestation statement shape is invalid")
    require(
        statement["schema_version"] == STATEMENT_SCHEMA_VERSION,
        "unsupported attestation statement schema",
    )
    require(statement["namespace"] == SIGNATURE_NAMESPACE, "attestation namespace mismatch")
    require(statement["repository"] == REPOSITORY, "attestation repository mismatch")
    require(statement["signer"] == SIGNER_IDENTITY, "attestation signer mismatch")
    for key in (
        "source_revision",
        "plugin_tree_sha256",
        "cases_sha256",
        "evaluator_sha256",
    ):
        require(statement[key] == evidence[key], f"attestation {key} mismatch")
    require(
        statement["issued_at"] == evidence["generated_at"],
        "attestation issued_at must equal evidence generated_at",
    )
    require(
        statement["evidence_sha256"] == sha256_bytes(evidence_bytes),
        "attestation evidence SHA-256 mismatch",
    )
    require(
        statement["response_manifest_sha256"] == sha256_bytes(manifest_bytes),
        "attestation response-manifest SHA-256 mismatch",
    )

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    issued_at = parse_utc(statement["issued_at"], "attestation issued_at")
    expires_at = parse_utc(statement["expires_at"], "attestation expires_at")
    require(issued_at <= current_time + timedelta(minutes=5), "attestation is future-dated")
    require(expires_at > issued_at, "attestation expiry must follow issuance")
    require(
        expires_at - issued_at <= timedelta(days=max_age_days),
        "attestation validity exceeds the allowed window",
    )
    require(current_time <= expires_at, "attestation has expired")
    verify_ssh_signature(statement_bytes, signature_path, allowed)
    return evidence


def bundle_paths(repo: Path) -> dict[str, Path]:
    tests = repo / "tests"
    return {
        "evidence": tests / "forward-eval-evidence.json",
        "response_manifest": tests / "forward-eval-response-manifest.json",
        "statement": tests / "forward-eval-attestation.json",
        "signature": tests / "forward-eval-attestation.json.sig",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--repo", type=Path, default=Path.cwd())
        subparser.add_argument("--evidence", type=Path)
        subparser.add_argument("--response-manifest", type=Path)
        subparser.add_argument("--statement", type=Path)
        subparser.add_argument("--max-age-days", type=int, default=30)
        if command == "verify":
            subparser.add_argument("--signature", type=Path)
            subparser.add_argument("--allowed-signers", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    defaults = bundle_paths(repo)
    evidence = args.evidence or defaults["evidence"]
    response_manifest = args.response_manifest or defaults["response_manifest"]
    statement = args.statement or defaults["statement"]
    try:
        if args.command == "prepare":
            prepared = prepare_statement(
                repo,
                evidence,
                response_manifest,
                statement,
                max_age_days=args.max_age_days,
            )
            print(f"[OK] unsigned statement: {statement}")
            print(f"[OK] expires_at: {prepared['expires_at']}")
            print(
                "[NEXT] sign with: ssh-keygen -Y sign -f <private-key> "
                f"-n {SIGNATURE_NAMESPACE} {statement}"
            )
        else:
            signature = args.signature or defaults["signature"]
            verified = verify_authenticated_bundle(
                repo,
                evidence,
                response_manifest,
                statement,
                signature,
                args.allowed_signers,
                max_age_days=args.max_age_days,
            )
            print(
                "[OK] authenticated forward evidence: "
                f"{verified['route_summary']['passed']}/{verified['route_summary']['total']} routes, "
                f"{verified['behavior_summary']['passed']}/{verified['behavior_summary']['total']} behaviors"
            )
    except (AuthenticationError, OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
