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
    "[ç”¨æˆ·ææ–™]": {
        "kaoyan-error-loop-coach",
        "kaoyan-mock-exam-coach",
        "kaoyan-408-tutor",
        "kaoyan-math2-coach",
        "kaoyan-english2-coach",
        "kaoyan-politics-coach",
        "kaoyan-past-paper-analyst",
        "kaoyan-material-study-assistant",
    },
    "[åŽŸåˆ›ç»ƒä¹ ]": {
        "kaoyan-error-loop-coach",
        "kaoyan-mock-exam-coach",
        "kaoyan-408-tutor",
        "kaoyan-math2-coach",
        "kaoyan-english2-coach",
        "kaoyan-politics-coach",
        "kaoyan-past-paper-analyst",
        "kaoyan-material-study-assistant",
    },
    "[å®˜æ–¹æ ¸éªŒ]": {"kaoyan-official-info-researcher"},
    "[å¾…æ ¸éªŒ]": {"kaoyan-politics-coach", "kaoyan-official-info-researcher"},
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
        "[Obsidianè®°å¿†]",
        "æœ¬æ¬¡ä¸è®°å¿†",
        "æœªè¿žæŽ¥",
        "æœ€å¤šä½¿ç”¨ 8 ç¯‡ç¬”è®°",
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
        "[Notionè®°å¿†]",
        "æœ¬æ¬¡ä¸è®°å¿†",
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
        "obçŸ¥è¯†åº“",
    ):
        requÛº¶‰žËkºwµçq½ˆ ˆ¨ˆ¤è(€€€€€€€É•ÅÕ¥É”¡¹½ÐÁ…Ñ ¹¥Í}Íåµ±¥¹¬ ¤°˜‰É•±•…Í”ÑÉ•”µÕÍÐ¹½Ð½¹Ñ…¥¸Íåµ‰½±¥Œ±¥¹­ÌèíÁ…Ñ¡ôˆ¤((€€€…ÑÕ…±}™¥±•Ì€ôì(€€€€€€€Á…Ñ ¹É•±…Ñ¥Ù•}Ñ¼¡Á±Õ¥¸¤¹…Í}Á½Í¥à ¤(€€€€€€€™½ÈÁ…Ñ ¥¸Á±Õ¥¸¹É±½ˆ ˆ¨ˆ¤(€€€€€€€¥˜Á…Ñ ¹¥Í}™¥±” ¤(€€€ô(€€€É•ÅÕ¥É”¡…ÑÕ…±}™¥±•Ì€ôô11=]}I1M}%1L°€‰É•±•…Í”ÑÉ•”‘½•Ì¹½Ðµ…Ñ Ñ¡”•á…Ð™Õ±°µÁ…Ñ …±±½Ý±¥ÍÐˆ¤((€€€™½ÈÉ•±…Ñ¥Ù”¥¸Í½ÉÑ•¡…ÑÕ…±}™¥±•Ì¤è(€€€€€€€ÁÕÉ”€ôAÕÉ•A½Í¥áA…Ñ ¡É•±…Ñ¥Ù”¤(€€€€€€€É•ÅÕ¥É”¡¹½Ð€¡íÁ…ÉÐ¹±½Ý•È ¤™½ÈÁ…ÉÐ¥¸ÁÕÉ”¹Á…ÉÑÍô€˜=I	%9}AQ!}AIQL¤°˜‰™½É‰¥‘‘•¸É•±•…Í”Á…Ñ èíÉ•±…Ñ¥Ù•ôˆ¤(€€€€€€€Ñ•áÐ€ôÉ•…‘}ÕÑ˜á}Ñ•áÐ¡Á±Õ¥¸€¼A…Ñ  ©ÁÕÉ”¹Á…ÉÑÌ¤¤(€€€€€€€É•ÅÕ¥É”¡A1!=1H¹½Ð¥¸Ñ•áÐ¹ÕÁÁ•È ¤°˜‰É•±•…Í”™¥±”½¹Ñ…¥¹Ì…¸Õ¹™¥¹¥Í¡•Á±…•¡½±‘•ÈèíÉ•±…Ñ¥Ù•ôˆ¤(€€€€€€€™½ÈÁ…ÑÑ•É¸¥¸1e}AQQI9Lè(€€€€€€€€€€€É•ÅÕ¥É”¡Á…ÑÑ•É¸¹Í•…É ¡Ñ•áÐ¤¥Ì9½¹”°˜‰É•±•…Í”™¥±”½¹Ñ…¥¹Ì„É•µ½Ù•µÍåÍÑ•´µ…É­•ÈèíÉ•±…Ñ¥Ù•ôˆ¤(€€€€€€€™½ÈÁ…ÑÑ•É¸¥¸M9M%Q%Y}AQQI9Lè(€€€€€€€€€€€É•ÅÕ¥É”¡Á…ÑÑ•É¸¹Í•…É ¡Ñ•áÐ¤¥Ì9½¹”°˜‰É•±•…Í”™¥±”½¹Ñ…¥¹Ì„±¥­•±äÍ•É•ÐèíÉ•±…Ñ¥Ù•ôˆ¤(()‘•˜¡•­}™½ÉÝ…É‘}…Í•Ì¡É•Á¼èA…Ñ ¤€´ø9½¹”è(€€€™½ÉÝ…É€ô±½…‘}©Í½¸¡É•Á¼€¼€‰Ñ•ÍÑÌˆ€¼€‰™½ÉÝ…Éµ…Í•Ì¹©Í½¸ˆ¤(€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡™½ÉÝ…É°‘¥Ð¤…¹™½ÉÝ…É¹•Ð ‰Í¡•µ…Y•ÉÍ¥½¸ˆ¤€ôô€ˆÄ¸Ìˆ°€‰™½ÉÝ…É…Í•ÌµÕÍÐÕÍ”Í¡•µ…Y•ÉÍ¥½¸€Ä¸Ìˆ¤(€€€…Í•Ì€ô™½ÉÝ…É¹•Ð ‰…Í•Ìˆ¤(€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡…Í•Ì°±¥ÍÐ¤…¹±•¸¡…Í•Ì¤€ôô€ØÀ°€‰™½ÉÝ…É…Í•ÌµÕÍÐ½¹Ñ…¥¸•á…Ñ±ä€ØÀ…Í•Ìˆ¤(€€€¥‘Ì€ôm…Í”¹•Ð ‰¥ˆ¤™½È…Í”¥¸…Í•Ì¥˜¥Í¥¹ÍÑ…¹”¡…Í”°‘¥Ð¥t(€€€É•ÅÕ¥É”¡±•¸¡¥‘Ì¤€ôô€ØÀ…¹±•¸¡Í•Ð¡¥‘Ì¤¤€ôô€ØÀ…¹…±°¡¥Í¥¹ÍÑ…¹”¡¥Ñ•´°ÍÑÈ¤…¹¥Ñ•´™½È¥Ñ•´¥¸¥‘Ì¤°€‰™½ÉÝ…É…Í”%ÌµÕÍÐ‰”Õ¹¥ÅÕ”¹½¸µ•µÁÑäÍÑÉ¥¹Ìˆ¤(€€€½Õ¹ÑÌè‘¥ÑmÍÑÈ°½Õ¹Ñ•ÉmÍÑÉut€ô‘•™…Õ±Ñ‘¥Ð¡½Õ¹Ñ•È¤(€€€™½È…Í”¥¸…Í•Ìè(€€€€€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡…Í”°‘¥Ð¤°€‰•… ™½ÉÝ…É…Í”µÕÍÐ‰”…¸½‰©•Ðˆ¤(€€€€€€€Í­¥±°€ô…Í”¹•Ð ‰Í­¥±±U¹‘•ÉQ•ÍÐˆ¤(€€€€€€€­¥¹€ô…Í”¹•Ð ‰­¥¹ˆ¤(€€€€€€€É•ÅÕ¥É”¡Í­¥±°¥¸aAQ}M-%11L°˜‰™½ÉÝ…É…Í”½¹Ñ…¥¹Ì…¸Õ¹­¹½Ý¸M­¥±°èí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€É•ÅÕ¥É”¡­¥¹¥¸ì‰Á½Í¥Ñ¥Ù”ˆ°€‰½±±½ÅÕ¥…°ˆ°€‰½¹™±¥Ðˆ°€‰½µÁ½Õ¹‰ô°˜‰™½ÉÝ…É…Í”­¥¹¥Ì¥¹Ù…±¥èí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€É•ÅÕ¥É”¡…Í”¹•Ð ‰•áÁ•Ñ•‘AÉ¥µ…Éäˆ¤¥¸aAQ}M-%11L°˜‰™½ÉÝ…É…Í”É½ÕÑ”¥Ì¥¹Ù…±¥èí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡…Í”¹•Ð ‰ÁÉ½µÁÐˆ¤°ÍÑÈ¤…¹…Í•l‰ÁÉ½µÁÐ‰t¹ÍÑÉ¥À ¤°˜‰™½ÉÝ…É…Í”¡…Ì¹¼ÁÉ½µÁÐèí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡…Í”¹•Ð ‰•áÁ•Ñ•‘	•¡…Ù¥½Èˆ¤°±¥ÍÐ¤…¹…Í•l‰•áÁ•Ñ•‘	•¡…Ù¥½È‰t°˜‰™½ÉÝ…É…Í”¡…Ì¹¼‰•¡…Ù¥½È…ÍÍ•ÉÑ¥½¹Ìèí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€É•ÅÕ¥É” (€€€€€€€€€€€…±°¡¥Í¥¹ÍÑ…¹”¡¥Ñ•´°ÍÑÈ¤…¹¥Ñ•´¹ÍÑÉ¥À ¤™½È¥Ñ•´¥¸…Í•l‰•áÁ•Ñ•‘	•¡…Ù¥½È‰t¤°(€€€€€€€€€€€˜‰™½ÉÝ…É‰•¡…Ù¥½È…ÍÍ•ÉÑ¥½¹ÌµÕÍÐ‰”¹½¸µ•µÁÑäÍÑÉ¥¹Ìèí…Í”¹•Ð ¥œ¥ôˆ°(€€€€€€€€¤(€€€€€€€¥˜­¥¹¥¸ì‰Á½Í¥Ñ¥Ù”ˆ°€‰½±±½ÅÕ¥…°‰ôè(€€€€€€€€€€€É•ÅÕ¥É”¡…Í•l‰•áÁ•Ñ•‘AÉ¥µ…Éä‰t€ôôÍ­¥±°°˜‰í­¥¹‘ô…Í”‘½•Ì¹½ÐÉ½ÕÑ”Ñ¼Ñ¡”M­¥±°Õ¹‘•ÈÑ•ÍÐèí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€•±¥˜­¥¹€ôô€‰½¹™±¥Ðˆè(€€€€€€€€€€€É•ÅÕ¥É”¡…Í”¹•Ð ‰•áÁ•Ñ•‘9½ÑAÉ¥µ…Éäˆ¤€ôôÍ­¥±°°˜‰½¹™±¥Ð…Í”‘½•Ì¹½Ð•á±Õ‘”Ñ¡”M­¥±°Õ¹‘•ÈÑ•ÍÐèí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€€€€€É•ÅÕ¥É”¡…Í•l‰•áÁ•Ñ•‘AÉ¥µ…Éä‰t€„ôÍ­¥±°°˜‰½¹™±¥Ð…Í”ÍÑ¥±°É½ÕÑ•ÌÑ¼Ñ¡”•á±Õ‘•M­¥±°èí…Í”¹•Ð ¥œ¥ôˆ¤(€€€€€€€½Õ¹ÑÍmÍ­¥±±um­¥¹‘t€¬ô€Ä(€€€™½ÈÍ­¥±°¥¸aAQ}M-%11Lè(€€€€€€€•áÁ•Ñ•€ô½Õ¹Ñ•È¡ì‰Á½Í¥Ñ¥Ù”ˆè€È°€‰½±±½ÅÕ¥…°ˆè€Ä°€‰½¹™±¥Ðˆè€Ä°€‰½µÁ½Õ¹ˆè€Åô¤(€€€€€€€É•ÅÕ¥É”¡½Õ¹ÑÍmÍ­¥±±t€ôô•áÁ•Ñ•°˜‰íÍ­¥±±ôµÕÍÐ¡…Ù”€ÈÁ½Í¥Ñ¥Ù”°€Ä½±±½ÅÕ¥…°°€Ä½¹™±¥Ð°…¹€Ä½µÁ½Õ¹…Í”ˆ¤(()‘•˜¡•­}‰•¡…Ù¥½É}…Í•Ì¡É•Á¼èA…Ñ ¤€´ø9½¹”è(€€€‰•¡…Ù¥½È€ô±½…‘}©Í½¸¡É•Á¼€¼€‰Ñ•ÍÑÌˆ€¼€‰‰•¡…Ù¥½Èµ…Í•Ì¹©Í½¸ˆ¤(€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡‰•¡…Ù¥½È°‘¥Ð¤…¹‰•¡…Ù¥½È¹•Ð ‰Í¡•µ…Y•ÉÍ¥½¸ˆ¤€ôô€ˆÄ¸Ìˆ°€‰‰•¡…Ù¥½È…Í•ÌµÕÍÐÕÍ”Í¡•µ…Y•ÉÍ¥½¸€Ä¸Ìˆ¤(€€€…Í•Ì€ô‰•¡…Ù¥½È¹•Ð ‰…Í•Ìˆ¤(€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡…Í•Ì°±¥ÍÐ¤…¹±•¸¡…Í•Ì¤€ôô€ÌØ°€‰‰•¡…Ù¥½È…Í•ÌµÕÍÐ½¹Ñ…¥¸•á…Ñ±ä€ÌØ…Í•Ìˆ¤(€€€¥‘Ìè±¥ÍÑmÍÑÉt€ômt(€€€™½È…Í”¥¸…Í•Ìè(€€€€€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡…Í”°‘¥Ð¤°€‰•… ‰•¡…Ù¥½È…Í”µÕÍÐ‰”…¸½‰©•Ðˆ¤(€€€€€€€…Í•}¥€ô…Í”¹•Ð ‰¥ˆ¤(€€€€€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡…Í•}¥°ÍÑÈ¤…¹…Í•}¥¹ÍÑÉ¥À ¤°€‰‰•¡…Ù¥½È…Í”%µÕÍÐ‰”„¹½¸µ•µÁÑäÍÑÉ¥¹œˆ¤(€€€€€€€¥‘Ì¹…ÁÁ•¹¡…Í•}¥¤(€€€€€€€É•ÅÕ¥É”¡…Í”¹•Ð ‰•áÁ•Ñ•‘AÉ¥µ…Éäˆ¤¥¸aAQ}M-%11L°˜‰‰•¡…Ù¥½È…Í”É½ÕÑ”¥Ì¥¹Ù…±¥èí…Í•}¥‘ôˆ¤(€€€€€€€¡…Í}ÁÉ½µÁÐ€ô¥Í¥¹ÍÑ…¹”¡…Í”¹•Ð ‰ÁÉ½µÁÐˆ¤°ÍÑÈ¤…¹‰½½°¡…Í•l‰ÁÉ½µÁÐ‰t¹ÍÑÉ¥À ¤¤(€€€€€€€¡…Í}ÑÕÉ¹Ì€ô¥Í¥¹ÍÑ…¹”¡…Í”¹•Ð ‰ÑÕÉ¹Ìˆ¤°±¥ÍÐ¤…¹‰½½°¡…Í•l‰ÑÕÉ¹Ì‰t¤(€€€€€€€¡…Í}ÑÉ…¹ÍÉ¥ÁÐ€ô¥Í¥¹ÍÑ…¹”¡…Í”¹•Ð ‰ÑÉ…¹ÍÉ¥ÁÐˆ¤°±¥ÍÐ¤…¹‰½½°¡…Í•l‰ÑÉ…¹ÍÉ¥ÁÐ‰t¤(€€€€€€€É•ÅÕ¥É” (€€€€€€€€€€€¡…Í}ÁÉ½µÁÐ½È¡…Í}ÑÕÉ¹Ì½È¡…Í}ÑÉ…¹ÍÉ¥ÁÐ°(€€€€€€€€€€€˜‰‰•¡…Ù¥½È…Í”µÕÍÐ½¹Ñ…¥¸ÁÉ½µÁÐ°ÑÕÉ¹Ì°½ÈÑÉ…¹ÍÉ¥ÁÐèí…Í•}¥‘ôˆ°(€€€€€€€€¤(€€€€€€€ÉÕ‰É¥Œ€ô…Í”¹•Ð ‰ÉÕ‰É¥Œˆ¤(€€€€€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡ÉÕ‰É¥Œ°±¥ÍÐ¤…¹‰½½°¡ÉÕ‰É¥Œ¤°˜‰‰•¡…Ù¥½È…Í”µÕÍÐ½¹Ñ…¥¸„¹½¸µ•µÁÑäÉÕ‰É¥Œ±¥ÍÐèí…Í•}¥‘ôˆ¤(€€€€€€€É•ÅÕ¥É” (€€€€€€€€€€€…±°¡¥Í¥¹ÍÑ…¹”¡¥Ñ•´°ÍÑÈ¤…¹¥Ñ•´¹ÍÑÉ¥À ¤™½È¥Ñ•´¥¸ÉÕ‰É¥Œ¤°(€€€€€€€€€€€˜‰‰•¡…Ù¥½ÈÉÕ‰É¥Œ•¹ÑÉ¥•ÌµÕÍÐ‰”¹½¸µ•µÁÑäÍÑÉ¥¹Ìèí…Í•}¥‘ôˆ°(€€€€€€€€¤(€€€€€€€¥˜¡…Í}ÑÉ…¹ÍÉ¥ÁÐè(€€€€€€€€€€€™½ÈÑÕÉ¸¥¸…Í•l‰ÑÉ…¹ÍÉ¥ÁÐ‰tè(€€€€€€€€€€€€€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡ÑÕÉ¸°‘¥Ð¤°˜‰‰•¡…Ù¥½ÈÑÉ…¹ÍÉ¥ÁÐÑÕÉ¸µÕÍÐ‰”…¸½‰©•Ðèí…Í•}¥‘ôˆ¤(€€€€€€€€€€€€€€€É•ÅÕ¥É”¡ÑÕÉ¸¹•Ð ‰É½±”ˆ¤¥¸ì‰ÕÍ•Èˆ°€‰…ÍÍ¥ÍÑ…¹Ð‰ô°˜‰‰•¡…Ù¥½ÈÑÉ…¹ÍÉ¥ÁÐÉ½±”¥Ì¥¹Ù…±¥èí…Í•}¥‘ôˆ¤(€€€€€€€€€€€€€€€É•ÅÕ¥É” (€€€€€€€€€€€€€€€€€€€¥Í¥¹ÍÑ…¹”¡ÑÕÉ¸¹•Ð ‰½¹Ñ•¹Ðˆ¤°ÍÑÈ¤…¹ÑÕÉ¹l‰½¹Ñ•¹Ð‰t¹ÍÑÉ¥À ¤°(€€€€€€€€€€€€€€€€€€€˜‰‰•¡…Ù¥½ÈÑÉ…¹ÍÉ¥ÁÐ½¹Ñ•¹Ð¥Ì•µÁÑäèí…Í•}¥‘ôˆ°(€€€€€€€€€€€€€€€€¤(€€€É•ÅÕ¥É”¡±•¸¡¥‘Ì¤€ôô±•¸¡Í•Ð¡¥‘Ì¤¤°€‰‰•¡…Ù¥½È…Í”%ÌµÕÍÐ‰”Õ¹¥ÅÕ”ˆ¤(€€€¹Õµ‰•ÉÌ€ôì(€€€€€€€¥¹Ð¡µ…Ñ ¹É½ÕÀ Ä¤¤(€€€€€€€™½È…Í•}¥¥¸¥‘Ì(€€€€€€€¥˜€¡µ…Ñ €èôÉ”¹™Õ±±µ…Ñ ¡È‰‰•¡…Ù¥½È´¡q‘ìÉô¤µm„µèÀ´äµt¬ˆ°…Í•}¥¤¤(€€€ô(€€€É•ÅÕ¥É”¡¹Õµ‰•ÉÌ€ôôÍ•Ð¡É…¹” Ä°€ÌÜ¤¤°€‰‰•¡…Ù¥½È…Í”%ÌµÕÍÐ½Ù•È‰•¡…Ù¥½È´ÀÄÑ¡É½Õ ‰•¡…Ù¥½È´ÌØ•á…Ñ±äˆ¤(()‘•˜¡•­}É•Á½Í¥Ñ½Éå}‘½Ì¡É•Á¼èA…Ñ ¤€´ø9½¹”è(€€€É•ÅÕ¥É•€ôì(€€€€€€€€‰I5¹µˆ°(€€€€€€€€‰!91=¹µˆ°(€€€€€€€€‰1%9Mˆ°(€€€€€€€€‰AI%Yd¹µˆ°(€€€€€€€€‰QI5L¹µˆ°(€€€€€€€€‰MUI%Qd¹µˆ°(€€€€€€€€‰Q!%I}AIQe}=9Q9P¹µˆ°(€€€€€€€€ˆ¹…•¹ÑÌ½Á±Õ¥¹Ì½µ…É­•ÑÁ±…”¹©Í½¸ˆ°(€€€€€€€€‰Ñ•ÍÑÌ½™½ÉÝ…Éµ…Í•Ì¹©Í½¸ˆ°(€€€€€€€€‰Ñ•ÍÑÌ½‰•¡…Ù¥½Èµ…Í•Ì¹©Í½¸ˆ°(€€€€€€€€‰Ñ•ÍÑÌ½ÍåÍÑ•´µÙ…±¥‘…Ñ½Èµ•Ù¥‘•¹”¹©Í½¸ˆ°(€€€ô(€€€™½ÈÉ•±…Ñ¥Ù”¥¸É•ÅÕ¥É•è(€€€€€€€É•ÅÕ¥É” ¡É•Á¼€¼É•±…Ñ¥Ù”¤¹¥Í}™¥±” ¤°˜‰É•ÅÕ¥É•É•Á½Í¥Ñ½Éä™¥±”¥Ìµ¥ÍÍ¥¹œèíÉ•±…Ñ¥Ù•ôˆ¤(€€€É•ÅÕ¥É”¡¹½Ð€¡É•Á¼€¼€‰ÍÕ‰µ¥ÍÍ¥½¸ˆ¤¹•á¥ÍÑÌ ¤°€‰½‰Í½±•Ñ”ÍÕ‰µ¥ÍÍ¥½¸‘¥É•Ñ½ÉäµÕÍÐ‰”…‰Í•¹Ðˆ¤((€€€µ…¹¥™•ÍÐ€ô±½…‘}©Í½¸ (€€€€€€€É•Á¼€¼A…Ñ  ©A1U%9}I1Q%Y}AQ ¹Á…ÉÑÌ¤€¼€ˆ¹½‘•àµÁ±Õ¥¸ˆ€¼€‰Á±Õ¥¸¹©Í½¸ˆ(€€€€¤(€€€Ù•ÉÍ¥½¸€ôµ…¹¥™•ÍÐ¹•Ð ‰Ù•ÉÍ¥½¸ˆ¤¥˜¥Í¥¹ÍÑ…¹”¡µ…¹¥™•ÍÐ°‘¥Ð¤•±Í”9½¹”(€€€É•ÅÕ¥É” (€€€€€€€¥Í¥¹ÍÑ…¹”¡Ù•ÉÍ¥½¸°ÍÑÈ¤…¹M5YH¹™Õ±±µ…Ñ ¡Ù•ÉÍ¥½¸¤¥Ì¹½Ð9½¹”°(€€€€€€€€‰µ…¹¥™•ÍÐÙ•ÉÍ¥½¸¥ÌÕ¹…Ù…¥±…‰±”™½È‘½Õµ•¹Ñ…Ñ¥½¸¡•­Ìˆ°(€€€€¤(€€€É•…‘µ”€ôÉ•…‘}ÕÑ˜á}Ñ•áÐ¡É•Á¼€¼€‰I5¹µˆ¤(€€€É•ÅÕ¥É” (€€€€€€€˜‹–öO–&7ž&#šr³¾òiíÙ•ÉÍ¥½¹õ€ˆ¥¸É•…‘µ”°(€€€€€€€€‰I5ÕÉÉ•¹ÐÙ•ÉÍ¥½¸µÕÍÐµ…Ñ Á±Õ¥¸¹©Í½¸¹Ù•ÉÍ¥½¸ˆ°(€€€€¤(€€€É•ÅÕ¥É” (€€€€€€€˜ˆ´µÉ•˜ÙíÙ•ÉÍ¥½¹ôˆ¥¸É•…‘µ”°(€€€€€€€€‰I5µ…É­•ÑÁ±…”É•˜µÕÍÐµ…Ñ Á±Õ¥¸¹©Í½¸¹Ù•ÉÍ¥½¸ˆ°(€€€€¤(€€€É•ÅÕ¥É” (€€€€€€€˜ˆ´µ‰É…¹ ÙíÙ•ÉÍ¥½¹ôˆ¥¸É•…‘µ”°(€€€€€€€€‰I5±½¹”Ñ…œµÕÍÐµ…Ñ Á±Õ¥¸¹©Í½¸¹Ù•ÉÍ¥½¸ˆ°(€€€€¤(€€€¡…¹•±½œ€ôÉ•…‘}ÕÑ˜á}Ñ•áÐ¡É•Á¼€¼€‰!91=¹µˆ¤(€€€ÕÉÉ•¹Ñ}É•±•…Í”€ôÉ”¹Í•…É  (€€€€€€€È‰xŒŒql¡myqut¬¥qt€´€¡U¹É•±•…Í•‘ñq‘ìÑôµq‘ìÉôµq‘ìÉô¤ˆ°(€€€€€€€¡…¹•±½œ°(€€€€€€€É”¹5U1Q%1%9°(€€€€¤(€€€É•ÅÕ¥É”¡ÕÉÉ•¹Ñ}É•±•…Í”¥Ì¹½Ð9½¹”°€‰!91=µÕÍÐÍÑ…ÉÐÝ¥Ñ „Ù•ÉÍ¥½¹•É•±•…Í”¡•…‘¥¹œˆ¤(€€€É•ÅÕ¥É” (€€€€€€€ÕÉÉ•¹Ñ}É•±•…Í”¹É½ÕÀ Ä¤€ôôÙ•ÉÍ¥½¸°(€€€€€€€€‰!91=ÕÉÉ•¹ÐÙ•ÉÍ¥½¸µÕÍÐµ…Ñ Á±Õ¥¸¹©Í½¸¹Ù•ÉÍ¥½¸ˆ°(€€€€¤((€€€µ…É­•ÑÁ±…”€ô±½…‘}©Í½¸¡É•Á¼€¼€ˆ¹…•¹ÑÌˆ€¼€‰Á±Õ¥¹Ìˆ€¼€‰µ…É­•ÑÁ±…”¹©Í½¸ˆ¤(€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡µ…É­•ÑÁ±…”°‘¥Ð¤…¹µ…É­•ÑÁ±…”¹•Ð ‰¹…µ”ˆ¤€ôô€‰­…½å…¸´ÈÈÐÀàˆ°€‰µ…É­•ÑÁ±…”¹…µ”¥Ì¥¹Ù…±¥ˆ¤(€€€Á±Õ¥¹Ì€ôµ…É­•ÑÁ±…”¹•Ð ‰Á±Õ¥¹Ìˆ¤(€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡Á±Õ¥¹Ì°±¥ÍÐ¤…¹±•¸¡Á±Õ¥¹Ì¤€ôô€Ä°€‰µ…É­•ÑÁ±…”µÕÍÐ½¹Ñ…¥¸•á…Ñ±ä½¹”Á±Õ¥¸ˆ¤(€€€•¹ÑÉä€ôÁ±Õ¥¹ÍlÁt(€€€É•ÅÕ¥É”¡¥Í¥¹ÍÑ…¹”¡•¹ÑÉä°‘¥Ð¤…¹•¹ÑÉä¹•Ð ‰¹…µ”ˆ¤€ôô€‰­…½å…¸´ÈÈÐÀàˆ°€‰µ…É­•ÑÁ±…”Á±Õ¥¸¹…µ”¥Ì¥¹Ù…±¥ˆ¤(€€€É•ÅÕ¥É”¡•¹ÑÉä¹•Ð ‰…Ñ•½Éäˆ¤€ôô€‰‘Õ…Ñ¥½¸ˆ°€‰µ…É­•ÑÁ±…”…Ñ•½ÉäµÕÍÐ‰”‘Õ…Ñ¥½¸ˆ¤(€€€É•ÅÕ¥É”¡•¹ÑÉä¹•Ð ‰Í½ÕÉ”ˆ°íô¤¹•Ð ‰Á…Ñ ˆ¤€ôô€ˆ¸½Á±Õ¥¹Ì½­…½å…¸´ÈÈÐÀàˆ°€‰µ…É­•ÑÁ±…”Í½ÕÉ”¹Á…Ñ ¥Ì¥¹Ù…±¥ˆ¤(€€€É•ÅÕ¥É”¡•¹ÑÉä¹•Ð ‰Á½±¥äˆ°íô¤¹•Ð ‰¥¹ÍÑ…±±…Ñ¥½¸ˆ¤€ôô€‰Y%1	1ˆ°€‰µ…É­•ÑÁ±…”¥¹ÍÑ…±±…Ñ¥½¸Á½±¥ä¥Ì¥¹Ù…±¥ˆ¤(€€€É•ÅÕ¥É”¡•¹ÑÉä¹•Ð ‰Á½±¥äˆ°íô¤¹•Ð ‰…ÕÑ¡•¹Ñ¥…Ñ¥½¸ˆ¤€ôô€‰=9}%9MQ10ˆ°€‰µ…É­•ÑÁ±…”…ÕÑ¡•¹Ñ¥…Ñ¥½¸Á½±¥ä¥Ì¥¹Ù…±¥ˆ¤(()‘•˜}ÉÕ¹}¥Ð¡É•Á¼èA…Ñ °…ÉÕµ•¹ÑÌè±¥ÍÑmÍÑÉt°€¨°¥¹ÁÕÑ}‰åÑ•Ìè‰åÑ•Ìð9½¹”€ô9½¹”¤€´øÍÕ‰ÁÉ½•ÍÌ¹½µÁ±•Ñ•‘AÉ½•ÍÍm‰åÑ•Ítè(€€€ÑÉäè(€€€€€€€É•ÍÕ±Ð€ôÍÕ‰ÁÉ½•ÍÌ¹ÉÕ¸ (€€€€€€€€€€€l‰¥Ðˆ°€©…ÉÕµ•¹ÑÍt°(€€€€€€€€€€€ÝõÉ•Á¼°(€€€€€€€€€€€¥¹ÁÕÐõ¥¹ÁÕÑ}‰åÑ•Ì°(€€€€€€€€€€€ÍÑ‘½ÕÐõÍÕ‰ÁÉ½•ÍÌ¹A%A°(€€€€€€€€€€€ÍÑ‘•ÉÈõÍÕ‰ÁÉ½•ÍÌ¹A%A°(€€€€€€€€€€€¡•¬õ…±Í”°(€€€€€€€€¤(€€€•á•ÁÐ=MÉÉ½È…Ì•áŒè(€€€€€€€É…¥Í”Y…±¥‘…Ñ¥½¹ÉÉ½È¡˜‰…¹¹½ÐÉÕ¸¥Ðèí•áôˆ¤™É½´•áŒ(€€€É•ÅÕ¥É”¡É•ÍÕ±Ð¹É•ÑÕÉ¹½‘”€ôô€À°˜‰¥Ðìœ€œ¹©½¥¸¡…ÉÕµ•¹ÑÌ¥ô™…¥±•èíÉ•ÍÕ±Ð¹ÍÑ‘•ÉÈ¹‘•½‘” ÕÑ˜´àœ°€É•Á±…”œ¤¹ÍÑÉ¥À ¥ôˆ¤(€€€É•ÑÕÉ¸É•ÍÕ±Ð(()‘•˜¡•­}¥Ñ}¡¥ÍÑ½Éä¡É•Á¼èA…Ñ ¤€´ø9½¹”è(€€€½‰©•ÑÍ}½ÕÑÁÕÐ€ô}ÉÕ¹}¥Ð¡É•Á¼°l‰É•Øµ±¥ÍÐˆ°€ˆ´µ½‰©•ÑÌˆ°€ˆ´µ…±°‰t¤¹ÍÑ‘½ÕÐ¹‘•½‘” ‰ÕÑ˜´àˆ°€‰ÍÑÉ¥Ðˆ¤(€€€½‰©•Ñ}Á…Ñ¡Ìè‘¥ÑmÍÑÈ°ÍÑÉt€ôíô(€€€½‰©•Ñ}¥‘Ìè±¥ÍÑmÍÑÉt€ômt(€€€™½È±¥¹”¥¸½‰©•ÑÍ}½ÕÑÁÕÐ¹ÍÁ±¥Ñ±¥¹•Ì ¤è(€€€€€€€½‰©•Ñ}¥°|°Á…Ñ €ô±¥¹”¹Á…ÉÑ¥Ñ¥½¸ ˆ€ˆ¤(€€€€€€€¥˜½‰©•Ñ}¥…¹½‰©•Ñ}¥¹½Ð¥¸½‰©•Ñ}Á…Ñ¡Ìè(€€€€€€€€€€€½‰©•Ñ}¥‘Ì¹…ÁÁ•¹¡½‰©•Ñ}¥¤(€€€€€€€€€€€½‰©•Ñ}Á…Ñ¡Ím½‰©•Ñ}¥‘t€ôÁ…Ñ (€€€€€€€¥˜Á…Ñ è(€€€€€€€€€€€Á…ÉÑÌ€ôíÁ…ÉÐ¹±½Ý•È ¤™½ÈÁ…ÉÐ¥¸AÕÉ•A½Í¥áA…Ñ ¡Á…Ñ ¤¹Á…ÉÑÍô(€€€€€€€€€€€É•ÅÕ¥É”¡¹½Ð€¡Á…ÉÑÌ€˜!%MQ=Ie}=I	%9}AQ!}AIQL¤°˜‰¥Ð¡¥ÍÑ½Éä½¹Ñ…¥¹Ì„É•µ½Ù•ÁÉ¥Ù…Ñ”µ‘…Ñ„Á…Ñ èíÁ…Ñ¡ôˆ¤(€€€€€€€€€€€•¹½‘•‘}Á…Ñ €ôÁ…Ñ ¹•¹½‘” ‰ÕÑ˜´àˆ¤(€€€€€€€€€€€™½ÈÁ…ÑÑ•É¸¥¸!%MQ=Ie}MIQ}AQQI9Lè(€€€€€€€€€€€€€€€É•ÅÕ¥É”¡Á…ÑÑ•É¸¹Í•…É ¡•¹½‘•‘}Á…Ñ ¤¥Ì9½¹”°˜‰¥Ð¡¥ÍÑ½Éä½¹Ñ…¥¹Ì„±¥­•±äÍ•É•Ð¥¸„Á…Ñ èíÁ…Ñ¡ôˆ¤((€€€¥˜¹½Ð½‰©•Ñ}¥‘Ìè(€€€€€€€É•ÑÕÉ¸(€€€‰…Ñ €ô}ÉÕ¹}¥Ð¡É•Á¼°l‰…Ðµ™¥±”ˆ°€ˆ´µ‰…Ñ ‰t°¥¹ÁÕÑ}‰åÑ•Ìô ‰q¸ˆ¹©½¥¸¡½‰©•Ñ}¥‘Ì¤€¬€‰q¸ˆ¤¹•¹½‘” ‰…Í¥¤ˆ¤¤¹ÍÑ‘½ÕÐ(€€€ÍÑÉ•…´€ô¥¼¹	åÑ•Í%<¡‰…Ñ ¤(€€€™½ÈÉ•ÅÕ•ÍÑ•‘}¥¥¸½‰©•Ñ}¥‘Ìè(€€€€€€€¡•…‘•È€ôÍÑÉ•…´¹É•…‘±¥¹” ¤¹ÉÍÑÉ¥À¡ˆ‰q¸ˆ¤(€€€€€€€™¥•±‘Ì€ô¡•…‘•È¹ÍÁ±¥Ð ¤(€€€€€€€É•ÅÕ¥É”¡±•¸¡™¥•±‘Ì¤€øô€Ì°˜‰Õ¹•áÁ•Ñ•¥Ð…Ðµ™¥±”É•ÍÁ½¹Í”™½ÈíÉ•ÅÕ•ÍÑ•‘}¥‘ôˆ¤(€€€€€€€½‰©•Ñ}ÑåÁ”€ô™¥•±‘ÍlÅt(€€€€€€€Í¥é”€ô¥¹Ð¡™¥•±‘ÍlÉt¤(€€€€€€€Á…å±½…€ôÍÑÉ•…´¹É•…¡Í¥é”¤(€€€€€€€É•ÅÕ¥É”¡±•¸¡Á…å±½…¤€ôôÍ¥é”…¹ÍÑÉ•…´¹É•… Ä¤€ôôˆ‰q¸ˆ°˜‰ÑÉÕ¹…Ñ•¥Ð½‰©•ÐèíÉ•ÅÕ•ÍÑ•‘}¥‘ôˆ¤(€€€€€€€Á…Ñ €ô½‰©•Ñ}Á…Ñ¡Ì¹•Ð¡É•ÅÕ•ÍÑ•‘}¥°€ˆˆ¤(€€€€€€€¥˜½‰©•Ñ}ÑåÁ”¥¸íˆ‰‰±½ˆˆ°ˆ‰½µµ¥Ðˆ°ˆ‰Ñ…œ‰ôè(€€€€€€€€€€€™½ÈÁ…ÑÑ•É¸¥¸!%MQ=Ie}MIQ}AQQI9Lè(€€€€€€€€€€€€€€€É•ÅÕ¥É”¡Á…ÑÑ•É¸¹Í•…É ¡Á…å±½…¤¥Ì9½¹”°˜‰¥Ð¡¥ÍÑ½Éä½¹Ñ…¥¹Ì„±¥­•±äÍ•É•Ð¥¸íÁ…Ñ ½ÈÉ•ÅÕ•ÍÑ•‘}¥‘ôˆ¤(€€€€€€€¥˜½‰©•Ñ}ÑåÁ”€ôôˆ‰‰±½ˆˆ…¹Á…Ñ ¹½Ð¥¸ìˆ¹Í•µÉ•À¹åµ°ˆ°€‰ÍÉ¥ÁÑÌ½Ù…±¥‘…Ñ•}É•Á½Í¥Ñ½Éä¹Áä‰ôè(€€€€€€€€€€€™½ÈÁ…ÑÑ•É¸¥¸!%MQ=Ie}1e}AQQI9Lè(€€€€€€€€€€€€€€€É•ÅÕ¥É”¡Á…ÑÑ•É¸¹Í•…É ¡Á…å±½…¤¥Ì9½¹”°˜‰¥Ð¡¥ÍÑ½Éä½¹Ñ…¥¹Ì„É•µ½Ù•µÍåÍÑ•´µ…É­•È¥¸íÁ…Ñ ½ÈÉ•ÅÕ•ÍÑ•‘}¥‘ôˆ¤(()‘•˜¡•­}™½ÉÝ…É‘}•Ù¥‘•¹”¡É•Á¼èA…Ñ °€¨°‰¥¹‘¥¹}µ½‘”èÍÑÈ€ô€‰ÁÈˆ¤€´ø9½¹”è(€€€É•ÅÕ¥É” (€€€€€€€‰¥¹‘¥¹}µ½‘”¥¸ì‰ÁÈˆ°€‰ÁÉ½Ñ•Ñ•µµ…¥¸‰ô°(€€€€€€€€‰™½ÉÝ…Éµ•Ù¥‘•¹”‰¥¹‘¥¹œµ½‘”¥Ì¥¹Ù…±¥ˆ°(€€€€¤(€€€‰Õ¹‘±”€ôì(€€€€€€€€‰•Ù¥‘•¹”ˆèÉ•Á¼€¼€‰Ñ•ÍÑÌˆ€¼€‰™½ÉÝ…Éµ•Ù…°µ•Ù¥‘•¹”¹©Í½¸ˆ°(€€€€€€€€‰É•ÍÁ½¹Í”µ…¹¥™•ÍÐˆèÉ•Á¼€¼€‰Ñ•ÍÑÌ½™½ÉÝ…Éµ•Ù…°µÉ•ÍÁ½¹Í”µµ…¹¥™•ÍÐ¹©Í½¸ˆ°(€€€€€€€€‰…ÑÑ•ÍÑ…Ñ¥½¸ÍÑ…Ñ•µ•¹ÐˆèÉ•Á¼€¼€‰Ñ•ÍÑÌ½™½ÉÝ…Éµ•Ù…°µ…ÑÑ•ÍÑ…Ñ¥½¸¹©Í½¸ˆ°(€€€€€€€€‰…ÑÑ•ÍÑ…Ñ¥½¸Í¥¹…ÑÕÉ”ˆèÉ•Á¼€¼€‰Ñ•ÍÑÌ½™½ÉÝ…Éµ•Ù…°µ…ÑÑ•ÍÑ…Ñ¥½¸¹©Í½¸¹Í¥œˆ°(€€€ô(€€€•á¥ÍÑ¥¹œ€ôí±…‰•°™½È±…‰•°°Á…Ñ ¥¸‰Õ¹‘±”¹¥Ñ•µÌ ¤¥˜Á…Ñ ¹•á¥ÍÑÌ ¥ô(€€€¥˜¹½Ð•á¥ÍÑ¥¹œè(€€€€€€€É•ÑÕÉ¸(€€€É•ÅÕ¥É” (€€€€€€€•á¥ÍÑ¥¹œ€ôôÍ•Ð¡‰Õ¹‘±”¤°(€€€€€€€€‰™½ÉÝ…Éµ•Ù…°•Ù¥‘•¹”‰Õ¹‘±”¥Ì¥¹½µÁ±•Ñ”è€ˆ(€€€€€€€˜‰ÁÉ•Í•¹ÐõíÍ½ÉÑ•¡•á¥ÍÑ¥¹œ¥ôˆ°(€€€€¤(€€€™½È±…‰•°°Á…Ñ ¥¸‰Õ¹‘±”¹¥Ñ•µÌ ¤è(€€€€€€€É•ÅÕ¥É”¡Á…Ñ ¹¥Í}™¥±” ¤°˜‰™½ÉÝ…Éµ•Ù…°í±…‰•±ôµÕÍÐ‰”„É•Õ±…È™¥±”ˆ¤(€€€€€€€É•ÅÕ¥É”¡¹½ÐÁ…Ñ ¹¥Í}Íåµ±¥¹¬ ¤°˜‰™½ÉÝ…Éµ•Ù…°í±…‰•±ôµÕÍÐ¹½Ð‰”„Íåµ±¥¹¬ˆ¤(€€€•Ù¥‘•¹”€ô‰Õ¹‘±•l‰•Ù¥‘•¹”‰t(€€€Ù•É¥™¥•È€ôÉ•Á¼€¼€‰•Ù…±Ìˆ€¼€‰Ù•É¥™å}™½ÉÝ…É‘}•Ù¥‘•¹”¹Áäˆ(€€€É•ÅÕ¥É”¡Ù•É¥™¥•È¹¥Í}™¥±” ¤°€‰™½ÉÝ…Éµ•Ù…°•Ù¥‘•¹”•á¥ÍÑÌ‰ÕÐ¥ÑÌÙ•É¥™¥•È¥Ìµ¥ÍÍ¥¹œˆ¤(€€€É•ÍÕ±Ð€ôÍÕ‰ÁÉ½•ÍÌ¹ÉÕ¸ (€€€€€€€l(€€€€€€€€€€€ÍåÌ¹•á•ÕÑ…‰±”°(€€€€€€€€€€€ÍÑÈ¡Ù•É¥™¥•È¤°(€€€€€€€€€€€€ˆ´µµ…àµ…”µ‘…åÌˆ°(€€€€€€€€€€€€ˆÌÀˆ°(€€€€€€€€€€€€ˆ´µ‰¥¹‘¥¹œµµ½‘”ˆ°(€€€€€€€€€€€‰¥¹‘¥¹}µ½‘”°(€€€€€€€t°(€€€€€€€ÝõÉ•Á¼°(€€€€€€€ÍÑ‘½ÕÐõÍÕ‰ÁÉ½•ÍÌ¹A%A°(€€€€€€€ÍÑ‘•ÉÈõÍÕ‰ÁÉ½•ÍÌ¹A%A°(€€€€€€€Ñ•áÐõQÉÕ”°(€€€€€€€•¹½‘¥¹œô‰ÕÑ˜´àˆ°(€€€€€€€•ÉÉ½ÉÌô‰É•Á±…”ˆ°(€€€€€€€¡•¬õ…±Í”°(€€€€¤(€€€‘•Ñ…¥°€ô€¡É•ÍÕ±Ð¹ÍÑ‘•ÉÈ½ÈÉ•ÍÕ±Ð¹ÍÑ‘½ÕÐ¤¹ÍÑÉ¥À ¤(€€€É•ÅÕ¥É”¡É•ÍÕ±Ð¹É•ÑÕÉ¹½‘”€ôô€À°˜‰™½ÉÝ…Éµ•Ù…°•Ù¥‘•¹”¥Ì¥¹Ù…±¥½ÈÍÑ…±”èí‘•Ñ…¥±ôˆ¤(()‘•˜Ù…±¥‘…Ñ•}É•Á¼ (€€€É•Á¼èA…Ñ ð9½¹”€ô9½¹”°(€€€€¨°(€€€Ù•É¥™å}•Ù¥‘•¹”è‰½½°€ôQÉÕ”°(€€€Í…¹}¡¥ÍÑ½Éäè‰½½°€ôQÉÕ”°(€€€•Ù¥‘•¹•}‰¥¹‘¥¹}µ½‘”èÍÑÈ€ô€‰ÁÈˆ°(¤€´ø±¥ÍÑmÍÑÉtè(€€€É•Á¼€ô€¡É•Á¼½ÈA…Ñ ¡}}™¥±•}|¤¹É•Í½±Ù” ¤¹Á…É•¹ÑÍlÅt¤¹É•Í½±Ù” ¤(€€€Á±Õ¥¸€ôÉ•Á¼€¼A…Ñ  ©A1U%9}I1Q%Y}AQ ¹Á…ÉÑÌ¤(€€€É•ÅÕ¥É”¡Á±Õ¥¸¹¥Í}‘¥È ¤°˜‰Á±Õ¥¸‘¥É•Ñ½Éä‘½•Ì¹½Ð•á¥ÍÐèíÁ±Õ¥¹ôˆ¤((€€€¡•­}É•Á½Í¥Ñ½Éå}‘½Ì¡É•Á¼¤(€€€¡•­}µ…¹¥™•ÍÐ¡Á±Õ¥¸¤(€€€¡•­}É•±•…Í•}ÑÉ•”¡Á±Õ¥¸¤(€€€¡•­}½‰Í¥‘¥…¹}‰É…¥¹}½¹ÑÉ…Ð¡Á±Õ¥¸¤(€€€¡•­}Á½ÉÑ…‰±•}Í¡•µ„¡Á±Õ¥¸¤((€€€Í­¥±±}É½½Ð€ôÁ±Õ¥¸€¼€‰Í­¥±±Ìˆ(€€€Í­¥±±}‘¥ÉÌ€ôíÁ…Ñ ¹¹…µ”èÁ…Ñ ™½ÈÁ…Ñ ¥¸Í­¥±±}É½½Ð¹¥Ñ•É‘¥È ¤¥˜Á…Ñ ¹¥Í}‘¥È ¥ô(€€€É•ÅÕ¥É”¡Í•Ð¡Í­¥±±}‘¥ÉÌ¤€ôôaAQ}M-%11L°€‰M­¥±°Í•ÐµÕÍÐµ…Ñ Ñ¡”€ÄÈµM­¥±°‘•Í¥¸ˆ¤(€€€™½È¹…µ”¥¸Í½ÉÑ•¡aAQ}M-%11L¤è(€€€€€€€¡•­}Í­¥±°¡Í­¥±±}‘¥ÉÍm¹…µ•t¤(€€€¡•­}±¥¹­Ì¡Á±Õ¥¸¤(€€€¡•­}™½ÉÝ…É‘}…Í•Ì¡É•Á¼¤(€€€¡•­}‰•¡…Ù¥½É}…Í•Ì¡É•Á¼¤(€€€¥˜Í…¹}¡¥ÍÑ½Éäè(€€€€€€€¡•­}¥Ñ}¡¥ÍÑ½Éä¡É•Á¼¤(€€€¥˜Ù•É¥™å}•Ù¥‘•¹”è(€€€€€€€¡•­}™½ÉÝ…É‘}•Ù¥‘•¹”¡É•Á¼°‰¥¹‘¥¹}µ½‘”õ•Ù¥‘•¹•}‰¥¹‘¥¹}µ½‘”¤(€€€É•ÑÕÉ¸l(€€€€€€€€‰µ…¹¥™•ÍÐ…¹µ…É­•ÑÁ±…”ˆ°(€€€€€€€€ˆÄÈM­¥±±Ì…¹½Á•¹…¤¹å…µ°™¥±•Ìˆ°(€€€€€€€€‰Í¡…É•½¹ÑÉ…ÑÌ°½ÁÑ¥½¹…°=‰Í¥‘¥…¸‰É…¥¸°…¹Á½ÉÑ…‰±”µÉ•½É)M=8M¡•µ„ˆ°(€€€€€€€€‰•á…ÐÉ•±•…Í”…±±½Ý±¥ÍÐ°UQ´à½1°…¹Í•¹Í¥Ñ¥Ù”µ½¹Ñ•¹ÐÍ…¸ˆ°(€€€€€€€€ˆØÀÉ½ÕÑ¥¹œ…Í•Ì…¹€ÌØ‰•¡…Ù¥½È…Í•Ìˆ°(€€€€€€€€‰¥Ðµ¡¥ÍÑ½Éä…¹™½ÉÝ…Éµ•Ù¥‘•¹”…Ñ•Ìˆ°(€€€t(()‘•˜µ…¥¸ ¤€´ø¥¹Ðè(€€€Á…ÉÍ•È€ô…ÉÁ…ÉÍ”¹ÉÕµ•¹ÑA…ÉÍ•È¡‘•ÍÉ¥ÁÑ¥½¸õ}}‘½}|¤(€€€Á…ÉÍ•È¹…‘‘}…ÉÕµ•¹Ð (€€€€€€€€ˆ´µ•Ù¥‘•¹”µ‰¥¹‘¥¹œµµ½‘”ˆ°(€€€€€€€¡½¥•Ìô ‰ÁÈˆ°€‰ÁÉ½Ñ•Ñ•µµ…¥¸ˆ¤°(€€€€€€€‘•™…Õ±Ðô‰ÁÈˆ°(€€€€¤(€€€…ÉÌ€ôÁ…ÉÍ•È¹Á…ÉÍ•}…ÉÌ ¤(€€€ÑÉäè(€€€€€€€É•ÍÕ±ÑÌ€ôÙ…±¥‘…Ñ•}É•Á¼¡•Ù¥‘•¹•}‰¥¹‘¥¹}µ½‘”õ…ÉÌ¹•Ù¥‘•¹•}‰¥¹‘¥¹}µ½‘”¤(€€€•á•ÁÐ€¡=MÉÉ½È°U¹¥½‘•ÉÉ½È°Y…±¥‘…Ñ¥½¹ÉÉ½È¤…Ì•áŒè(€€€€€€€ÁÉ¥¹Ð¡˜‰m%1tí•áôˆ°™¥±”õÍåÌ¹ÍÑ‘•ÉÈ¤(€€€€€€€É•ÑÕÉ¸€Ä(€€€™½ÈÉ•ÍÕ±Ð¥¸É•ÍÕ±ÑÌè(€€€€€€€ÁÉ¥¹Ð¡˜‰m=-tíÉ•ÍÕ±Ñôˆ¤(€€€É•ÑÕÉ¸€À(()¥˜}}¹…µ•}|€ôô€‰}}µ…¥¹}|ˆè(€€€É…¥Í”MåÍÑ•µá¥Ð¡µ…¥¸ ¤¤(