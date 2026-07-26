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

    def test_behavior_sensitive_skills_state_explicit_contracts(self) -> None:
        skills = REPO / "plugins/kaoyan-22408/skills"
        mock = (skills / "kaoyan-mock-exam-coach/SKILL.md").read_text(
            encoding="utf-8"
        )
        material = (
            skills / "kaoyan-material-study-assistant/SKILL.md"
        ).read_text(encoding="utf-8")
        tutor_408 = (skills / "kaoyan-408-tutor/SKILL.md").read_text(
            encoding="utf-8"
        )
        diagnostician = (
            skills / "kaoyan-progress-diagnostician/SKILL.md"
        ).read_text(encoding="utf-8")
        planner = (skills / "kaoyan-22408-planner/SKILL.md").read_text(
            encoding="utf-8"
        )
        error_loop = (skills / "kaoyan-error-loop-coach/SKILL.md").read_text(
            encoding="utf-8"
        )
        english = (skills / "kaoyan-english2-coach/SKILL.md").read_text(
            encoding="utf-8"
        )
        official = (
            skills / "kaoyan-official-info-researcher/SKILL.md"
        ).read_text(encoding="utf-8")
        past_paper = (
            skills / "kaoyan-past-paper-analyst/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("交卷时回报实际用时", mock)
        self.assertIn("不得写成“可附用时”", mock)
        self.assertIn("不下载、补齐、搜索或重建", material)
        self.assertIn("没有跨会话长期记忆，也没有后台学习状态", material)
        self.assertIn("必须另起“模型讲解”段落", tutor_408)
        self.assertIn("不得放在 `[用户材料]` 标签之下", tutor_408)
        self.assertIn("相对周期不是已提供的绝对日期", diagnostician)
        self.assertIn("不得根据当前系统日期自行推定", diagnostician)
        self.assertIn("用户未说明当前阶段时写 `null`", planner)
        self.assertIn("支持/证伪后的双向更新规则", error_loop)
        self.assertIn("不能因此把另一端自动称为“短期”", english)
        self.assertIn("标题为“必须修正”和“可选提升”的两个清单", english)
        self.assertIn("传递：[待核验] 暂无可传递的已核验结论", official)
        self.assertIn("必须建立 Markdown 样本覆盖表", past_paper)
        self.assertIn("每条趋势同时写支持样本数", past_paper)

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
