from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "evals"))

from forward_attestation import (  # noqa: E402
    AuthenticationError,
    SIGNATURE_NAMESPACE,
    cases_sha256,
    evaluator_sha256,
    plugin_tree_sha256,
    prepare_statement,
    validate_evidence,
    verify_authenticated_bundle,
)

try:
    from .test_support import copy_as_committed_repo, run_git  # type: ignore[import-not-found]
except ImportError:
    from test_support import copy_as_committed_repo, run_git  # type: ignore[no-redef]


def build_evidence(repo: Path, generated_at: datetime) -> dict:
    route_cases = json.loads(
        (repo / "tests/forward-cases.json").read_text(encoding="utf-8")
    )["cases"]
    behavior_cases = json.loads(
        (repo / "tests/behavior-cases.json").read_text(encoding="utf-8")
    )["cases"]
    return {
        "schema_version": "1.2",
        "complete": True,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "source_revision": run_git(repo, "rev-parse", "HEAD").stdout.strip(),
        "plugin_tree_sha256": plugin_tree_sha256(repo),
        "cases_sha256": cases_sha256(repo),
        "evaluator_sha256": evaluator_sha256(repo),
        "codex_version": "codex-cli attestation-test",
        "model": "test-model",
        "service_tier": "fast",
        "route_summary": {"passed": len(route_cases), "total": len(route_cases)},
        "behavior_summary": {"passed": len(behavior_cases), "total": len(behavior_cases)},
        "route_results": [
            {
                "id": case["id"],
                "expected_primary": case["expectedPrimary"],
                "actual_primary": case["expectedPrimary"],
                "passed": True,
                "rationale": "temporary signing fixture",
                "response_preview": "temporary signing fixture",
            }
            for case in route_cases
        ],
        "behavior_results": [
            {
                "id": case["id"],
                "expected_primary": case["expectedPrimary"],
                "actual_primary": case["expectedPrimary"],
                "actor_response": "temporary signing fixture",
                "record_types": [],
                "evidence_tags": [],
                "judge": {
                    "passed": True,
                    "primarySkillPassed": True,
                    "criteria": [
                        {
                            "criterion": criterion,
                            "passed": True,
                            "evidence": "temporary signing fixture",
                        }
                        for criterion in case["rubric"]
                    ],
                    "summary": "temporary signing fixture",
                },
                "passed": True,
            }
            for case in behavior_cases
        ],
    }


class ForwardAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("ssh-keygen") is None:
            self.skipTest("OpenSSH ssh-keygen is unavailable")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = copy_as_committed_repo(self.root / "repo")
        self.evidence_path = self.repo / "tests/forward-eval-evidence.json"
        self.manifest_path = self.repo / "tests/forward-eval-response-manifest.json"
        self.statement_path = self.repo / "tests/forward-eval-attestation.json"
        self.signature_path = self.repo / "tests/forward-eval-attestation.json.sig"
        self.allowed_signers = self.root / "trusted.allowed_signers"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        evidence = build_evidence(self.repo, self.now)
        self.evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        prepare_statement(
            self.repo,
            self.evidence_path,
            self.manifest_path,
            self.statement_path,
            now=self.now,
        )
        self.private_key = self.root / "maintainer_ed25519"
        self.create_key(self.private_key)
        public_key = self.private_key.with_suffix(".pub").read_text(
            encoding="utf-8"
        ).strip()
        self.allowed_signers.write_text(
            f"yq6666-66 {public_key}\n",
            encoding="utf-8",
            newline="\n",
        )

    @staticmethod
    def create_key(path: Path) -> None:
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
                SIGNATURE_NAMESPACE,
                str(self.statement_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertTrue(self.signature_path.is_file())

    def verify(self, *, now: datetime | None = None) -> dict:
        return verify_authenticated_bundle(
            self.repo,
            self.evidence_path,
            self.manifest_path,
            self.statement_path,
            self.signature_path,
            self.allowed_signers,
            now=now or self.now,
        )

    def test_accepts_external_pinned_signature(self) -> None:
        self.sign()
        evidence = self.verify()
        self.assertEqual(evidence["route_summary"], {"passed": 60, "total": 60})

    def test_rejects_unsigned_bundle(self) -> None:
        with self.assertRaisesRegex(AuthenticationError, "signature is missing"):
            self.verify()

    def test_rejects_evidence_tampering_after_signature(self) -> None:
        self.sign()
        evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        evidence["route_results"][0]["response_preview"] = "tampered after signing"
        self.evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(AuthenticationError, "manifest does not match"):
            self.verify()

    def test_rejects_wrong_external_key(self) -> None:
        self.sign()
        wrong_key = self.root / "wrong_ed25519"
        self.create_key(wrong_key)
        public_key = wrong_key.with_suffix(".pub").read_text(
            encoding="utf-8"
        ).strip()
        self.allowed_signers.write_text(
            f"yq6666-66 {public_key}\n",
            encoding="utf-8",
            newline="\n",
        )
        with self.assertRaisesRegex(AuthenticationError, "signature verification failed"):
            self.verify()

    def test_rejects_candidate_owned_allowed_signers(self) -> None:
        self.sign()
        candidate_owned = self.repo / "tests/allowed_signers"
        candidate_owned.write_bytes(self.allowed_signers.read_bytes())
        with self.assertRaisesRegex(AuthenticationError, "outside the candidate"):
            verify_authenticated_bundle(
                self.repo,
                self.evidence_path,
                self.manifest_path,
                self.statement_path,
                self.signature_path,
                candidate_owned,
                now=self.now,
            )

    def test_rejects_expired_attestation(self) -> None:
        self.sign()
        with self.assertRaisesRegex(AuthenticationError, "expired"):
            self.verify(now=self.now + timedelta(days=31))

    def test_trusted_verifier_never_resolves_candidate_schema_refs(self) -> None:
        requests: list[str] = []

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                requests.append(self.path)
                self.send_response(500)
                self.end_headers()

            def log_message(self, _format: str, *args: object) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), RequestHandler)
        server.timeout = 0.5
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        candidate_schema = self.repo / "evals/schemas/evidence.schema.json"
        candidate_schema.write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$ref": (
                        f"http://127.0.0.1:{server.server_port}/"
                        "candidate-schema.json"
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        try:
            evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))
            validate_evidence(self.repo, evidence)
            thread.join(timeout=2)
        finally:
            server.server_close()
        self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
