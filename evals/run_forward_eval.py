#!/usr/bin/env python3
"""Run isolated Codex route and multi-turn behavior forward evaluations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from jsonschema import Draft202012Validator

from common import (
    BEHAVIOR_CASES,
    EVIDENCE,
    EVIDENCE_SCHEMA,
    PLUGIN,
    REPO,
    RESPONSE_MANIFEST,
    ROUTE_CASES,
    cases_sha256,
    evaluator_sha256,
    load_json,
    plugin_tree_sha256,
)
from forward_attestation import (
    AuthenticationError,
    canonical_json_bytes,
    structured_response_manifest,
    validate_evidence,
    validate_response_manifest,
)


SCHEMAS = REPO / "evals" / "schemas"
REPORT = REPO / "tests" / "forward-eval-report.md"
PRINT_LOCK = threading.Lock()
ABORT_EVENT = threading.Event()
PROCESS_LOCK = threading.Lock()
ACTIVE_PROCESSES: set[subprocess.Popen[str]] = set()


class EvaluationError(RuntimeError):
    pass


class NonRetryableEvaluationError(EvaluationError):
    pass


def is_non_retryable_runtime_failure(detail: str) -> bool:
    normalized = detail.casefold()
    return any(
        marker in normalized
        for marker in (
            "you've hit your usage limit",
            "insufficient_quota",
            "billing_hard_limit_reached",
            "insufficient credits",
        )
    )


def log(message: str) -> None:
    with PRINT_LOCK:
        print(message, flush=True)


def register_process(process: subprocess.Popen[str]) -> None:
    with PROCESS_LOCK:
        ACTIVE_PROCESSES.add(process)


def unregister_process(process: subprocess.Popen[str]) -> None:
    with PROCESS_LOCK:
        ACTIVE_PROCESSES.discard(process)


def terminate_process_tree(
    process: subprocess.Popen[str],
    *,
    platform: str = os.name,
    grace_seconds: float = 2.0,
) -> None:
    """Terminate one managed Codex process and all descendants."""
    if platform == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    else:
        process_group = process.pid
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if platform == "nt":
        # taskkill /T /F is the tree kill; process.kill() only covers the leader.
        try:
            process.kill()
        except ProcessLookupError:
            pass
    else:
        try:
            process.wait(timeout=grace_seconds)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass


def terminate_active_processes(
    *,
    exclude: subprocess.Popen[str] | None = None,
) -> None:
    with PROCESS_LOCK:
        processes = [process for process in ACTIVE_PROCESSES if process is not exclude]
    for process in processes:
        try:
            terminate_process_tree(process)
        finally:
            unregister_process(process)


def managed_popen(
    command: list[str],
    **kwargs: Any,
) -> subprocess.Popen[str]:
    """Launch a process in its own tree so another worker can stop it."""
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    # Serialize the abort check, spawn, and registration.  Otherwise an abort
    # can observe an empty registry between Popen() and register_process().
    with PROCESS_LOCK:
        if ABORT_EVENT.is_set():
            raise NonRetryableEvaluationError("evaluation aborted before process launch")
        process = subprocess.Popen(command, **kwargs)
        ACTIVE_PROCESSES.add(process)
    return process


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


def isolated_config_arguments() -> list[str]:
    """Disable every nonessential agent feature in the temporary Codex home."""
    arguments: list[str] = []
    for feature in (
        "apps",
        "memories",
        "multi_agent",
        "plugins",
        "shell_snapshot",
        "shell_tool",
    ):
        arguments.extend(["--disable", feature])
    return arguments


def prepare_isolated_codex_home(root: Path, source_home: Path | None = None) -> Path:
    """Create a minimal temporary home containing only the CLI login material."""
    source = source_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    auth = source / "auth.json"
    if not auth.is_file() or auth.is_symlink():
        raise EvaluationError("Codex auth.json is unavailable; run `codex login` before evaluation")
    destination = root / "codex-home"
    destination.mkdir(mode=0o700, parents=True)
    target = destination / "auth.json"
    shutil.copyfile(auth, target)
    target.chmod(0o600)
    return destination


def isolated_environment(codex_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CODEX_HOME": str(codex_home),
            "HOME": str(codex_home),
            "USERPROFILE": str(codex_home),
        }
    )
    return env


def verify_mcp_isolation(
    codex: str,
    arguments: list[str],
    service_tier: str,
    codex_home: Path,
) -> None:
    """Fail closed if the masked CLI listing still reports an enabled MCP server."""
    env = isolated_environment(codex_home)
    output = run_checked(
        [
            codex,
            "mcp",
            "list",
            "--config",
            f'service_tier="{service_tier}"',
            *arguments,
        ],
        env=env,
    )
    if re.search(r"(?m)\s+enabled\s+", output):
        raise EvaluationError("one or more global MCP servers remain enabled")


def run_checked(
    command: list[str],
    cwd: Path = REPO,
    env: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
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


def source_revision_matches_inputs(revision: str) -> bool:
    """Require the evaluated commit to contain every current relevant input."""
    relevant = [
        "plugins/kaoyan-22408",
        "tests/forward-cases.json",
        "tests/behavior-cases.json",
        "evals",
    ]
    checks = [
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        ["git", "diff", "--quiet", revision, "HEAD", "--", *relevant],
    ]
    for command in checks:
        if subprocess.run(
            command,
            cwd=REPO,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode != 0:
            return False
    return relevant_inputs_are_clean()


def prepare_input_snapshot(root: Path, revision: str) -> Path:
    """Materialize committed evaluation inputs without rereading the live tree."""
    snapshot = root / "input-snapshot"
    prefixes = [
        "plugins/kaoyan-22408",
        "tests/forward-cases.json",
        "tests/behavior-cases.json",
        "evals",
    ]
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", revision, "--", *prefixes],
        cwd=REPO,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if listing.returncode != 0:
        detail = listing.stderr.decode("utf-8", "replace").strip()
        raise EvaluationError(f"cannot snapshot evaluation inputs: {detail}")
    entries = [entry for entry in listing.stdout.split(b"\0") if entry]
    if not entries:
        raise EvaluationError("committed evaluation input snapshot is empty")
    for entry in entries:
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
            relative_text = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise EvaluationError("Git returned a malformed evaluation snapshot entry") from exc
        relative = PurePosixPath(relative_text)
        if (
            object_type != "blob"
            or mode not in {"100644", "100755"}
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise EvaluationError(f"unsupported evaluation snapshot entry: {relative_text}")
        blob = subprocess.run(
            ["git", "cat-file", "blob", object_id],
            cwd=REPO,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if blob.returncode != 0:
            detail = blob.stderr.decode("utf-8", "replace").strip()
            raise EvaluationError(f"cannot read evaluation snapshot blob {object_id}: {detail}")
        target = snapshot / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob.stdout)
    return snapshot


def validate_case_sets(route_data: dict[str, Any], behavior_data: dict[str, Any]) -> None:
    if route_data.get("schemaVersion") != "1.3" or len(route_data.get("cases", [])) != 60:
        raise EvaluationError("route cases must use schemaVersion 1.3 and contain exactly 60 cases")
    if behavior_data.get("schemaVersion") != "1.3" or len(behavior_data.get("cases", [])) != 36:
        raise EvaluationError("behavior cases must use schemaVersion 1.3 and contain exactly 36 cases")
    route_ids = [case.get("id") for case in route_data["cases"]]
    behavior_ids = [case.get("id") for case in behavior_data["cases"]]
    if len(route_ids) != len(set(route_ids)) or len(behavior_ids) != len(set(behavior_ids)):
        raise EvaluationError("evaluation case IDs must be unique")
    for case in behavior_data["cases"]:
        host_context = case.get("hostContext")
        if host_context is not None and (
            not isinstance(host_context, str) or not host_context.strip()
        ):
            raise EvaluationError(
                f"{case.get('id', '<unknown>')}: hostContext must be a non-empty string"
            )


def prepare_workspace(root: Path, snapshot: Path) -> Path:
    workspace = root / "workspace"
    shutil.copytree(snapshot / "plugins" / "kaoyan-22408", workspace / "plugin")
    shutil.copytree(snapshot / "evals" / "schemas", workspace / "schemas")
    return workspace


def plugin_prompt_context(plugin: Path = PLUGIN, *, full: bool) -> str:
    """Embed only hash-bound plugin inputs so actors never need filesystem tools."""
    files: list[Path] = [
        plugin / ".codex-plugin" / "plugin.json",
        plugin / "references" / "capability-routing-contract.md",
    ]
    if full:
        files.extend(sorted((plugin / "references").glob("*")))
        files.extend(sorted((plugin / "skills").glob("*/SKILL.md")))
    else:
        for skill_file in sorted((plugin / "skills").glob("*/SKILL.md")):
            text = skill_file.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            if len(parts) != 3:
                raise EvaluationError(f"Skill frontmatter is malformed: {skill_file}")
            files.append(skill_file)

    sections: list[str] = []
    seen: set[Path] = set()
    for path in files:
        if path in seen or not path.is_file() or path.is_symlink():
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        if not full and path.name == "SKILL.md":
            text = f"---{text.split('---', 2)[1]}---"
        relative = path.relative_to(plugin).as_posix()
        sections.append(f"===== {relative} =====\n{text}")
    return "\n\n".join(sections)


def structured_call(
    *,
    codex: str,
    model: str,
    service_tier: str,
    isolated_config: list[str],
    codex_home: Path,
    prompt: str,
    schema: Path,
    workspace: Path,
    result_path: Path,
    timeout: int,
) -> dict[str, Any]:
    if ABORT_EVENT.is_set():
        raise NonRetryableEvaluationError("evaluation aborted after a non-retryable runtime failure")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    if result_path.exists():
        result_path.unlink()
    command = [
        codex,
        "exec",
        "--config",
        f'service_tier="{service_tier}"',
        *isolated_config,
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
    env = isolated_environment(codex_home)
    env.update(
        {
            "NO_COLOR": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    process = managed_popen(
        command,
        cwd=workspace,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        try:
            stdout, stderr = process.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            terminate_process_tree(process)
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(
                command,
                timeout,
                output=stdout,
                stderr=stderr,
            ) from exc
        detail = "\n".join(
            part.strip()
            for part in (stdout, stderr)
            if part and part.strip()
        )
        if is_non_retryable_runtime_failure(detail):
            ABORT_EVENT.set()
            terminate_active_processes(exclude=process)
            raise NonRetryableEvaluationError(
                f"Codex runtime reported a non-retryable account limit: {detail[-2000:]}"
            )
        if process.returncode != 0:
            raise EvaluationError(f"Codex call failed ({process.returncode}): {detail[-6000:]}")
    finally:
        if process.poll() is None:
            terminate_process_tree(process)
        unregister_process(process)
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
        if ABORT_EVENT.is_set():
            raise NonRetryableEvaluationError("evaluation aborted after a non-retryable runtime failure")
        try:
            result = structured_call(schema=schema, **kwargs)
            break
        except NonRetryableEvaluationError:
            ABORT_EVENT.set()
            raise
        except (EvaluationError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            if ABORT_EVENT.is_set():
                raise NonRetryableEvaluationError(
                    "evaluation aborted after a non-retryable runtime failure"
                ) from exc
            if attempt >= retries:
                raise
            log(f"[RETRY] structured call attempt {attempt + 1} failed: {exc}")
            time.sleep(min(2 ** attempt, 4))
    else:  # pragma: no cover - the loop always breaks or raises
        raise EvaluationError(f"structured call failed: {last_error}")
    if not no_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(cache_path)
    return result


def stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def evaluate_cases_parallel(
    cases: list[dict[str, Any]],
    evaluator: Callable[..., dict[str, Any]],
    *,
    workers: int,
    common: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run cases while cancelling pending work and process trees on failure."""
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {
        executor.submit(evaluator, case, **common): case["id"]
        for case in cases
    }
    results: list[dict[str, Any]] = []
    try:
        for future in as_completed(futures):
            results.append(future.result())
    except BaseException:
        ABORT_EVENT.set()
        for future in futures:
            future.cancel()
        terminate_active_processes()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    executor.shutdown(wait=True, cancel_futures=True)
    results.sort(key=lambda item: item["id"])
    return results


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def publish_evidence_artifacts(
    evidence: dict[str, Any],
    *,
    version: str,
    evidence_path: Path,
    response_manifest_path: Path,
    report_path: Path,
) -> None:
    """Validate the complete bundle before atomically replacing any artifact."""
    manifest = structured_response_manifest(evidence)
    validate_evidence(REPO, evidence)
    validate_response_manifest(evidence, manifest)
    evidence_bytes = (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_bytes = canonical_json_bytes(manifest)
    report_bytes = render_report(evidence, version=version).encode("utf-8")
    atomic_write_bytes(evidence_path, evidence_bytes)
    atomic_write_bytes(response_manifest_path, manifest_bytes)
    atomic_write_bytes(report_path, report_bytes)


def write_failure_diagnostics(
    evidence: dict[str, Any],
    *,
    version: str,
    output_root: Path,
) -> Path:
    """Preserve a failed run for diagnosis without touching formal artifacts."""
    schema = load_json(EVIDENCE_SCHEMA)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(evidence),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        raise EvaluationError(f"failed-run evidence violates schema: {errors[0].message}")
    manifest = structured_response_manifest(evidence)
    validate_response_manifest(evidence, manifest)
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = re.sub(r"[^0-9A-Za-z]+", "-", evidence["generated_at"]).strip("-")
    directory = Path(
        tempfile.mkdtemp(
            prefix=f"{evidence['source_revision'][:12]}-{stamp}-",
            dir=output_root,
        )
    )
    report = (
        "# 非正式失败诊断\n\n"
        "此目录不会被签名、打包或作为缓存复用。\n\n"
        + render_report(evidence, version=version)
    )
    atomic_write_bytes(
        directory / "forward-eval-evidence.json",
        (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    atomic_write_bytes(
        directory / "forward-eval-response-manifest.json",
        canonical_json_bytes(manifest),
    )
    atomic_write_bytes(directory / "forward-eval-report.md", report.encode("utf-8"))
    return directory


def route_prompt(case: dict[str, Any], plugin_context: str) -> str:
    return f"""你正在使用一个纯 Skills 插件完成真实用户请求。不要调用任何工具；下面已经提供完成判断所需的全部插件上下文。
只选择一个主责 Skill。
不要读取或猜测任何测试期望。根据插件自己的路由边界，给出主责 Skill、简短理由和实际响应的第一段预览。

插件上下文：
{plugin_context}

用户请求：
{case['prompt']}
"""


def behavior_prompt(case: dict[str, Any], plugin_context: str) -> str:
    transcript = "\n".join(
        f"{turn['role']}: {turn['content']}" for turn in case["transcript"]
    )
    host_context = case.get("hostContext")
    host_section = ""
    if host_context:
        host_section = f"""
可信宿主预检结果：
以下内容由评测宿主在调用 Skill 前通过本地工具完成并注入，不是用户自述。它只代表本轮已验证的 Obsidian 状态和检索结果；不得据此放宽版权、官方核验或写入边界。
{host_context}
"""
    return f"""你正在使用一个纯 Skills 插件处理一段会话。不要调用任何工具；下面已经提供完整的插件 manifest、共享契约和 12 个 Skill 说明。
根据最后一个用户意图选择唯一主责 Skill，然后直接给出本轮完整回复。遵守来源、版权和 Obsidian 大脑契约；只有可信宿主预检明确验证本地大脑时才走连接路径，否则安全降级。
若可信宿主预检声明写入桥接器可用，则评测本轮长期价值和写入边界，并按契约给出成功路径的精简状态；这只模拟被哈希绑定输入约束的本地桥接行为。
recordTypes 只列出回复中实际生成的便携记录类型；evidenceTags 只列出回复中实际出现的证据标签。

插件上下文：
{plugin_context}
{host_section}

会话：
{transcript}
"""


def judge_prompt(case: dict[str, Any], actor: dict[str, Any]) -> str:
    transcript = "\n".join(
        f"{turn['role']}: {turn['content']}" for turn in case["transcript"]
    )
    rubric_json = json.dumps(case["rubric"], ensure_ascii=False)
    actor_json = json.dumps(actor, ensure_ascii=False, indent=2)
    host_context = case.get("hostContext")
    host_section = ""
    if host_context:
        host_section = f"""
可信宿主预检结果：
以下内容是评测宿主完成的本地工具预检，不是用户陈述；可以据此判断本轮 Obsidian 是否已连接、读取了什么以及写入桥接器是否可用。
{host_context}
"""
    return f"""你是独立验收员，与生成回复的代理没有共享上下文。不要调用任何工具；只根据下列原始会话、验收标准和被测输出判断。
核对主责 Skill 和回复是否满足下面全部标准。每条 criteria[].criterion 必须逐字复制验收标准 JSON 数组中对应的字符串，不得添加编号、项目符号、前后缀或改写，并给出可在回复中定位的证据；不得因措辞友好而放宽边界。
判断用户是否提供了日期、材料、题面或既有 rubric 时，必须以原始会话为准，不得只根据被测回复猜测。
只有主责 Skill 正确且全部标准通过时，passed 才能为 true。

预期主责 Skill：{case['expectedPrimary']}

原始会话：
{transcript}
{host_section}

验收标准 JSON 数组：
{rubric_json}

被测代理结构化输出：
{actor_json}
"""


def evaluate_route_case(
    case: dict[str, Any],
    *,
    codex: str,
    model: str,
    service_tier: str,
    isolated_config: list[str],
    codex_home: Path,
    plugin_context: str,
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
        service_tier=service_tier,
        isolated_config=isolated_config,
        codex_home=codex_home,
        prompt=route_prompt(case, plugin_context),
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
    service_tier: str,
    isolated_config: list[str],
    codex_home: Path,
    plugin_context: str,
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
        service_tier=service_tier,
        isolated_config=isolated_config,
        codex_home=codex_home,
        prompt=behavior_prompt(case, plugin_context),
        schema=workspace / "schemas" / "behavior-output.schema.json",
        workspace=workspace,
        result_path=results_dir / "actors" / f"{case['id']}.json",
        timeout=timeout,
    )
    actor = {
        **actor,
        "recordTypes": stable_unique(actor["recordTypes"]),
        "evidenceTags": stable_unique(actor["evidenceTags"]),
    }
    judge = cached_call(
        cache_path=cache_dir / "judges" / f"{case['id']}.json",
        no_cache=no_cache,
        retries=retries,
        codex=codex,
        model=model,
        service_tier=service_tier,
        isolated_config=isolated_config,
        codex_home=codex_home,
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


def render_report(evidence: dict[str, Any], *, version: str | None = None) -> str:
    version = version or load_json(PLUGIN / ".codex-plugin" / "plugin.json")["version"]
    failed_routes = [item["id"] for item in evidence["route_results"] if not item["passed"]]
    failed_behaviors = [item["id"] for item in evidence["behavior_results"] if not item["passed"]]
    route_failures = "、".join(failed_routes) if failed_routes else "无"
    behavior_failures = "、".join(failed_behaviors) if failed_behaviors else "无"
    return f"""# v{version} 动态前向评测报告

- 生成时间：{evidence['generated_at']}
- Codex：{evidence['codex_version']}
- 模型：{evidence['model']}
- 服务层级：{evidence['service_tier']}
- 缓存模式：{evidence['cache_mode']}
- 源提交：{evidence['source_revision']}
- 插件树 SHA-256：`{evidence['plugin_tree_sha256']}`
- 测试集 SHA-256：`{evidence['cases_sha256']}`
- 评测器 SHA-256：`{evidence['evaluator_sha256']}`

## 结果

| 门禁 | 通过 | 总数 | 失败项 |
| --- | ---: | ---: | --- |
| 主路由 | {evidence['route_summary']['passed']} | {evidence['route_summary']['total']} | {route_failures} |
| 多轮行为 | {evidence['behavior_summary']['passed']} | {evidence['behavior_summary']['total']} | {behavior_failures} |

评测代理只读取临时只读工作区中的最终插件树；60 个路由场景直接比较主责 Skill，36 个行为场景由独立新上下文逐条按 rubric 复核。仓库内一致性检查不认证模型运行来源；正式 PR 与 Release 门禁还要求维护者离线签名，并由受保护基分支中的可信验证器使用候选 checkout 之外固定的公钥验证。签名有效期最长 30 天。
"""


def main() -> int:
    ABORT_EVENT.clear()
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
    parser.add_argument("--response-manifest", type=Path, default=RESPONSE_MANIFEST)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument(
        "--failure-output-dir",
        type=Path,
        default=REPO / ".cache" / "forward-eval-failures",
    )
    args = parser.parse_args()

    if args.dry_run:
        route_data = load_json(ROUTE_CASES)
        behavior_data = load_json(BEHAVIOR_CASES)
        validate_case_sets(route_data, behavior_data)
        print(f"plugin_tree_sha256={plugin_tree_sha256()}")
        print(f"cases_sha256={cases_sha256()}")
        print(f"evaluator_sha256={evaluator_sha256()}")
        print("[OK] dry run: 60 route cases and 36 behavior cases are structurally valid")
        return 0
    if not args.model:
        parser.error("--model is required unless --dry-run is used")
    if not args.no_cache:
        parser.error("--no-cache is required for every non-dry-run evaluation")
    if args.allow_dirty:
        raise EvaluationError("--allow-dirty cannot produce formal evidence")
    if not relevant_inputs_are_clean():
        raise EvaluationError("plugin, cases, or eval harness is dirty; commit inputs before official evaluation")

    codex = resolve_codex(args.codex)
    isolated_config = isolated_config_arguments()
    codex_version = run_checked([codex, "--version"])
    source_revision = run_checked(["git", "rev-parse", "HEAD"])
    if not source_revision_matches_inputs(source_revision):
        raise EvaluationError("source revision does not contain the clean evaluation inputs")

    with tempfile.TemporaryDirectory(prefix="kaoyan-22408-forward-eval-") as temporary:
        root = Path(temporary)
        snapshot = prepare_input_snapshot(root, source_revision)
        snapshot_plugin = snapshot / "plugins" / "kaoyan-22408"
        snapshot_routes = snapshot / "tests" / "forward-cases.json"
        snapshot_behaviors = snapshot / "tests" / "behavior-cases.json"
        snapshot_evals = snapshot / "evals"
        route_data = load_json(snapshot_routes)
        behavior_data = load_json(snapshot_behaviors)
        validate_case_sets(route_data, behavior_data)
        plugin_hash = plugin_tree_sha256(snapshot_plugin)
        case_hash = cases_sha256(snapshot_routes, snapshot_behaviors)
        evaluator_hash = evaluator_sha256(snapshot_evals, relative_to=snapshot)
        print(f"plugin_tree_sha256={plugin_hash}")
        print(f"cases_sha256={case_hash}")
        print(f"evaluator_sha256={evaluator_hash}")
        runtime_hash = hashlib.sha256(
            f"{codex_version}\0{args.model}\0{args.service_tier}".encode("utf-8")
        ).hexdigest()[:16]
        cache_key = f"{plugin_hash}-{case_hash}-{evaluator_hash}-{runtime_hash}"
        cache_dir = args.cache_dir.resolve() / cache_key
        codex_home = prepare_isolated_codex_home(root)
        verify_mcp_isolation(codex, isolated_config, args.service_tier, codex_home)
        workspace = prepare_workspace(root, snapshot)
        results_dir = root / "results"
        common = {
            "codex": codex,
            "model": args.model,
            "service_tier": args.service_tier,
            "isolated_config": isolated_config,
            "codex_home": codex_home,
            "workspace": workspace,
            "results_dir": results_dir,
            "cache_dir": cache_dir,
            "no_cache": args.no_cache,
            "timeout": args.timeout,
            "retries": args.retries,
        }
        snapshot_workspace_plugin = workspace / "plugin"
        route_common = {
            **common,
            "plugin_context": plugin_prompt_context(snapshot_workspace_plugin, full=False),
        }
        behavior_common = {
            **common,
            "plugin_context": plugin_prompt_context(snapshot_workspace_plugin, full=True),
        }
        route_results = evaluate_cases_parallel(
            route_data["cases"],
            evaluate_route_case,
            workers=args.workers,
            common=route_common,
        )
        behavior_results = evaluate_cases_parallel(
            behavior_data["cases"],
            evaluate_behavior_case,
            workers=args.workers,
            common=behavior_common,
        )
        if (
            not source_revision_matches_inputs(source_revision)
            or plugin_tree_sha256() != plugin_hash
            or cases_sha256() != case_hash
            or evaluator_sha256() != evaluator_hash
        ):
            raise EvaluationError("evaluation inputs changed while the immutable snapshot was running")
        plugin_version = load_json(snapshot_plugin / ".codex-plugin" / "plugin.json")["version"]

    route_passed = sum(item["passed"] for item in route_results)
    behavior_passed = sum(item["passed"] for item in behavior_results)
    evidence = {
        "schema_version": "1.3",
        "complete": True,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_revision": source_revision,
        "plugin_tree_sha256": plugin_hash,
        "cases_sha256": case_hash,
        "evaluator_sha256": evaluator_hash,
        "codex_version": codex_version,
        "model": args.model,
        "service_tier": args.service_tier,
        "cache_mode": "disabled",
        "route_summary": {"passed": route_passed, "total": 60},
        "behavior_summary": {"passed": behavior_passed, "total": 36},
        "route_results": route_results,
        "behavior_results": behavior_results,
    }
    print(f"[RESULT] route={route_passed}/60 behavior={behavior_passed}/36")
    if route_passed != 60 or behavior_passed != 36:
        failure_directory = write_failure_diagnostics(
            evidence,
            version=plugin_version,
            output_root=args.failure_output_dir.resolve(),
        )
        print("[RESULT] formal evidence artifacts were not replaced")
        print(f"[RESULT] failure diagnostics={failure_directory}")
        return 1
    publish_evidence_artifacts(
        evidence,
        version=plugin_version,
        evidence_path=args.evidence,
        response_manifest_path=args.response_manifest,
        report_path=args.report,
    )
    print(f"[RESULT] evidence={args.evidence}")
    print(f"[RESULT] structured_response_manifest={args.response_manifest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        AuthenticationError,
        EvaluationError,
        OSError,
        ValueError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
