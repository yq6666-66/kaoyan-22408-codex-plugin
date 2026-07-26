from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ci"))

import trusted_forward_attestation as trusted  # noqa: E402

try:
    from .test_support import commit_all, copy_as_committed_repo, run_git  # type: ignore[import-not-found]
except ImportError:
    from test_support import commit_all, copy_as_committed_repo, run_git  # type: ignore[no-redef]


def expand_cases(repo: Path) -> None:
    route_path = repo / "tests/forward-cases.json"
    routes = json.loads(route_path.read_text(encoding="utf-8"))
    routes["schemaVersion"] = "1.2"
    templates = list(routes["cases"])
    while len(routes["cases"]) < 60:
        number = len(routes["cases"]) + 1
        case = dict(templates[(number - 1) % len(templates)])
        case["id"] = f"transition-route-{number:02d}"
        routes["cases"].append(case)
    route_path.write_text(
        json.dumps(routes, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    behavior_path = repo / "tests/behavior-cases.json"
    behaviors = json.loads(behavior_path.read_text(encoding="utf-8"))
    behaviors["schemaVersion"] = "1.2"
    templates = list(behaviors["cases"])
    while len(behaviors["cases"]) < 24:
        number = len(behaviors["cases"]) + 1
        case = dict(templates[(number - 1) % len(templates)])
        case["id"] = f"transition-behavior-{number:02d}"
        behaviors["cases"].append(case)
    behavior_path.write_text(
        json.dumps(behaviors, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_evidence(repo: Path, schema_version: str, now: datetime) -> dict:
    route_cases = json.loads(
        (repo / "tests/forward-cases.json").read_text(encoding="utf-8")
    )["cases"]
    behavior_cases = json.loads(
        (repo / "tests/behavior-cases.json").read_text(encoding="utf-8")
    )["cases"]
    evidence = {
        "schema_version": schema_version,
        "complete": True,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "source_revision": run_git(repo, "rev-parse", "HEAD").stdout.strip(),
        "plugin_tree_sha256": trusted.legacy.plugin_tree_sha256(repo),
        "cases_sha256": trusted.legacy.cases_sha256(repo),
        "evaluator_sha256": trusted.legacy.evaluator_sha256(repo),
        "codex_version": "codex-cli transition-test",
        "model": "test-model",
        "service_tier": "fast",
        "route_summary": {"passed": len(route_cases), "total": len(route_cases)},
        "behavior_summary": {
            "passed": len(behavior_cases),
            "total": len(behavior_cases),
        },
        "route_results": [
            {
                "id": case["id"],
                "expected_primary": case["expectedPrimary"],
                "actual_primary": case["expectedPrimary"],
                "passed": True,
                "rationale": "trusted transition fixture",
                "response_preview": "trusted transition fixture",
            }
            for case in route_cases
        ],
        "behavior_results": [
            {
                "id": case["id"],
                "expected_primary": case["expectedPrimary"],
                "actual_primary": case["expectedPrimary"],
                "actor_response": "trusted transition fixture",
                "record_types": [],
                "evidence_tags": [],
                "judge": {
                    "passed": True,
                    "primarySkillPassed": True,
                    "criteria": [
                        {
                            "criterion": criterion,
                            "passed": True,
                            "evidence": "trusted transition fixture",
                        }
                        for criterion in case["rubric"]
                    ],
                    "summary": "trusted transition fixture",
                },
                "passed": True,
            }
            for case in behavior_cases
        ],
    }
    if schema_version == "1.2":
        evidence["cache_mode"] = "disabled"
    return evidence


class TrustedForwardAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("ssh-keygen") is None:
            self.skipTest("OpenSSH ssh-keygen is unavailable")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = copy_as_committed_repo(self.root / "repo")
        expand_cases(self.repo)
        if run_git(self.repo, "status", "--porcelain").stdout.strip():
            commit_all(self.repo, "expand transition cases")
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.evidence = build_evidence(self.repo, "1.2", self.now)
        self.evidence_path = self.repo / "tests/forward-eval-evidence.json"
        self.manifest_path = self.repo / "tests/forward-eval-response-manifest.json"
        self.statement_path = self.repo / "tests/forward-eval-attestation.json"
        self.signature_path = self.repo / "tests/forward-eval-attestation.json.sig"
        self.evidence_path.write_text(
            json.dumps(self.evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        trusted.BINDING_MODE = "pr"
        trusted.EXPECTED_HEAD = run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        trusted.legacy.prepare_statement(
            self.repo,
            self.evidence_path,
            self.manifest_path,
            self.statement_path,
            now=self.now,
        )
        self.private_key = self.root / "maintainer_ed25519"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(self.private_key),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        public_key = self.private_key.with_suffix(".pub").read_text(
            encoding="utf-8"
        ).strip()
        self.allowed_signers = self.root / "trusted.allowed_signers"
        self.allowed_signers.write_text(
            f"yq6666-66 {public_key}\n",
            encoding="utf-8",
            newline="\n",
        )

    def sign(self) -> None:
        subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(self.private_key),
                "-n",
                trusted.legacy.SIGNATURE_NAMESPACE,
                str(self.statement_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def verify(self) -> dict:
        return trusted.legacy.verify_authenticated_bundle(
            self.repo,
            self.evidence_path,
            self.manifest_path,
            self.statement_path,
            self.signature_path,
            self.allowed_signers,
            now=self.now,
        )

    def test_accepts_60_24_and_requires_108_manifest_entries(self) -> None:
        self.sign()
        evidence = self.verify()
        self.assertEqual(evidence["route_summary"], {"passed": 60, "total": 60})
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["entries"]), 108)
        identities = {(entry["case_id"], entry["role"]) for entry in manifest["entries"]}
        self.assertEqual(len(identities), 108)

    def test_rejects_wrong_v12_counts_and_unknown_profile(self) -> None:
        cached = json.loads(json.dumps(self.evidence))
        cached["cache_mode"] = "enabled"
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "schema violation"):
            trusted.validate_evidence(self.repo, cached)
        short = json.loads(json.dumps(self.evidence))
        short["route_results"].pop()
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "schema violation"):
            trusted.validate_evidence(self.repo, short)
        short_behavior = json.loads(json.dumps(self.evidence))
        short_behavior["behavior_results"].pop()
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "schema violation"):
            trusted.validate_evidence(self.repo, short_behavior)
        wrong_summary = json.loads(json.dumps(self.evidence))
        wrong_summary["route_summary"] = {"passed": 59, "total": 60}
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "route summary"):
            trusted.validate_evidence(self.repo, wrong_summary)
        unknown = json.loads(json.dumps(self.evidence))
        unknown["schema_version"] = "9.9"
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "unsupported"):
            trusted.validate_evidence(self.repo, unknown)

    def test_v12_requires_disabled_cache_mode(self) -> None:
        missing = json.loads(json.dumps(self.evidence))
        missing.pop("cache_mode")
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "schema violation"):
            trusted.validate_evidence(self.repo, missing)
        enabled = json.loads(json.dumps(self.evidence))
        enabled["cache_mode"] = "enabled"
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "schema violation"):
            trusted.validate_evidence(self.repo, enabled)

    def test_pr_binding_rejects_wrong_event_head(self) -> None:
        self.sign()
        trusted.BINDING_MODE = "pr"
        trusted.EXPECTED_HEAD = "0" * 40
        with self.assertRaisesRegex(
            trusted.legacy.AuthenticationError,
            "does not match the protected workflow event",
        ):
            self.verify()

    def test_pr_binding_is_strict_but_protected_main_is_content_addressed(self) -> None:
        self.sign()
        self.verify()
        tree = run_git(self.repo, "rev-parse", "HEAD^{tree}").stdout.strip()
        detached = run_git(self.repo, "commit-tree", tree, "-m", "simulated squash").stdout.strip()
        run_git(self.repo, "update-ref", "HEAD", detached)
        trusted.EXPECTED_HEAD = detached
        trusted.BINDING_MODE = "pr"
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "must be an ancestor"):
            self.verify()
        trusted.BINDING_MODE = "protected-main"
        self.assertEqual(self.verify()["schema_version"], "1.2")

    def test_rejects_changed_candidate_inputs(self) -> None:
        self.sign()
        skill = next((self.repo / "plugins/kaoyan-22408/skills").glob("*/SKILL.md"))
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\nmutation\n",
            encoding="utf-8",
            newline="\n",
        )
        trusted.BINDING_MODE = "protected-main"
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "plugin tree"):
            self.verify()

    def test_rejects_changed_cases_and_evaluator_on_protected_main(self) -> None:
        self.sign()
        trusted.BINDING_MODE = "protected-main"
        for relative, expected_message in (
            ("tests/forward-cases.json", "candidate case set"),
            ("evals/run_forward_eval.py", "candidate evaluator"),
        ):
            with self.subTest(relative=relative):
                path = self.repo / relative
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n")
                    with self.assertRaisesRegex(
                        trusted.legacy.AuthenticationError,
                        expected_message,
                    ):
                        self.verify()
                finally:
                    path.write_bytes(original)

    def test_v11_keeps_legacy_ancestry_in_protected_main_mode(self) -> None:
        baseline = copy_as_committed_repo(self.root / "baseline")
        evidence = build_evidence(baseline, "1.1", self.now)
        tree = run_git(baseline, "rev-parse", "HEAD^{tree}").stdout.strip()
        detached = run_git(baseline, "commit-tree", tree, "-m", "unrelated root").stdout.strip()
        run_git(baseline, "update-ref", "HEAD", detached)
        trusted.BINDING_MODE = "protected-main"
        with self.assertRaisesRegex(trusted.legacy.AuthenticationError, "must be an ancestor"):
            trusted.validate_candidate_binding(baseline, evidence)


if __name__ == "__main__":
    unittest.main()
