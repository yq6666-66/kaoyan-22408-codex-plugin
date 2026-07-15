#!/usr/bin/env python3
"""Run isolated Codex route and multi-turn behavior forward evaluations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from common import (
    BEHAVIOR_CASES,
    EVIDENCE,
    PLUGIN,
    REPO,
    ROUTE_CASES,
    cases_sha256,
    evaluator_sha256,
    load_json,
    plugin_tree_sha256,
)


SCHEMAS = REPO / "evals" / "schemas"
REPORT = REPO / "tests" / "forward-eval-report.md"
PRINT_LOCK = threading.Lock()


class EvaluationError(RuntimeError):
    pass


def log(message: str) -> None:
    with PRINT_LOCK:
        print(message, flush=True)


def resolve_codex(command: str, *, platform: str = os.name) -> str:
    """Prefer an executable Windows shim instead of an extensionless npm file."""
    candidate = Path(command)
    is_bare_name = candidate.name == command and not candidate.suffix
    if platform == "nt" and is_bare_name:
        for suffix in (".cmd", ".exe"):
            resolved = shutil.which(f"{command}{suffix}")
            if resolved:
                return resolved
    return shutil.which(command) or command


def run_checked(command: list[str], cwd: Path = REPO) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise EvaluationError(f"command failed ({completed.returncode}): {' '.join(command)}\n{detail[-4000:]}")
    return completed.stdout.strip()


def relevant_inputs_are_clean() -> bool:
    paths = [
        "plugins/kaoyan-22408",
        "tests/forward-cases.json",
        "tests/behavior-cases.json",
        "evals",
    ]
    output = run_checked(["git", "status", "--porcelain", "--", *paths])
    return not output


def validate_case_sets(route_data: dict[str, Any], behavior_data: dict[str, Any]) -> None:
    if route_data.get("schemaVersion") != "1.1" or len(route_data.get("cases", [])) != 36:
        raise EvaluationError("route cases must use schemaVersion 1.1 and contain exactly 36 cases")
    if behavior_data.get("schemaVersion") != "1.1" or len(behavior_data.get("cases", [])) != 12:
        raise EvaluationError("behavior cases must use schemaVersion 1.1 and contain exactly 12 cases")
    route_ids = [case.get("id") for case in route_data["cases"]]
    behavior_ids = [case.get("id") for case in behavior_data["cases"]]
    if len(route_ids) != len(set(route_ids)) or len(behavior_ids) != len(set(behavior_ids)):
        raise EvaluationError("evaluation case IDs must be unique")


def prepare_workspace(root: Path) -> Path:
    workspace = root / "workspace"
    shutil.copytree(PLUGIN, workspace / "plugin")
    shutil.copytree(SCHEMAS, workspace / "schemas")
    return workspace


def structured_call(
    *,
    codex: str,
    model: str,
    service_tier: str,
    prompt: str,
    schema: Path,
    workspace: Path,
    result_path: Path,
    timeout: int,
) -> dict[str, Any]:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    if result_path.exists():
        result_path.unlink()
    command = [
        codex,
        "exec",
        "--config",
        f'service_tier="{service_tier}"',
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(result_path),
        "--cd",
        str(workspace),
        "--json",
        "--model",
        model,
        "-",
    ]
    env = os.environ.copy()
    env.update({"NO_COLOR": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    completed = subprocess.run(
        command,
        input=prompt,
        cwd=workspace,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise EvaluationError(f"Codex call failed ({completed.returncode}): {detail[-6000:]}")
    if not result_path.is_file():
        raise EvaluationError("Codex did not write --output-last-message")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"Codex returned invalid structured JSON: {exc}") from exc
    schema_data = load_json(schema)
    errors = list(Draft202012Validator(schema_data).iter_errors(result))
    if errors:
        raise EvaluationError(f"Codex output violates schema: {errors[0].message}")
    return result


def cached_call(
    *,
    cache_path: Path,
    no_cache: bool,
    schema: Path,
    retries: int,
    **kwargs: Any,
) -> dict[str, Any]:
    if cache_path.is_file() and not no_cache:
        cached = load_json(cache_path)
        errors = list(Draft202012Validator(load_json(schema)).iter_errors(cached))
        if not errors:
            return cached
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            result = structured_call(schema=schema, **kwargs)
            break
        except (EvaluationError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            log(f"[RETRY] structured call attempt {attempt + 1} failed: {exc}")
            time.sleep(min(2 ** attempt, 4))
    else:  # pragma: no cover - the loop always breaks or raises
        raise EvaluationError(f"structured call failed: {last_error}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(cache_path)
    return result


def route_prompt(case: dict[str, Any]) -> str:
    return f"""你正在使用当前目录中的纯 Skills 插件完成真实用户请求。
先读取 plugin/.codex-plugin/plugin.json、plugin/references/capability-routing-contract.md，以及需要比较的 Skill frontmatter；只选择一个主责 Skill。
不要读取或猜测任何测试期望。根据插件自己的路由边界，给出主责 Skill、简短理由和实际响应的第一段预览。

