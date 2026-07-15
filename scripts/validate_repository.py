#!/usr/bin/env python3
"""Validate the public repository and the Skills-only release contract."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_SKILLS = {
    "kaoyan-22408-planner",
    "kaoyan-review-executor",
    "kaoyan-progress-diagnostician",
    "kaoyan-error-loop-coach",
    "kaoyan-mock-exam-coach",
    "kaoyan-408-tutor",
    "kaoyan-math2-coach",
    "kaoyan-english2-coach",
    "kaoyan-politics-coach",
    "kaoyan-past-paper-analyst",
    "kaoyan-material-study-assistant",
    "kaoyan-official-info-researcher",
}

EXPECTED_REFERENCES = {
    "capability-routing-contract.md",
    "evidence-copyright-contract.md",
    "portable-learning-records.md",
}

ALLOWED_PLUGIN_ROOTS = {".codex-plugin", "skills", "references", "assets"}
FORBIDDEN_PATH_PARTS = {"app", "android", "corpus", "raw", "index", "user"}
PLACEHOLDER = "TO" + "DO"


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"无法读取 JSON：{path}: {exc}") from exc


def parse_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    require(lines and lines[0] == "---", f"缺少 YAML frontmatter：{path}")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError(f"frontmatter 未闭合：{path}") from exc

    values: dict[str, str] = {}
    for line in lines[1:end]:
        require(":" in line, f"无效 frontmatter 行：{path}: {line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    require(set(values) == {"name", "description"}, f"frontmatter 只能包含 name/description：{path}")
    return values


def check_manifest(plugin: Path) -> None:
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    manifest = load_json(manifest_path)
    require(manifest.get("name") == "kaoyan-22408", "manifest name 必须为 kaoyan-22408")
    require(manifest.get("version") == "1.0.0", "manifest version 必须为 1.0.0")
    require(manifest.get("skills") == "./skills/", "manifest skills 路径错误")
    for key in ("apps", "mcpServers", "hooks"):
        require(key not in manifest, f"Skills-only manifest 不得包含 {key}")

    interface = manifest.get("interface")
    require(isinstance(interface, dict), "manifest 缺少 interface")
    require(interface.get("category") == "Education", "插件分类必须为 Education")
    require("screenshots" not in interface, "Skills-only 插件不应声明截图")
    prompts = interface.get("defaultPrompt")
    require(isinstance(prompts, list) and 1 <= len(prompts) <= 3, "Starter Prompts 必须为 1 至 3 条")
    require(all(isinstance(item, str) and len(item) <= 128 for item in prompts), "Starter Prompt 超过 128 字符")
    for key in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        require(str(interface.get(key, "")).startswith("https://"), f"{key} 必须为 HTTPS URL")
    for key in ("composerIcon", "logo"):
        rel = interface.get(key)
        require(isinstance(rel, str) and rel.startswith("./"), f"{key} 必须为相对路径")
        require((plugin / rel[2:]).is_file(), f"{key} 指向的文件不存在")


def check_skill(skill_dir: Path) -> None:
    name = skill_dir.name
    expected_files = {"SKILL.md", "agents/openai.yaml"}
    actual_files = {
        path.relative_to(skill_dir).as_posix()
        for path in skill_dir.rglob("*")
        if path.is_file()
    }
    require(actual_files == expected_files, f"{name} 只能包含 SKILL.md 与 agents/openai.yaml")

    skill_path = skill_dir / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(skill_path)
    require(metadata["name"] == name, f"Skill 名称与目录不一致：{name}")
    require(len(metadata["description"]) >= 25, f"Skill description 过短：{name}")
    require(PLACEHOLDER not in content.upper(), f"Skill 含未完成占位符：{name}")
    for reference in EXPECTED_REFERENCES:
        require(reference in content, f"{name} 未引用共享契约 {reference}")

    yaml_path = skill_dir / "agents" / "openai.yaml"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    require(PLACEHOLDER not in yaml_text.upper(), f"openai.yaml 含未完成占位符：{name}")
    fields: dict[str, str] = {}
    pattern = re.compile(r'^  (display_name|short_description|default_prompt): "(.*)"$')
    for line in yaml_text.splitlines():
        match = pattern.match(line)
        if match:
            fields[match.group(1)] = match.group(2)
    require(set(fields) == {"display_name", "short_description", "default_prompt"}, f"openai.yaml 字段无效：{name}")
    require(25 <= len(fields["short_description"]) <= 64, f"short_description 长度应为 25 至 64：{name}")
    require(f"${name}" in fields["default_prompt"], f"default_prompt 必须显式包含 ${name}")


def check_links(plugin: Path) -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    plugin_resolved = plugin.resolve()
    for md_path in plugin.rglob("*.md"):
        for target in link_pattern.findall(md_path.read_text(encoding="utf-8")):
            clean = target.split("#", 1)[0].strip()
            if not clean or clean.startswith(("https://", "http://", "mailto:")):
                continue
            resolved = (md_path.parent / clean).resolve()
            require(resolved == plugin_resolved or plugin_resolved in resolved.parents, f"引用越出插件目录：{md_path}: {target}")
            require(resolved.exists(), f"引用文件不存在：{md_path}: {target}")


def check_release_tree(plugin: Path) -> None:
    roots = {path.name for path in plugin.iterdir()}
    require(roots == ALLOWED_PLUGIN_ROOTS, f"插件根目录不符合发布允许列表：{sorted(roots)}")
    require((plugin / "assets" / "kaoyan-22408.svg").is_file(), "缺少正式 SVG Logo")
    require({p.name for p in (plugin / "assets").iterdir()} == {"kaoyan-22408.svg"}, "assets 只能包含正式 SVG Logo")
    require({p.name for p in (plugin / "references").iterdir()} == EXPECTED_REFERENCES, "共享契约必须恰好为三份")

    for path in plugin.rglob("*"):
        require(not path.is_symlink(), f"发布树不得包含符号链接：{path}")
        relative = path.relative_to(plugin)
        lowered_parts = {part.lower() for part in relative.parts}
        require(not (lowered_parts & FORBIDDEN_PATH_PARTS), f"发布树含禁止路径：{relative}")

    local_user_path = r"(?i)(?:[a-z]:\\" + "users" + r"\\|/" + "users" + r"/|/home/[^/\s]+/)"
    forbidden_content = [
        re.compile(r"(?i)\b(?:baidu|netdisk|localstorage|study-state)\b"),
        re.compile(local_user_path),
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|figd_[A-Za-z0-9_-]{20,})\b"),
        re.compile(r"(?i)\b(?:api[_ -]?key|access[_ -]?token|cookie)\s*[:=]\s*[^\s]{8,}"),
    ]
    for path in plugin.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        require(PLACEHOLDER not in text.upper(), f"发布文件含未完成占位符：{path.relative_to(plugin)}")
        for pattern in forbidden_content:
            require(not pattern.search(text), f"发布文件含敏感或旧系统残留：{path.relative_to(plugin)}")


def check_scenarios(repo: Path) -> None:
    submission = load_json(repo / "submission" / "test-cases.json")
    require(set(submission) == {"schemaVersion", "positive", "negative"}, "提交测试集字段错误")
    require(len(submission["positive"]) == 5, "提交测试集必须恰好有 5 个正向场景")
    require(len(submission["negative"]) == 3, "提交测试集必须恰好有 3 个负向场景")
    ids = [case.get("id") for group in ("positive", "negative") for case in submission[group]]
    require(len(ids) == len(set(ids)), "提交测试场景 ID 重复")
    required_case_fields = {"id", "prompt", "expectedBehavior", "expectedResultShape", "fixture"}
    for group in ("positive", "negative"):
        for case in submission[group]:
            require(required_case_fields <= set(case), f"提交测试场景字段不完整：{case.get('id')}")

    forward = load_json(repo / "tests" / "forward-cases.json")
    require(forward.get("schemaVersion") == "1.0", "前向测试版本错误")
    cases = forward.get("cases")
    require(isinstance(cases, list) and len(cases) == 36, "前向测试必须恰好有 36 个场景")
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for case in cases:
        skill = case.get("skillUnderTest")
        kind = case.get("kind")
        require(skill in EXPECTED_SKILLS, f"前向测试包含未知 Skill：{skill}")
        require(kind in {"positive", "conflict"}, f"前向测试类型错误：{case.get('id')}")
        require(case.get("expectedPrimary") in EXPECTED_SKILLS, f"前向测试主路由错误：{case.get('id')}")
        require(isinstance(case.get("prompt"), str) and case["prompt"].strip(), f"前向测试缺少 prompt：{case.get('id')}")
        require(isinstance(case.get("expectedBehavior"), list) and case["expectedBehavior"], f"前向测试缺少行为断言：{case.get('id')}")
        if kind == "positive":
            require(case["expectedPrimary"] == skill, f"正向场景未路由到被测 Skill：{case.get('id')}")
        else:
            require(case.get("expectedNotPrimary") == skill, f"冲突场景必须排除被测 Skill：{case.get('id')}")
            require(case["expectedPrimary"] != skill, f"冲突场景仍路由到被测 Skill：{case.get('id')}")
        counts[skill][kind] += 1
    for skill in EXPECTED_SKILLS:
        require(counts[skill] == Counter({"positive": 2, "conflict": 1}), f"{skill} 必须有 2 正向 + 1 冲突场景")


def check_repository_docs(repo: Path) -> None:
    required = {
        "README.md",
        "LICENSE",
        "PRIVACY.md",
        "TERMS.md",
        "SECURITY.md",
        "THIRD_PARTY_CONTENT.md",
        ".agents/plugins/marketplace.json",
        "submission/listing.json",
        "submission/test-cases.json",
        "submission/release-notes.md",
        "tests/forward-eval-report.md",
    }
    for relative in required:
        require((repo / relative).is_file(), f"缺少仓库文件：{relative}")
    marketplace = load_json(repo / ".agents" / "plugins" / "marketplace.json")
    require(marketplace.get("name") == "kaoyan-22408", "marketplace 名称错误")
    plugins = marketplace.get("plugins")
    require(isinstance(plugins, list) and len(plugins) == 1, "marketplace 必须只有一个插件条目")
    require(plugins[0].get("category") == "Education", "marketplace 分类错误")
    require(plugins[0].get("source", {}).get("path") == "./plugins/kaoyan-22408", "marketplace source.path 错误")

    listing = load_json(repo / "submission" / "listing.json")
    require(listing.get("slug") == "kaoyan-22408", "提交 listing slug 错误")
    require(listing.get("category") == "Education", "提交 listing 分类错误")
    require(listing.get("regions") == "all-available", "提交 listing 地区设置错误")
    require(listing.get("screenshots") == [], "Skills-only listing 不应包含截图")


def validate_repo(repo: Path | None = None) -> list[str]:
    repo = (repo or Path(__file__).resolve().parents[1]).resolve()
    plugin = repo / "plugins" / "kaoyan-22408"
    require(plugin.is_dir(), f"插件目录不存在：{plugin}")

    check_repository_docs(repo)
    check_manifest(plugin)
    check_release_tree(plugin)

    skill_dirs = {path.name: path for path in (plugin / "skills").iterdir() if path.is_dir()}
    require(set(skill_dirs) == EXPECTED_SKILLS, "Skill 集合必须与 v1.0 设计完全一致")
    for name in sorted(EXPECTED_SKILLS):
        check_skill(skill_dirs[name])
    check_links(plugin)
    check_scenarios(repo)
    return [
        "manifest 与 marketplace 通过",
        "12 个 Skills 与 openai.yaml 通过",
        "三份共享契约与引用通过",
        "发布允许列表与敏感残留检查通过",
        "36 个前向场景及 5+3 提交测试集通过",
    ]


def main() -> int:
    try:
        results = validate_repo()
    except ValidationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    for result in results:
        print(f"[OK] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
