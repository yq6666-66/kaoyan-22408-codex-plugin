from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "evals"))

from common import (  # noqa: E402
    BEHAVIOR_CASES,
    ROUTE_CASES,
    cases_sha256,
    evaluator_sha256,
    load_json,
    plugin_tree_sha256,
)
from verify_forward_evidence import EvidenceError, verify_evidence  # noqa: E402
from run_forward_eval import (  # noqa: E402
    isolated_config_arguments,
    plugin_prompt_context,
    prepare_isolated_codex_home,
    resolve_codex,
)


def valid_evidence() -> dict:
    routes = load_json(ROUTE_CASES)["cases"]
    behaviors = load_json(BEHAVIOR_CASES)["cases"]
    return {
        "schema_version": "1.1",
        "complete": True,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_revision": "0" * 40,
        "plugin_tree_sha256": plugin_tree_sha256(),
        "cases_sha256": cases_sha256(),
        "evaluator_sha256": evaluator_sha256(),
        "codex_version": "codex-cli test",
        "model": "test-model",
        "service_tier": "fast",
        "route_summary": {"passed": 36, "total": 36},
        "behavior_summary": {"passed": 12, "total": 12},
        "route_results": [
            {
                "id": case["id"],
                "expected_primary": case["expectedPrimary"],
                "actual_primary": case["expectedPrimary"],
                "passed": True,
                "rationale": "test",
                "response_preview": "test",
            }
            for case in routes
        ],
        "behavior_results": [
            {
                "id": case["id"],
                "expected_primary": case["expectedPrimary"],
                "actual_primary": case["expectedPrimary"],
                "actor_response": "test",
                "record_types": [],
                "evidence_tags": [],
                "judge": {
                    "passed": True,
                    "primarySkillPassed": True,
                    "criteria": [
                        {"criterion": criterion, "passed": True, "evidence": "test"}
                        for criterion in case["rubric"]
                    ],
                    "summary": "test",
                },
                "passed": True,
            }
            for case in behaviors
        ],
    }


class ForwardEvidenceTests(unittest.TestCase):
    def verify(self, evidence: dict, *, max_age_days: int = 30) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
            return verify_evidence(
                path,
                max_age_days=max_age_days,
                check_source_revision=False,
            )

    def test_accepts_current_complete_evidence(self) -> None:
        result = self.verify(valid_evidence())
        self.assertEqual(result["route_summary"], {"passed": 36, "total": 36})

    def test_rejects_plugin_tree_tampering(self) -> None:
        evidence = valid_evidence()
        evidence["plugin_tree_sha256"] = "f" * 64
        with self.assertRaisesRegex(EvidenceError, "current plugin tree"):
            self.verify(evidence)

    def test_rejects_case_set_tampering(self) -> None:
        evidence = valid_evidence()
        evidence["cases_sha256"] = "f" * 64
        with self.assertRaisesRegex(EvidenceError, "route/behavior cases"):
            self.verify(evidence)

    def test_rejects_evaluator_tampering(self) -> None:
        evidence = valid_evidence()
        evidence["evaluator_sha256"] = "f" * 64
        with self.assertRaisesRegex(EvidenceError, "evaluator harness"):
            self.verify(evidence)

    def test_rejects_unresolvable_source_revision(self) -> None:
        evidence = valid_evidence()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(EvidenceError, "source revision"):
                verify_evidence(path)

    def test_rejects_expired_evidence(self) -> None:
        evidence = valid_evidence()
        evidence["generated_at"] = (
            datetime.now(timezone.utc) - timedelta(days=31)
        ).isoformat().replace("+00:00", "Z")
        with self.assertRaisesRegex(EvidenceError, "older than 30 days"):
            self.verify(evidence)

    def test_rejects_changed_judge_rubric(self) -> None:
        evidence = valid_evidence()
        evidence["behavior_results"][0]["judge"]["criteria"][0]["criterion"] = "changed"
        with self.assertRaisesRegex(EvidenceError, "rubric text/order"):
            self.verify(evidence)

    def test_windows_codex_resolution_uses_executable_shim(self) -> None:
        resolved = resolve_codex("codex", platform="nt")
        self.assertTrue(resolved.casefold().endswith(("codex.cmd", "codex.exe")))

    def test_eval_isolation_uses_minimal_temporary_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "auth.json").write_text('{"auth_mode":"test"}', encoding="utf-8")
            (source / "config.toml").write_text("ignored = true", encoding="utf-8")
            (source / "models_cache.json").write_text("{}", encoding="utf-8")
            isolated = prepare_isolated_codex_home(root / "run", source)
            self.assertEqual({path.name for path in isolated.iterdir()}, {"auth.json"})
            self.assertEqual(
                (isolated / "auth.json").read_text(encoding="utf-8"),
                '{"auth_mode":"test"}',
            )
        arguments = isolated_config_arguments()
        self.assertIn("plugins", arguments)
        self.assertIn("shell_tool", arguments)

    def test_prompt_context_is_plugin_only_and_tool_free(self) -> None:
        route_context = plugin_prompt_context(full=False)
        behavior_context = plugin_prompt_context(full=True)
        self.assertIn("capability-routing-contract.md", route_context)
        self.assertIn("kaoyan-review-executor", route_context)
        self.assertNotIn("## 展开时段", route_context)
        self.assertIn("## 展开时段", behavior_context)
        self.assertNotIn("expectedPrimary", behavior_context)
        self.assertNotIn("tests/", behavior_context)


if __name__ == "__main__":
    unittest.main()
