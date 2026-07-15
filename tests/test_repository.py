from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from validate_repository import (  # noqa: E402
    ALLOWED_RELEASE_FILES,
    EXPECTED_SKILLS,
    ValidationError,
    check_behavior_cases,
    check_forward_cases,
    check_portable_schema,
    check_progress_accuracy_semantics,
    validate_repo,
)


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contract(self) -> None:
        results = validate_repo(REPO, verify_evidence=False, scan_history=False)
        self.assertEqual(len(results), 6)

    def test_manifest_is_release_semver_and_skills_only(self) -> None:
        manifest = json.loads(
            (REPO / "plugins/kaoyan-22408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue({"apps", "mcpServers", "hooks"}.isdisjoint(manifest))

    def test_exact_skill_and_release_file_sets(self) -> None:
        plugin = REPO / "plugins/kaoyan-22408"
        skills = {path.name for path in (plugin / "skills").iterdir() if path.is_dir()}
        files = {
            path.relative_to(plugin).as_posix()
            for path in plugin.rglob("*")
            if path.is_file()
        }
        self.assertEqual(skills, EXPECTED_SKILLS)
        self.assertEqual(files, set(ALLOWED_RELEASE_FILES))

    def test_schema_and_eval_case_contracts(self) -> None:
        plugin = REPO / "plugins/kaoyan-22408"
        check_portable_schema(plugin)
        check_forward_cases(REPO)
        check_behavior_cases(REPO)

    def test_accuracy_semantics_reject_impossible_or_inconsistent_values(self) -> None:
        base = {
            "schemaVersion": "1.1",
            "recordType": "ProgressSnapshot",
            "period": {"start": None, "end": None},
            "metrics": [],
            "blockers": [],
        }
        check_progress_accuracy_semantics(
            {**base, "accuracy": [{"subject": "english2", "correct": 16, "total": 20, "rate": 0.8}]}
        )
        with self.assertRaisesRegex(ValidationError, "must not exceed"):
            check_progress_accuracy_semantics(
                {**base, "accuracy": [{"subject": "english2", "correct": 21, "total": 20, "rate": 1.0}]}
            )
        with self.assertRaisesRegex(ValidationError, "must equal"):
            check_progress_accuracy_semantics(
                {**base, "accuracy": [{"subject": "english2", "correct": 16, "total": 20, "rate": 0.7}]}
            )


if __name__ == "__main__":
    unittest.main()