用户请求：
{case['prompt']}
"""


def behavior_prompt(case: dict[str, Any]) -> str:
    transcript = "\n".join(
        f"{turn['role']}: {turn['content']}" for turn in case["transcript"]
    )
    return f"""你正在使用当前目录中的纯 Skills 插件处理一段会话。
先读取 plugin/.codex-plugin/plugin.json、plugin/references/capability-routing-contract.md，并按所选 Skill 的条件加载说明读取其他契约。
根据最后一个用户意图选择唯一主责 Skill，然后直接给出本轮完整回复。遵守当前会话、无写入、无长期记忆、来源与版权边界。
recordTypes 只列出回复中实际生成的便携记录类型；evidenceTags 只列出回复中实际出现的证据标签。

会话：
{transcript}
"""


def judge_prompt(case: dict[str, Any], actor: dict[str, Any]) -> str:
    rubric = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(case["rubric"]))
    actor_json = json.dumps(actor, ensure_ascii=False, indent=2)
    return f"""你是独立验收员。当前目录含被测插件，但你与生成回复的代理没有共享上下文。
核对主责 Skill 和回复是否满足下面全部标准。每条 criteria 必须按原顺序逐条复制标准文本，给出可在回复中定位的证据；不得因措辞友好而放宽边界。
只有主责 Skill 正确且全部标准通过时，passed 才能为 true。

预期主责 Skill：{case['expectedPrimary']}

验收标准：
{rubric}

被测代理结构化输出：
{actor_json}
"""


def evaluate_route_case(
    case: dict[str, Any],
    *,
    codex: str,
    model: str,
    workspace: Path,
    results_dir: Path,
    cache_dir: Path,
    no_cache: bool,
    timeout: int,
    retries: int,
) -> dict[str, Any]:
    output = cached_call(
        cache_path=cache_dir / "routes" / f"{case['id']}.json",
        no_cache=no_cache,
        retries=retries,
        codex=codex,
        model=model,
        prompt=route_prompt(case),
        schema=workspace / "schemas" / "route-output.schema.json",
        workspace=workspace,
        result_path=results_dir / "routes" / f"{case['id']}.json",
        timeout=timeout,
    )
    passed = output["primarySkill"] == case["expectedPrimary"]
    log(f"[{'PASS' if passed else 'FAIL'}] route {case['id']}: {output['primarySkill']}")
    return {
        "id": case["id"],
        "expected_primary": case["expectedPrimary"],
        "actual_primary": output["primarySkill"],
        "passed": passed,
        "rationale": output["rationale"],
        "response_preview": output["responsePreview"],
    }


def evaluate_behavior_case(
    case: dict[str, Any],
    *,
    codex: str,
    model: str,
    workspace: Path,
    results_dir: Path,
    cache_dir: Path,
    no_cache: bool,
    timeout: int,
    retries: int,
) -> dict[str, Any]:
    actor = cached_call(
        cache_path=cache_dir / "actors" / f"{case['id']}.json",
        no_cache=no_cache,
        retries=retries,
        codex=codex,
        model=model,
        prompt=behavior_prompt(case),
        schema=workspace / "schemas" / "behavior-output.schema.json",
        workspace=workspace,
        result_path=results_dir / "actors" / f"{case['id']}.json",
        timeout=timeout,
    )
    judge = cached_call(
        cache_path=cache_dir / "judges" / f"{case['id']}.json",
        no_cache=no_cache,
        retries=retries,
        codex=codex,
        model=model,
        prompt=judge_prompt(case, actor),
        schema=workspace / "schemas" / "judge-output.schema.json",
        workspace=workspace,
        result_path=results_dir / "judges" / f"{case['id']}.json",
        timeout=timeout,
    )
    criteria = judge.get("criteria", [])
    rubric_matches = (
        len(criteria) == len(case["rubric"])
        and [criterion.get("criterion") for criterion in criteria] == case["rubric"]
    )
    passed = (
        actor["primarySkill"] == case["expectedPrimary"]
        and judge["primarySkillPassed"] is True
        and rubric_matches
        and all(item.get("passed") is True for item in criteria)
        and judge["passed"] is True
    )
    log(f"[{'PASS' if passed else 'FAIL'}] behavior {case['id']}: {actor['primarySkill']}")
    return {
        "id": case["id"],
        "expected_primary": case["expectedPrimary"],
        "actual_primary": actor["primarySkill"],
        "actor_response": actor["response"],
        "record_types": actor["recordTypes"],
        "evidence_tags": actor["evidenceTags"],
        "judge": judge,
        "passed": passed,
    }


def render_report(evidence: dict[str, Any]) -> str:
    version = load_json(PLUGIN / ".codex-plugin" / "plugin.json")["version"]
    failed_routes = [item["id"] for item in evidence["route_results"] if not item["passed"]]
    failed_behaviors = [item["id"] for item in evidence["behavior_results"] if not item["passed"]]
    route_failures = "、".join(failed_routes) if failed_routes else "无"
    behavior_failures = "、".join(failed_behaviors) if failed_behaviors else "无"
    return f"""# v{version} 动态前向评测报告

