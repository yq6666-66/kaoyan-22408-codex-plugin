from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from validate_repository import EXPECTED_SKILLS, validate_repo  # noqa: E402


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contract(self) -> None:
        results = validate_repo(REPO)
        self.assertEqual(len(results), 5)

    def test_manifest_is_skills_only(self) -> None:
        manifest = json.loads(
            (REPO / "plugins/kaoyan-22408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue({"apps", "mcpServers", "hooks"}.isdisjoint(manifest))

    def test_exact_skill_set(self) -> None:
        skills = {
            path.name
            for path in (REPO / "plugins/kaoyan-22408/skills").iterdir()
            if path.is_dir()
        }
        self.assertEqual(skills, EXPECTED_SKILLS)


if __name__ == "__main__":
    unittest.main()
