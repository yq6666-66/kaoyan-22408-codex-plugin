from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "configure_obsidian_brain.py"
sys.path.insert(0, str(REPO / "scripts"))

import configure_obsidian_brain as brain  # noqa: E402


class ObsidianBrainConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.vault = self.root / "vault"
        (self.vault / "00-系统").mkdir(parents=True)
        (self.vault / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
        (self.vault / "00-系统" / "知识库索引.md").write_text(
            "# 知识库索引\n\n## 项目\n\n暂无。\n",
            encoding="utf-8",
        )
        (self.vault / "00-系统" / "成长日志.md").write_text(
            "# 成长日志\n",
            encoding="utf-8",
        )
        self.config = self.root / "config" / "brain.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--config", str(self.config), *arguments],
            cwd=REPO,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )

    def test_configure_check_disable_enable_and_idempotence(self) -> None:
        first = self.run_cli("configure", "--vault", str(self.vault))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        data = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertTrue(data["enabled"])
        self.assertEqual(data["schemaVersion"], "1.1")
        self.assertEqual(data["projectRoot"], "20-项目/408考研")
        self.assertEqual(data["knowledgeRoot"], "30-知识/408考研")
        self.assertEqual(data["pastPaperRoot"], "40-真题/408考研")
        project = self.vault / "20-项目" / "408考研"
        for name in ("主页.md", "学习档案.md", "当前进度.md", "错题队列.md", "记忆索引.md"):
            self.assertTrue((project / name).is_file())

        second = self.run_cli("configure", "--vault", str(self.vault))
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        index = (self.vault / "00-系统" / "知识库索引.md").read_text(encoding="utf-8")
        self.assertEqual(index.count("kaoyan-408-brain"), 1)
        self.assertTrue((self.vault / "40-真题" / "408考研" / "真题索引.md").is_file())

        disabled = self.run_cli("disable")
        self.assertEqual(disabled.returncode, 0, disabled.stdout + disabled.stderr)
        self.assertFalse(json.loads(self.config.read_text(encoding="utf-8"))["enabled"])
        enabled = self.run_cli("enable")
        self.assertEqual(enabled.returncode, 0, enabled.stdout + enabled.stderr)
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("[OK] enabled: true", checked.stdout)

    def test_dry_run_changes_nothing(self) -> None:
        result = self.run_cli(
            "configure",
            "--vault",
            str(self.vault),
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.vault / "20-项目").exists())

    def test_path_traversal_is_rejected(self) -> None:
        result = self.run_cli(
            "configure",
            "--vault",
            str(self.vault),
            "--project-root",
            "../escape",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsafe path segment", result.stdout)
        self.assertFalse((self.root / "escape").exists())

    def test_damaged_json_is_rejected(self) -> None:
        self.config.parent.mkdir(parents=True)
        self.config.write_text("{broken", encoding="utf-8")
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid config JSON", result.stdout)

    def test_write_failure_is_reported_without_traceback(self) -> None:
        args = brain.build_parser().parse_args(
            [
                "--config",
                str(self.config),
                "configure",
                "--vault",
                str(self.vault),
            ]
        )
        with patch.object(
            brain,
            "_atomic_write",
            side_effect=brain.BrainConfigError("read-only Vault"),
        ):
            with self.assertRaisesRegex(brain.BrainConfigError, "read-only Vault"):
                args.handler(args)

    def test_migrate_preserves_legacy_paths_and_config(self) -> None:
        legacy_project = self.vault / "20-项目" / "考研 22408"
        legacy_knowledge = self.vault / "30-知识" / "考研 22408"
        legacy_project.mkdir(parents=True)
        legacy_knowledge.mkdir(parents=True)
        (legacy_project / "主页.md").write_text("# 旧主页\n", encoding="utf-8")
        legacy = self.root / "legacy.json"
        legacy.write_text(json.dumps({
            "schemaVersion": "1.0",
            "enabled": True,
            "vaultPath": str(self.vault.resolve()),
            "projectRoot": "20-项目/考研 22408",
            "writeMode": "auto-structured",
            "retrievalScope": "project-first",
        }, ensure_ascii=False), encoding="utf-8")
        result = self.run_cli("migrate", "--legacy-config", str(legacy))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        migrated = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(migrated["projectRoot"], "20-项目/考研 22408")
        self.assertEqual(migrated["knowledgeRoot"], "30-知识/考研 22408")
        self.assertTrue(legacy.is_file())
        self.assertIn("kaoyan-408-brain", (legacy_project / "主页.md").read_text(encoding="utf-8"))

    def test_symbolic_link_vault_is_rejected(self) -> None:
        link = self.root / "vault-link"
        try:
            os.symlink(self.vault, link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symbolic links unavailable: {exc}")
        result = self.run_cli("configure", "--vault", str(link))
        self.assertEqual(result.returncode, 1)
        self.assertIn("symbolic link", result.stdout)


if __name__ == "__main__":
    unittest.main()