- 生成时间：{evidence['generated_at']}
- Codex：{evidence['codex_version']}
- 模型：{evidence['model']}
- 服务层级：{evidence['service_tier']}
- 源提交：{evidence['source_revision']}
- 插件树 SHA-256：`{evidence['plugin_tree_sha256']}`
- 测试集 SHA-256：`{evidence['cases_sha256']}`
- 评测器 SHA-256：`{evidence['evaluator_sha256']}`

## 结果

| 门禁 | 通过 | 总数 | 失败项 |
| --- | ---: | ---: | --- |
| 主路由 | {evidence['route_summary']['passed']} | {evidence['route_summary']['total']} | {route_failures} |
| 多轮行为 | {evidence['behavior_summary']['passed']} | {evidence['behavior_summary']['total']} | {behavior_failures} |

评测代理只读取临时只读工作区中的最终插件树；36 个路由场景直接比较主责 Skill，12 个行为场景由独立新上下文逐条按 rubric 复核。CI 不调用模型，只验证机器证据、当前插件树和测试集哈希一致，且证据未超过 30 天。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Codex model identifier; required for a full run")
    parser.add_argument(
        "--service-tier",
        choices=("fast", "flex"),
        default="fast",
        help="CLI-compatible service tier; explicitly overrides the host config",
    )
    parser.add_argument("--codex", default="codex", help="Codex executable")
    parser.add_argument("--workers", type=int, default=2, choices=range(1, 5))
    parser.add_argument("--timeout", type=int, default=900, help="seconds per Codex call")
    parser.add_argument("--retries", type=int, default=2, choices=range(0, 6))
    parser.add_argument("--cache-dir", type=Path, default=REPO / ".cache" / "forward-eval")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()

    route_data = load_json(ROUTE_CASES)
    behavior_data = load_json(BEHAVIOR_CASES)
    validate_case_sets(route_data, behavior_data)
    plugin_hash = plugin_tree_sha256()
    case_hash = cases_sha256()
    evaluator_hash = evaluator_sha256()
    print(f"plugin_tree_sha256={plugin_hash}")
    print(f"cases_sha256={case_hash}")
    print(f"evaluator_sha256={evaluator_hash}")
    if args.dry_run:
        print("[OK] dry run: 36 route cases and 12 behavior cases are structurally valid")
        return 0
    if not args.model:
        parser.error("--model is required unless --dry-run is used")
    if not args.allow_dirty and not relevant_inputs_are_clean():
        raise EvaluationError("plugin, cases, or eval harness is dirty; commit inputs before official evaluation")

    codex = resolve_codex(args.codex)
    codex_version = run_checked([codex, "--version"])
    source_revision = run_checked(["git", "rev-parse", "HEAD"])
    runtime_hash = hashlib.sha256(
        f"{codex_version}\0{args.model}\0{args.service_tier}".encode("utf-8")
    ).hexdigest()[:16]
    cache_key = f"{plugin_hash}-{case_hash}-{evaluator_hash}-{runtime_hash}"
    cache_dir = args.cache_dir.resolve() / cache_key

    with tempfile.TemporaryDirectory(prefix="kaoyan-22408-forward-eval-") as temporary:
        root = Path(temporary)
        workspace = prepare_workspace(root)
        results_dir = root / "results"
        common = {
            "codex": codex,
            "model": args.model,
            "service_tier": args.service_tier,
            "workspace": workspace,
            "results_dir": results_dir,
            "cache_dir": cache_dir,
            "no_cache": args.no_cache,
            "timeout": args.timeout,
            "retries": args.retries,
        }
        route_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(evaluate_route_case, case, **common): case["id"]
                for case in route_data["cases"]
            }
            for future in as_completed(futures):
                route_results.append(future.result())
        route_results.sort(key=lambda item: item["id"])

        behavior_results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(evaluate_behavior_case, case, **common): case["id"]
                for case in behavior_data["cases"]
            }
            for future in as_completed(futures):
                behavior_results.append(future.result())
        behavior_results.sort(key=lambda item: item["id"])

    route_passed = sum(item["passed"] for item in route_results)
    behavior_passed = sum(item["passed"] for item in behavior_results)
    evidence = {
        "schema_version": "1.1",
        "complete": True,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_revision": source_revision,
        "plugin_tree_sha256": plugin_hash,
        "cases_sha256": case_hash,
        "evaluator_sha256": evaluator_hash,
        "codex_version": codex_version,
        "model": args.model,
        "service_tier": args.service_tier,
        "route_summary": {"passed": route_passed, "total": 36},
        "behavior_summary": {"passed": behavior_passed, "total": 12},
        "route_results": route_results,
        "behavior_results": behavior_results,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.report.write_text(render_report(evidence), encoding="utf-8", newline="\n")
    print(f"[RESULT] route={route_passed}/36 behavior={behavior_passed}/12")
    print(f"[RESULT] evidence={args.evidence}")
    if route_passed != 36 or behavior_passed != 12:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvaluationError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
