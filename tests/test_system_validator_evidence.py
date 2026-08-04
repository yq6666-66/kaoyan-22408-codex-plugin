from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from run_system_validators import (  # noqa: E402
    EvidenceError,
    current_plugin_tree_hash,
    verify_evidence,
)
from validate_repository import EXPECTED_SKILLS  # noqa: E402


class SystemValidatorEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "evidence.json"
        self.now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        manifest = json.loads(
            (REPO / "plugins/kaoyan-408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.evidence = {
            "schemaVersion": "1.1",
            "generatedAt": self.now.isoformat().replace("+00:00", "Z"),
            "plugin": {
                "name": "kaoyan-408",
                "version": manifest["version"],
                "treeSha256": current_plugin_tree_hash(REPO),
            },
            "runtime": {"pythonVersion": "3.13.0"},
            "validators": {
                "plugin": {
                    "mode": "spec-backed-repository",
                    "source": "scripts/validate_repository.py",
                    "sha256": hashlib.sha256(
                        (REPO / "scripts/validate_repository.py").read_bytes()
                    ).hexdigest(),
                    "specSource": "plugin-creator/references/plugin-json-spec.md",
                    "specSha256": "a" * 64,
                    "standaloneOfficialValidatorAvailable": False,
                },
                "skill": {
                    "source": "skill-creator/scripts/quick_validate.py",
                    "sha256": "b" * 64,
                },
            },
            "results": {
                "plugin": {"passed": True, "exitCode": 0},
                "skills": {
                    name: {"passed": True, "exitCode": 0}
                    for name in sorted(EXPECTED_SKILLS)
                },
            },
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, document: dict[str, object]) -> None:
        self.path.write_text(json.dumps(document), encoding="utf-8")

    def test_current_complete_evidence_passes(self) -> None:
        self.write(self.evidence)
        verified = verify_evidence(REPO, self.path, now=self.now)
        self.assertEqual(verified["plugin"]["treeSha256"], current_plugin_tree_hash(REPO))

    def test_stale_evidence_is_rejected(self) -> None:
        stale = deepcopy(self.evidence)
        stale["generatedAt"] = (self.now - timedelta(days=31)).isoformat().replace("+00:00", "Z")
        self.write(stale)
        with self.assertRaisesRegex(EvidenceError, "older"):
            verify_evidence(REPO, self.path, now=self.now)

    def test_tree_hash_tampering_is_rejected(self) -> None:
        tampered = deepcopy(self.evidence)
        tampered["plugin"]["treeSha256"] = "0" * 64
        self.write(tampered)
        with self.assertRaisesRegex(EvidenceError, "tree hash"):
            verify_evidence(REPO, self.path, now=self.now)

    def test_incomplete_skill_results_are_rejected(self) -> None:
        incomplete = deepcopy(self.evidence)
        incomplete["results"]["skills"].pop(next(iter(EXPECTED_SKILLS)))
        self.write(incomplete)
        with self.assertRaisesRegex(EvidenceError, "exactly 13"):
            verify_evidence(REPO, self.path, now=self.now)

    def test_stale_repository_validator_hash_is_rejected(self) -> None:
        stale = deepcopy(self.evidence)
        stale["validators"]["plugin"]["sha256"] = "0" * 64
        self.write(stale)
        with self.assertRaisesRegex(EvidenceError, "repository validator hash"):
            verify_evidence(REPO, self.path, now=self.now)


if __name__ == "__main__":
    unittest.main()
