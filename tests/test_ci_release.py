Exit code: 0
Wall time: 1.1 seconds
Output:
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ci"))

from release_metadata import metadata  # noqa: E402
from verify_reproducible import release_pair  # noqa: E402


class ReleaseCiTests(unittest.TestCase):
    ACTION_SHAS = {
        "actions/checkout": "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
        "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    }

    @staticmethod
    def workflow_documents() -> list[tuple[Path, dict]]:
        paths = sorted((REPO / ".github/workflows").glob("*.yml"))
        paths += sorted((REPO / ".github/workflows").glob("*.yaml"))
        return [
            (path, yaml.safe_load(path.read_text(encoding="utf-8")))
            for path in paths
        ]

    def test_ci_uses_only_offline_quality_gates(self) -> None:
        workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("Run offline quality gates", workflow)
        self.assertIn("python scripts/check.py --verify-system-evidence", workflow)
        self.assertIn("python scripts/build_release.py", workflow)
        self.assertNotIn("forward-eval", workflow)
        self.assertNotIn("trusted_forward", workflow)
        self.assertNotIn("ALLOWED_SIGNERS", workflow)
        self.assertNotIn("codex exec", workflow)
        self.assertNotIn("--evidence-binding-mode", workflow)
        self.assertIn(
            'git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main',
            workflow,
        )

    def test_obsolete_authenticated_evidence_workflow_is_absent(self) -> None:
        self.assertFalse(
            (REPO / ".github/workflows/authenticated-forward-evidence.yml").exists()
        )

    def test_actions_are_pinned_to_the_approved_node24_commits(self) -> None:
        seen: set[str] = set()
        for path, document in self.workflow_documents():
            for job in document.get("jobs", {}).values():
                for step in job.get("steps", []):
                    uses = step.get("uses")
                    if not uses or uses.startswith("./"):
                        continue
                    action, separator, reference = uses.partition("@")
                    self.assertTrue(separator, f"{path}: unpinned action {uses}")
                    self.assertIn(action, self.ACTION_SHAS, f"{path}: unapproved action {action}")
                    self.assertEqual(
                        reference,
                        self.ACTION_SHAS[action],
                        f"{path}: {action} must use the exact approved commit",
                    )
                    self.assertRegex(reference, r"^[0-9a-f]{40}$")
                    seen.add(action)
        self.assertEqual(seen, set(self.ACTION_SHAS))

    def test_metadata_is_derived_from_manifest(self) -> None:
        values = metadata("ubuntu")
        manifest = json.loads(
            (REPO / "plugins/kaoyan-22408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        version = manifest["version"]
        self.assertEqual(values["version"], version)
        self.assertEqual(values["tag"], f"v{version}")
        self.assertEqual(values["archive"], f"kaoyan-22408-{version}.zip")
        self.assertEqual(values["artifact"], f"kaoyan-22408-{version}-ubuntu")

    def test_release_pair_verifies_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / metadata()["archive"]
            archive.write_bytes(b"same bytes")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            checksum = archive.with_name(archive.name + ".sha256")
            checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8", newline="\n")
            found_archive, found_checksum, found_digest = release_pair(directory)
            self.assertEqual(found_archive, archive)
            self.assertEqual(found_checksum, checksum)
            self.assertEqual(found_digest, digest)

    def test_release_pair_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / metadata()["archive"]
            archive.write_bytes(b"tampered")
            checksum = archive.with_name(archive.name + ".sha256")
            checksum.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release_pair(directory)


if __name__ == "__main__":
    unittest.main()

