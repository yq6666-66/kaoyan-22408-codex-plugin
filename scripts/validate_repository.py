#!/usr/bin/env python3
"""Validate the public Skills-only repository and its release payload."""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError as JsonSchemaValidationError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


PLUGIN_RELATIVE_PATH = PurePosixPath("plugins/kaoyan-22408")
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
    "obsidian-brain-contract.md",
    "notion-brain-contract.md",
    "portable-learning-records.md",
    "portable-learning-records.schema.json",
}

ALLOWED_PLUGIN_ROOTS = {".codex-plugin", "skills", "references", "assets"}
PLACEHOLDER = "TO" + "DO"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
FORBIDDEN_PATH_PARTS = {"app", "android", "corpus", "raw", "index", "user"}
HISTORY_FORBIDDEN_PATH_PARTS = {"app", "android", "corpus", "raw"}

PORTABLE_RECORD_SKILLS = {
    "kaoyan-22408-planner",
    "kaoyan-review-executor",
    "kaoyan-progress-diagnostician",
    "kaoyan-error-loop-coach",
    "kaoyan-mock-exam-coach",
}

EVIDENCE_SKILLS = set(EXPECTED_SKILLS)

OUTPUT_TAG_SKILLS = {
    "[用户材料]": {
        "kaoyan-error-loop-coach",
        "kaoyan-mock-exam-coach",
        "kaoyan-408-tutor",
        "kaoyan-math2-coach",
        "kaoyan-english2-coach",
        "kaoyan-politics-coach",
        "kaoyan-past-paper-analyst",
        "kaoyan-material-study-assistant",
    },
    "[原创练习]": {
        "kaoyan-error-loop-coach",
        "kaoyan-mock-exam-coach",
        "kaoyan-408-tutor",
        "kaoyan-math2-coach",
        "kaoyan-english2-coach",
        "kaoyan-politics-coach",
        "kaoyan-past-paper-analyst",
        "kaoyan-material-study-assistant",
    },
    "[官方核验]": {"kaoyan-official-info-researcher"},
    "[待核验]": {"kaoyan-politics-coach", "kaoyan-official-info-researcher"},
}

LEGACY_PATTERNS = (
    re.compile(r"\b" + "bai" + r"du\b", re.IGNORECASE),
    re.compile(r"\bnet" + r"disk\b", re.IGNORECASE),
    re.compile(r"\blocal" + r"storage\b", re.IGNORECASE),
    re.compile(r"\bstudy" + r"-state\b", re.IGNORECASE),
)

