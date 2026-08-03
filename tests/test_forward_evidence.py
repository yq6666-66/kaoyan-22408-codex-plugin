from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


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
from forward_attestation import AuthenticationError  # noqa: E402
from verify_forward_evidence import (  # noqa: E402
    EvidenceError,
    source_revision_matches_inputs,
    verify_evidence,
)
from run_forward_eval import (  # noqa: E402
    ABORT_EVENT,
    NonRetryableEvaluationError,
    cached_call,
    evaluate_cases_parallel,
    is_non_retryable_runtime_failure,
    isolated_config_arguments,
    judge_prompt,
    managed_popen,
    plugin_prompt_context,
    prepare_input_snapshot,
    prepare_isolated_codex_home,
    prepare_workspace,
    publish_evidence_artifacts,
    resolve_codex,
    main as run_forward_main,
    stable_unique,
    terminate_active_processes,
    write_failure_diagnostics,
)


def valid_evidence() -> dict:
    routes = load_json(ROUTE_CASES)["cases"]
    behaviors = load_json(BEHAVIOR_CASES)["cases"]
    return {
        "schema_version": "1.3",
        "complete": True,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_revision": "0" * 40,
        "plugin_tree_sha256": plugin_tree_sha256(),
        "cases_sha256": cases_sha256(),
        "evaluator_sha256": evaluator_sha256(),
        "codex_version": "codex-cli test",
        "model": "test-model",
        "service_tier": "fast",
        "cache_mode": "disabled",
        "route_summary": {"passed": 60, "total": 60},
        "behavior_summary": {"passed": 36, "total": 36},
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
    def tearDown(self) -> None:
        ABORT_EVENT.clear()

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
        self.assertEqual(result["route_summary"], {"passed": 60, "total": 60})

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

    def test_rejects_missing_or_enabled_cache_mode(self) -> None:
        missing = valid_evidence()
        missing.pop("cache_mode")
        with self.assertRaisesRegex(EvidenceError, "schema violation"):
            self.verify(missing)
        enabled = valid_evidence()
        enabled["cache_mode"] = "enabled"
        with self.assertRaisesRegex(EvidenceError, "schema violation"):
            self.verify(enabled)

    def test_consistency_only_mode_does_not_require_source_commit(self) -> None:
        evidence = valid_evidence()
        result = self.verify(evidence)
        self.assertEqual(result["source_revision"], "0" * 40)

    def test_protected_main_binding_is_explicit_and_content_addressed(self) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch("verify_forward_evidence.subprocess.run", return_value=completed) as run:
            self.assertTrue(
                source_revision_matches_inputs("0" * 40, "1.3", "protected-main")
            )
        self.assertEqual(run.call_count, 1)
        self.assertIn("status", run.call_args.args[0])

    def test_default_pr_binding_checks_commit_ancestry_and_relevant_diff(self) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch("verify_forward_evidence.subprocess.run", return_value=completed) as run:
            self.assertTrue(source_revision_matches_inputs("0" * 40, "1.3"))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 4)
        self.assertIn("cat-file", commands[0])
        self.assertIn("merge-base", commands[1])
        self.assertIn("diff", commands[2])
        self.assertIn("status", commands[3])

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
        available = {
            "codex.cmd": r"C:\tools\codex.cmd",
            "codex": "/usr/local/bin/codex",
        }
        with patch(
            "run_forward_eval.shutil.which",
            side_effect=lambda command: available.get(command),
        ) as which:
            resolved = resolve_codex("codex", platform="nt")
        self.assertEqual(resolved, r"C:\tools\codex.cmd")
        self.assertEqual(which.call_args_list[0].args, ("codex.cmd",))

    def test_usage_limit_is_non_retryable_and_stops_after_one_attempt(self) -> None:
        self.assertTrue(
            is_non_retryable_runtime_failure(
                "You've hit your usage limit. Try again at Jul 25th."
            )
        )
        self.assertFalse(is_non_retryable_runtime_failure("temporary transport error"))
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "result.json"
            with patch(
                "run_forward_eval.structured_call",
                side_effect=NonRetryableEvaluationError("usage limit"),
            ) as call:
                with self.assertRaisesRegex(NonRetryableEvaluationError, "usage limit"):
                    cached_call(
                        cache_path=cache,
                        no_cache=True,
                        schema=REPO / "evals/schemas/route-output.schema.json",
                        retries=5,
                    )
        self.assertEqual(call.call_count, 1)
        self.assertTrue(ABORT_EVENT.is_set())

    def test_no_cache_neither_reads_nor_writes_cache_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "result.json"
            cache.write_text('{"primarySkill":"stale"}', encoding="utf-8")
            fresh = {
                "primarySkill": "kaoyan-408-tutor",
                "rationale": "fresh",
                "responsePreview": "fresh",
            }
            with patch("run_forward_eval.structured_call", return_value=fresh) as call:
                result = cached_call(
                    cache_path=cache,
                    no_cache=True,
                    schema=REPO / "evals/schemas/route-output.schema.json",
                    retries=0,
                )
            self.assertEqual(result, fresh)
            self.assertEqual(cache.read_text(encoding="utf-8"), '{"primarySkill":"stale"}')
            self.assertEqual(call.call_count, 1)

    def test_full_run_requires_no_cache_before_launching_codex(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["run_forward_eval.py", "--model", "test-model"],
        ):
            with self.assertRaises(SystemExit) as raised:
                run_forward_main()
        self.assertEqual(raised.exception.code, 2)

    def test_fail_fast_terminates_managed_process(self) -> None:
        process = managed_popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            self.assertIsNone(process.poll())
            ABORT_EVENT.set()
            terminate_active_processes()
            process.wait(timeout=5)
            self.assertIsNotNone(process.returncode)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def test_parallel_failure_cancels_pending_cases(self) -> None:
        started: list[str] = []

        def evaluator(case: dict, **_kwargs: object) -> dict:
            started.append(case["id"])
            if case["id"] == "first":
                ABORT_EVENT.set()
                raise NonRetryableEvaluationError("usage limit")
            if ABORT_EVENT.is_set():
                time.sleep(0.2)
                raise NonRetryableEvaluationError("aborted")
            return {"id": case["id"]}

        with self.assertRaises(NonRetryableEvaluationError):
            evaluate_cases_parallel(
                [{"id": "first"}, {"id": "second"}, {"id": "third"}],
                evaluator,
                workers=1,
                common={},
            )
        self.assertTrue(ABORT_EVENT.is_set())
        self.assertNotIn("third", started)

    def test_actor_metadata_stable_deduplication(self) -> None:
        self.assertEqual(stable_unique(["a", "b", "a", "c", "b"]), ["a", "b", "c"])

    def test_invalid_bundle_never_replaces_formal_artifacts(self) -> None:
        evidence = valid_evidence()
        evidence["cache_mode"] = "enabled"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / "evidence.json", root / "manifest.json", root / "report.md"]
            for path in paths:
                path.write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(AuthenticationError, "schema violation"):
                publish_evidence_artifacts(
                    evidence,
                    version="1.3.0",
                    evidence_path=paths[0],
                    response_manifest_path=paths[1],
                    report_path=paths[2],
                )
            self.assertEqual(
                [path.read_text(encoding="utf-8") for path in paths],
                ["sentinel", "sentinel", "sentinel"],
            )

    def test_failed_run_writes_only_nonformal_diagnostics(self) -> None:
        evidence = valid_evidence()
        evidence["route_results"][0]["actual_primary"] = "kaoyan-408-tutor"
        evidence["route_results"][0]["passed"] = False
        evidence["route_summary"] = {"passed": 59, "total": 60}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = write_failure_diagnostics(
                evidence,
                version="1.3.0",
                output_root=root,
            )
            self.assertEqual(directory.parent, root)
            self.assertEqual(
                {path.name for path in directory.iterdir()},
                {
                    "forward-eval-evidence.json",
                    "forward-eval-response-manifest.json",
                    "forward-eval-report.md",
                },
            )
            report = (directory / "forward-eval-report.md").read_text(encoding="utf-8")
            self.assertIn("非正式失败诊断", report)
            self.assertIn("不会被签名、打包或作为缓存复用", report)

    def test_snapshot_workspace_and_prompt_share_committed_bytes(self) -> None:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = prepare_input_snapshot(root, revision)
            workspace = prepare_workspace(root, snapshot)
            snapshot_plugin = snapshot / "plugins" / "kaoyan-22408"
            self.assertEqual(
                plugin_prompt_context(workspace / "plugin", full=True),
                plugin_prompt_context(snapshot_plugin, full=True),
            )

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
        self.assertNotIn("## 展开与恢复", route_context)
        self.assertIn("## 展开与恢复", behavior_context)
        self.assertNotIn("expectedPrimary", behavior_context)
        self.assertNotIn("tests/", behavior_context)

    def test_codex_output_schemas_avoid_unsupported_unique_items(self) -> None:
        for name in (
            "route-output.schema.json",
            "behavior-output.schema.json",
            "judge-output.schema.json",
        ):
            schema = load_json(REPO / "evals" / "schemas" / name)
            stack = [schema]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    self.assertNotIn("uniqueItems", value, name)
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)

    def test_judge_receives_transcript_and_exact_rubric_strings(self) -> None:
        case = load_json(BEHAVIOR_CASES)["cases"][2]
        actor = {
            "primarySkill": case["expectedPrimary"],
            "response": "test response",
            "recordTypes": [],
            "evidenceTags": [],
        }
        prompt = judge_prompt(case, actor)
        self.assertIn(case["transcript"][0]["content"], prompt)
        self.assertIn(json.dumps(case["rubric"], ensure_ascii=False), prompt)
        self.assertIn("不得添加编号", prompt)
        self.assertNotIn(f"1. {case['rubric'][0]}", prompt)


if __name__ == "__main__":
    unittest.main()