SENSITIVE_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bfigd_[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bnpm_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\baws[_ -]?secret[_ -]?access[_ -]?key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{30,}", re.IGNORECASE),
    re.compile(r"\bAccountKey\s*=\s*[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(r"-----BEGIN PGP " + r"PRIVATE KEY BLOCK-----"),
    re.compile(
        r"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|secret[_ -]?key|cookie)"
        r"\s*[:=]\s*[\"']?[^\s\"']{8,}",
        re.IGNORECASE,
    ),
)

HISTORY_SECRET_PATTERNS = (
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bfigd_[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(rb"\bnpm_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(rb"\baws[_ -]?secret[_ -]?access[_ -]?key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{30,}", re.IGNORECASE),
    re.compile(rb"\bAccountKey\s*=\s*[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE),
    re.compile(
        rb"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|secret[_ -]?key|cookie)"
        rb"\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{16,}",
        re.IGNORECASE,
    ),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(rb"-----BEGIN PGP " + rb"PRIVATE KEY BLOCK-----"),
)

HISTORY_LEGACY_PATTERNS = (
    re.compile(rb"\b" + b"bai" + rb"du\b", re.IGNORECASE),
    re.compile(rb"\bnet" + rb"disk\b", re.IGNORECASE),
    re.compile(rb"\blocal" + rb"storage\b", re.IGNORECASE),
    re.compile(rb"\bstudy" + rb"-state\b", re.IGNORECASE),
)


class ValidationError(RuntimeError):
    """Raised when a repository contract is violated."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read_utf8_text(path: Path, *, require_lf: bool = True) -> str:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    require(b"\x00" not in payload, f"text file contains NUL bytes: {path}")
    if require_lf:
        require(b"\r" not in payload, f"release text must use LF, not CRLF: {path}")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"file is not valid UTF-8: {path}: {exc}") from exc


def load_json(path: Path) -> Any:
    try:
        return json.loads(read_utf8_text(path))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {path}: {exc}") from exc


def load_yaml(path: Path) -> Any:
    try:
        return yaml.load(read_utf8_text(path), Loader=UniqueKeyLoader)
    except (TypeError, yaml.YAMLError) as exc:
        raise ValidationError(f"invalid YAML: {path}: {exc}") from exc


def parse_frontmatter(path: Path) -> dict[str, Any]:
    text = read_utf8_text(path)
    lines = text.splitlines()
    require(lines and lines[0] == "---", f"missing YAML frontmatter: {path}")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValidationError(f"unclosed YAML frontmatter: {path}") from exc
    require(any(line.strip() for line in lines[end + 1 :]), f"empty Skill body: {path}")
    try:
        metadata = yaml.load("\n".join(lines[1:end]), Loader=UniqueKeyLoader)
    except (TypeError, yaml.YAMLError) as exc:
        raise ValidationError(f"invalid YAML frontmatter: {path}: {exc}") from exc
    require(isinstance(metadata, dict), f"frontmatter must be a mapping: {path}")
    require(set(metadata) == {"name", "description"}, f"frontmatter must contain only name/description: {path}")
    require(all(isinstance(value, str) for value in metadata.values()), f"frontmatter values must be strings: {path}")
    return metadata


def expected_release_files() -> frozenset[str]:
    names = {
        ".codex-plugin/plugin.json",
        "assets/kaoyan-22408.svg",
        *(f"references/{name}" for name in EXPECTED_REFERENCES),
    }
    for skill in EXPECTED_SKILLS:
        names.add(f"skills/{skill}/SKILL.md")
        names.add(f"skills/{skill}/agents/openai.yaml")
    return frozenset(names)


ALLOWED_RELEASE_FILES = expected_release_files()


def check_manifest(plugin: Path) -> dict[str, Any]:
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    manifest = load_json(manifest_path)
    require(isinstance(manifest, dict), "plugin manifest must be an object")
    require(manifest.get("name") == "kaoyan-22408", "manifest name must be kaoyan-22408")
    version = manifest.get("version")
    require(isinstance(version, str) and SEMVER.fullmatch(version) is not None, "manifest version must be strict semver")
    require(manifest.get("skills") == "./skills/", "manifest skills path must be ./skills/")
    for key in ("apps", "mcpServers", "hooks"):
        require(key not in manifest, f"Skills-only manifest must not contain {key}")

    interface = manifest.get("interface")
    require(isinstance(interface, dict), "manifest is missing interface")
    require(interface.get("category") == "Education", "manifest category must be Education")
    require("screenshots" not in interface, "Skills-only manifest must not declare screenshots")
    prompts = interface.get("defaultPrompt")
    require(isinstance(prompts, list) and 1 <= len(prompts) <= 3, "defaultPrompt must contain 1 to 3 entries")
    require(
        all(isinstance(item, str) and 1 <= len(item) <= 128 for item in prompts),
        "each defaultPrompt must contain at most 128 characters",
    )
    for key in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        require(str(interface.get(key, "")).startswith("https://"), f"{key} must be an HTTPS URL")
    for key in ("composerIcon", "logo"):
        relative = interface.get(key)
        require(isinstance(relative, str) and relative.startswith("./"), f"{key} must be a relative path")
        require((plugin / relative[2:]).is_file(), f"{key} target does not exist")
    return manifest


def check_skill(skill_dir: Path) -> None:
    name = skill_dir.name
    skill_path = skill_dir / "SKILL.md"
    content = read_utf8_text(skill_path)
    metadata = parse_frontmatter(skill_path)
    require(metadata["name"] == name, f"Skill name does not match directory: {name}")
    require(25 <= len(metadata["description"]) <= 1024, f"Skill description length is invalid: {name}")
    require(PLACEHOLDER not in content.upper(), f"Skill contains an unfinished placeholder: {name}")
    require("capability-routing-contract.md" in content, f"Skill does not load the routing contract: {name}")
    if name in EVIDENCE_SKILLS:
        require("evidence-copyright-contract.md" in content, f"Skill lacks conditional evidence contract loading: {name}")
    if name in PORTABLE_RECORD_SKILLS:
        require("portable-learning-records.md" in content, f"Skill lacks portable-record contract loading: {name}")
    for tag, skills in OUTPUT_TAG_SKILLS.items():
        if name in skills:
            require(tag in content, f"Skill does not require the output evidence tag {tag}: {name}")

    yaml_path = skill_dir / "agents" / "openai.yaml"
    document = load_yaml(yaml_path)
    require(isinstance(document, dict) and set(document) == {"interface"}, f"openai.yaml root is invalid: {name}")
    interface = document.get("interface")
    required_fields = {"display_name", "short_description", "default_prompt"}
    require(isinstance(interface, dict) and set(interface) == required_fields, f"openai.yaml interface fields are invalid: {name}")
    require(all(isinstance(interface[field], str) for field in required_fields), f"openai.yaml values must be strings: {name}")
    require(25 <= len(interface["short_description"]) <= 64, f"short_description must contain 25 to 64 characters: {name}")
    require(f"${name}" in interface["default_prompt"], f"default_prompt must explicitly include ${name}")
    require(PLACEHOLDER not in read_utf8_text(yaml_path).upper(), f"openai.yaml contains a placeholder: {name}")


def check_links(plugin: Path) -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    plugin_resolved = plugin.resolve()
    for md_path in plugin.rglob("*.md"):
        for target in link_pattern.findall(read_utf8_text(md_path)):
            clean = target.split("#", 1)[0].strip()
            if not clean or clean.startswith(("https://", "http://", "mailto:")):
                continue
            resolved = (md_path.parent / clean).resolve()
            require(
                resolved == plugin_resolved or plugin_resolved in resolved.parents,
                f"Markdown link leaves plugin tree: {md_path}: {target}",
            )
            require(resolved.exists(), f"Markdown link target does not exist: {md_path}: {target}")


def check_obsidian_brain_contract(plugin: Path) -> None:
    routing = read_utf8_text(plugin / "references" / "capability-routing-contract.md")
    brain = read_utf8_text(plugin / "references" / "obsidian-brain-contract.md")
    notion = read_utf8_text(plugin / "references" / "notion-brain-contract.md")
    require(
        "obsidian-brain-contract.md" in routing,
        "routing contract must load the Obsidian brain contract",
    )
    for marker in (
        ".codex/kaoyan-22408/obsidian-brain.json",
        '"schemaVersion": "1.0"',
        '"writeMode": "auto-structured"',
        '"retrievalScope": "project-first"',
        "[Obsidian记忆]",
        "本次不记忆",
        "未连接",
        "最多使用 8 篇笔记",
        "16,000",
        "hypothesis",
        "planned",
        "completed",
    ):
        require(marker in brain, f"Obsidian brain contract is missing marker: {marker}")
    require(
        "notion-brain-contract.md" in routing,
        "routing contract must conditionally load the Notion brain contract",
    )
    for marker in (
        "Notion:search",
        "Notion:fetch",
        "Notion:notion-create-pages",
        "Notion:notion-update-page",
        "filters: {}",
        "[Notion记忆]",
        "本次不记忆",
        "old_str",
        "new_str",
        "planned",
        "completed",
        "hypothesis",
    ):
        require(marker in notion, f"Notion brain contract is missing marker: {marker}")
    combined = "\n".join(
        read_utf8_text(path)
        for path in plugin.rglob("*")
        if path.is_file()
    )
    for private_marker in (
        "C:\\Users\\admin",
        "C:/Users/admin",
        "ob知识库",
    ):
        require(
            private_marker not in combined,
            f"public plugin contains a private local path marker: {private_marker}",
        )


def check_portable_schema(plugin: Path) -> None:
    schema_path = plugin / "references" / "portable-learning-records.schema.json"
    schema = load_json(schema_path)
    require(isinstance(schema, dict), "portable record schema must be an object")
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "portable record schema must use Draft 2020-12")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationError(f"invalid portable-record JSON Schema: {exc.message}") from exc

    output_samples = (
        {
            "schemaVersion": "1.1",
            "recordType": "StudyProfile",
            "targetExam": None,
            "targetDate": None,
            "weeklyHours": None,
            "currentPhase": None,
            "constraints": [],
        },
        {
            "schemaVersion": "1.1",
            "recordType": "ProgressSnapshot",
            "period": {"start": None, "end": None},
            "metrics": [],
            "accuracy": [],
            "blockers": [],
        },
        {
            "schemaVersion": "1.1",
            "recordType": "ReviewQueue",
            "generatedAt": None,
            "items": [],
        },
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for sample in output_samples:
        try:
            validator.validate(sample)
        except JsonSchemaValidationError as exc:
            raise ValidationError(f"portable-record schema rejects a required 1.1 shape: {exc.message}") from exc

    defs = schema.get("$defs")
    require(isinstance(defs, dict) and "legacyInput" in defs, "portable-record schema must expose $defs/legacyInput")
    legacy_root = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/legacyInput",
        "$defs": defs,
    }
    legacy_validator = Draft202012Validator(legacy_root, format_checker=FormatChecker())
    legacy_samples = (
        {
            "schemaVersion": "1.0",
            "period": {"start": "2026-07-01", "end": "2026-07-07"},
            "plannedUnits": 10,
            "completedUnits": 8,
            "accuracy": 0.7,
            "sampleSize": 20,
            "legacyExtension": "preserve me",
        },
        {
            "schemaVersion": "1.0",
            "items": [{"topic": "limit", "retestDate": "D+3"}],
        },
        {
            "schemaVersion": "1.0",
            "targetExam": "未提供",
            "targetDate": "",
            "weeklyHours": "unknown",
            "currentPhase": "",
            "constraints": [],
            "blockers": ["legacy extension that also resembles progress data"],
            "unrecognizedExtension": {"preserve": True},
        },
    )
    for sample in legacy_samples:
        try:
            legacy_validator.validate(sample)
        except JsonSchemaValidationError as exc:
            raise ValidationError(f"portable-record schema rejects a supported 1.0 input: {exc.message}") from exc
    require(
        all(not validator.is_valid(sample) for sample in legacy_samples),
        "portable-record root schema must reject all Schema 1.0 inputs",
    )
    invalid_11_date = {
        "schemaVersion": "1.1",
        "recordType": "ReviewQueue",
        "generatedAt": None,
        "items": [
            {
                "subject": None,
                "topic": "limit",
                "errorCause": None,
                "errorCauseStatus": None,
                "nextRetestDate": "D+3",
                "retestOffsetDays": None,
                "status": "pending",
                "masteryEvidence": [],
            }
        ],
    }
    require(
        not validator.is_valid(invalid_11_date),
        "portable-record schema must reject D+N in a Schema 1.1 date field",
    )
    invalid_date_and_offset = {
        **invalid_11_date,
        "items": [
            {
                **invalid_11_date["items"][0],
                "nextRetestDate": "2026-07-18",
                "retestOffsetDays": 3,
            }
        ],
    }
    require(
        not validator.is_valid(invalid_date_and_offset),
        "portable-record schema must reject simultaneous nextRetestDate and retestOffsetDays",
    )
    invalid_zero_total = {
        "schemaVersion": "1.1",
        "recordType": "ProgressSnapshot",
        "period": {"start": None, "end": None},
        "metrics": [],
        "accuracy": [
            {"subject": "math2", "correct": 1, "total": 0, "rate": None}
        ],
        "blockers": [],
    }
    require(
        not validator.is_valid(invalid_zero_total),
        "portable-record schema must reject correct > 0 when total is zero",
    )
    valid_accuracy_record = {
        "schemaVersion": "1.1",
        "recordType": "ProgressSnapshot",
        "period": {"start": None, "end": None},
        "metrics": [],
        "accuracy": [
            {"subject": "english2", "correct": 16, "total": 20, "rate": 0.8}
        ],
        "blockers": [],
    }
    check_progress_accuracy_semantics(valid_accuracy_record)
    semantic_mutations = (
        {"subject": "english2", "correct": 21, "total": 20, "rate": 1.0},
        {"subject": "english2", "correct": 16, "total": 20, "rate": 0.7},
    )
    for entry in semantic_mutations:
        record = {**valid_accuracy_record, "accuracy": [entry]}
        try:
            check_progress_accuracy_semantics(record)
        except ValidationError:
            continue
        raise ValidationError("portable-record semantic gate accepted inconsistent accuracy values")


def check_progress_accuracy_semantics(record: dict[str, Any]) -> None:
    """Enforce numeric relationships JSON Schema cannot express portably."""

    require(record.get("recordType") == "ProgressSnapshot", "accuracy semantics require ProgressSnapshot")
    accuracy = record.get("accuracy")
    require(isinstance(accuracy, list), "ProgressSnapshot accuracy must be an array")
    for index, entry in enumerate(accuracy):
        require(isinstance(entry, dict), f"accuracy[{index}] must be an object")
        correct = entry.get("correct")
        total = entry.get("total")
        rate = entry.get("rate")
        if correct is not None and total is not None:
            require(correct <= total, f"accuracy[{index}].correct must not exceed total")
        if total == 0:
            require(correct in {None, 0}, f"accuracy[{index}].correct must be 0 or null when total is zero")
            require(rate is None, f"accuracy[{index}].rate must be null when total is zero")
        elif correct is not None and total is not None and rate is not None:
            expected_rate = correct / total
            require(
                math.isclose(rate, expected_rate, rel_tol=0.0, abs_tol=1e-12),
                f"accuracy[{index}].rate must equal correct / total",
            )


def check_release_tree(plugin: Path) -> None:
    roots = {path.name for path in plugin.iterdir()}
    require(roots == ALLOWED_PLUGIN_ROOTS, f"plugin roots do not match the release allowlist: {sorted(roots)}")

    for path in plugin.rglob("*"):
        require(not path.is_symlink(), f"release tree must not contain symbolic links: {path}")

    actual_files = {
        path.relative_to(plugin).as_posix()
        for path in plugin.rglob("*")
        if path.is_file()
    }
    require(actual_files == ALLOWED_RELEASE_FILES, "release tree does not match the exact full-path allowlist")

    for relative in sorted(actual_files):
        pure = PurePosixPath(relative)
        require(not ({part.lower() for part in pure.parts} & FORBIDDEN_PATH_PARTS), f"forbidden release path: {relative}")
        text = read_utf8_text(plugin / Path(*pure.parts))
        require(PLACEHOLDER not in text.upper(), f"release file contains an unfinished placeholder: {relative}")
        for pattern in LEGACY_PATTERNS:
            require(pattern.search(text) is None, f"release file contains a removed-system marker: {relative}")
        for pattern in SENSITIVE_PATTERNS:
            require(pattern.search(text) is None, f"release file contains a likely secret: {relative}")


def check_forward_cases(repo: Path) -> None:
    forward = load_json(repo / "tests" / "forward-cases.json")
    require(isinstance(forward, dict) and forward.get("schemaVersion") == "1.3", "forward cases must use schemaVersion 1.3")
    cases = forward.get("cases")
    require(isinstance(cases, list) and len(cases) == 60, "forward cases must contain exactly 60 cases")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    require(len(ids) == 60 and len(set(ids)) == 60 and all(isinstance(item, str) and item for item in ids), "forward case IDs must be unique non-empty strings")
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for case in cases:
        require(isinstance(case, dict), "each forward case must be an object")
        skill = case.get("skillUnderTest")
        kind = case.get("kind")
        require(skill in EXPECTED_SKILLS, f"forward case contains an unknown Skill: {case.get('id')}")
        require(kind in {"positive", "colloquial", "conflict", "compound"}, f"forward case kind is invalid: {case.get('id')}")
        require(case.get("expectedPrimary") in EXPECTED_SKILLS, f"forward case route is invalid: {case.get('id')}")
        require(isinstance(case.get("prompt"), str) and case["prompt"].strip(), f"forward case has no prompt: {case.get('id')}")
        require(isinstance(case.get("expectedBehavior"), list) and case["expectedBehavior"], f"forward case has no behavior assertions: {case.get('id')}")
        require(
            all(isinstance(item, str) and item.strip() for item in case["expectedBehavior"]),
            f"forward behavior assertions must be non-empty strings: {case.get('id')}",
        )
        if kind in {"positive", "colloquial"}:
            require(case["expectedPrimary"] == skill, f"{kind} case does not route to the Skill under test: {case.get('id')}")
        elif kind == "conflict":
            require(case.get("expectedNotPrimary") == skill, f"conflict case does not exclude the Skill under test: {case.get('id')}")
            require(case["expectedPrimary"] != skill, f"conflict case still routes to the excluded Skill: {case.get('id')}")
        counts[skill][kind] += 1
    for skill in EXPECTED_SKILLS:
        expected = Counter({"positive": 2, "colloquial": 1, "conflict": 1, "compound": 1})
        require(counts[skill] == expected, f"{skill} must have 2 positive, 1 colloquial, 1 conflict, and 1 compound case")


def check_behavior_cases(repo: Path) -> None:
    behavior = load_json(repo / "tests" / "behavior-cases.json")
    require(isinstance(behavior, dict) and behavior.get("schemaVersion") == "1.3", "behavior cases must use schemaVersion 1.3")
    cases = behavior.get("cases")
    require(isinstance(cases, list) and len(cases) == 36, "behavior cases must contain exactly 36 cases")
    ids: list[str] = []
    for case in cases:
        require(isinstance(case, dict), "each behavior case must be an object")
        case_id = case.get("id")
        require(isinstance(case_id, str) and case_id.strip(), "behavior case ID must be a non-empty string")
        ids.append(case_id)
        require(case.get("expectedPrimary") in EXPECTED_SKILLS, f"behavior case route is invalid: {case_id}")
        has_prompt = isinstance(case.get("prompt"), str) and bool(case["prompt"].strip())
        has_turns = isinstance(case.get("turns"), list) and bool(case["turns"])
        has_transcript = isinstance(case.get("transcript"), list) and bool(case["transcript"])
        require(
            has_prompt or has_turns or has_transcript,
            f"behavior case must contain prompt, turns, or transcript: {case_id}",
        )
        rubric = case.get("rubric")
        require(isinstance(rubric, list) and bool(rubric), f"behavior case must contain a non-empty rubric list: {case_id}")
        require(
            all(isinstance(item, str) and item.strip() for item in rubric),
            f"behavior rubric entries must be non-empty strings: {case_id}",
        )
        if has_transcript:
            for turn in case["transcript"]:
                require(isinstance(turn, dict), f"behavior transcript turn must be an object: {case_id}")
                require(turn.get("role") in {"user", "assistant"}, f"behavior transcript role is invalid: {case_id}")
                require(
                    isinstance(turn.get("content"), str) and turn["content"].strip(),
                    f"behavior transcript content is empty: {case_id}",
                )
    require(len(ids) == len(set(ids)), "behavior case IDs must be unique")
    numbers = {
        int(match.group(1))
        for case_id in ids
        if (match := re.fullmatch(r"behavior-(\d{2})-[a-z0-9-]+", case_id))
    }
    require(numbers == set(range(1, 37)), "behavior case IDs must cover behavior-01 through behavior-36 exactly")


def check_repository_docs(repo: Path) -> None:
    required = {
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "PRIVACY.md",
        "TERMS.md",
        "SECURITY.md",
        "THIRD_PARTY_CONTENT.md",
        "QUALITY_GATES.md",
        ".agents/plugins/marketplace.json",
        "tests/forward-cases.json",
        "tests/behavior-cases.json",
        "tests/system-validator-evidence.json",
    }
    for relative in required:
        require((repo / relative).is_file(), f"required repository file is missing: {relative}")
    require(not (repo / "submission").exists(), "obsolete submission directory must be absent")

    manifest = load_json(
        repo / Path(*PLUGIN_RELATIVE_PATH.parts) / ".codex-plugin" / "plugin.json"
    )
    version = manifest.get("version") if isinstance(manifest, dict) else None
    require(
        isinstance(version, str) and SEMVER.fullmatch(version) is not None,
        "manifest version is unavailable for documentation checks",
    )
    readme = read_utf8_text(repo / "README.md")
    require(
        f"当前版本：`{version}`" in readme,
        "README current version must match plugin.json.version",
    )
    require(
        f"--ref v{version}" in readme,
        "README marketplace ref must match plugin.json.version",
    )
    require(
        f"--branch v{version}" in readme,
        "README clone tag must match plugin.json.version",
    )
    changelog = read_utf8_text(repo / "CHANGELOG.md")
    current_release = re.search(
        r"^## \[([^\]]+)\] - (Unreleased|\d{4}-\d{2}-\d{2})$",
        changelog,
        re.MULTILINE,
    )
    require(current_release is not None, "CHANGELOG must start with a versioned release heading")
    require(
        current_release.group(1) == version,
        "CHANGELOG current version must match plugin.json.version",
    )

    marketplace = load_json(repo / ".agents" / "plugins" / "marketplace.json")
    require(isinstance(marketplace, dict) and marketplace.get("name") == "kaoyan-22408", "marketplace name is invalid")
    plugins = marketplace.get("plugins")
    require(isinstance(plugins, list) and len(plugins) == 1, "marketplace must contain exactly one plugin")
    entry = plugins[0]
    require(isinstance(entry, dict) and entry.get("name") == "kaoyan-22408", "marketplace plugin name is invalid")
    require(entry.get("category") == "Education", "marketplace category must be Education")
    require(entry.get("source", {}).get("path") == "./plugins/kaoyan-22408", "marketplace source.path is invalid")
    require(entry.get("policy", {}).get("installation") == "AVAILABLE", "marketplace installation policy is invalid")
    require(entry.get("policy", {}).get("authentication") == "ON_INSTALL", "marketplace authentication policy is invalid")


def _run_git(repo: Path, arguments: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ValidationError(f"cannot run git: {exc}") from exc
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result


def check_git_history(repo: Path) -> None:
    objects_output = _run_git(repo, ["rev-list", "--objects", "--all"]).stdout.decode("utf-8", "strict")
    object_paths: dict[str, str] = {}
    object_ids: list[str] = []
    for line in objects_output.splitlines():
        object_id, _, path = line.partition(" ")
        if object_id and object_id not in object_paths:
            object_ids.append(object_id)
            object_paths[object_id] = path
        if path:
            parts = {part.lower() for part in PurePosixPath(path).parts}
            require(not (parts & HISTORY_FORBIDDEN_PATH_PARTS), f"Git history contains a removed private-data path: {path}")
            encoded_path = path.encode("utf-8")
            for pattern in HISTORY_SECRET_PATTERNS:
                require(pattern.search(encoded_path) is None, f"Git history contains a likely secret in a path: {path}")

    if not object_ids:
        return
    batch = _run_git(repo, ["cat-file", "--batch"], input_bytes=("\n".join(object_ids) + "\n").encode("ascii")).stdout
    stream = io.BytesIO(batch)
    for requested_id in object_ids:
        header = stream.readline().rstrip(b"\n")
        fields = header.split()
        require(len(fields) >= 3, f"unexpected git cat-file response for {requested_id}")
        object_type = fields[1]
        size = int(fields[2])
        payload = stream.read(size)
        require(len(payload) == size and stream.read(1) == b"\n", f"truncated git object: {requested_id}")
        path = object_paths.get(requested_id, "")
        if object_type in {b"blob", b"commit", b"tag"}:
            for pattern in HISTORY_SECRET_PATTERNS:
                require(pattern.search(payload) is None, f"Git history contains a likely secret in {path or requested_id}")
        if object_type == b"blob" and path not in {".semgrep.yml", "scripts/validate_repository.py"}:
            for pattern in HISTORY_LEGACY_PATTERNS:
                require(pattern.search(payload) is None, f"Git history contains a removed-system marker in {path or requested_id}")


def validate_repo(
    repo: Path | None = None,
    *,
    scan_history: bool = True,
) -> list[str]:
    repo = (repo or Path(__file__).resolve().parents[1]).resolve()
    plugin = repo / Path(*PLUGIN_RELATIVE_PATH.parts)
    require(plugin.is_dir(), f"plugin directory does not exist: {plugin}")

    check_repository_docs(repo)
    check_manifest(plugin)
    check_release_tree(plugin)
    check_obsidian_brain_contract(plugin)
    check_portable_schema(plugin)

    skill_root = plugin / "skills"
    skill_dirs = {path.name: path for path in skill_root.iterdir() if path.is_dir()}
    require(set(skill_dirs) == EXPECTED_SKILLS, "Skill set must match the 12-Skill design")
    for name in sorted(EXPECTED_SKILLS):
        check_skill(skill_dirs[name])
    check_links(plugin)
    check_forward_cases(repo)
    check_behavior_cases(repo)
    if scan_history:
        check_git_history(repo)
    return [
        "manifest and marketplace",
        "12 Skills and openai.yaml files",
        "shared contracts, optional Obsidian brain, and portable-record JSON Schema",
        "exact release allowlist, UTF-8/LF, and sensitive-content scan",
        "60 routing and 36 behavior scenario coverage checks",
        "Git-history, secret, and removed-system scans",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        results = validate_repo()
    except (OSError, UnicodeError, ValidationError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    for result in results:
        print(f"[OK] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
