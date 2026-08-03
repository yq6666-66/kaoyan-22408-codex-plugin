#!/usr/bin/env python3
"""Configure and validate the optional local Obsidian brain."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT_ROOT = "20-项目/考研 22408"
DEFAULT_WRITE_MODE = "auto-structured"
DEFAULT_RETRIEVAL_SCOPE = "project-first"
EXPECTED_KEYS = {
    "schemaVersion",
    "enabled",
    "vaultPath",
    "projectRoot",
    "writeMode",
    "retrievalScope",
}


class BrainConfigError(RuntimeError):
    """Raised when the local brain cannot be configured safely."""


def default_config_path() -> Path:
    return Path.home() / ".codex" / "kaoyan-22408" / "obsidian-brain.json"


def local_date() -> str:
    return datetime.now().astimezone().date().isoformat()


def _validate_project_root(value: str) -> PurePosixPath:
    if "\\" in value:
        raise BrainConfigError("projectRoot must use forward slashes")
    project = PurePosixPath(value)
    if project.is_absolute() or not project.parts:
        raise BrainConfigError("projectRoot must be a non-empty relative path")
    if any(part in {"", ".", ".."} for part in project.parts):
        raise BrainConfigError("projectRoot contains an unsafe path segment")
    return project


def _require_real_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise BrainConfigError(f"{label} does not exist: {path}") from exc
    if not resolved.is_dir():
        raise BrainConfigError(f"{label} is not a directory: {resolved}")
    if path.expanduser().is_symlink():
        raise BrainConfigError(f"{label} must not be a symbolic link: {path}")
    return resolved


def _assert_no_symlink_chain(vault: Path, target: Path) -> None:
    try:
        relative = target.relative_to(vault)
    except ValueError as exc:
        raise BrainConfigError(f"target escapes Vault: {target}") from exc
    cursor = vault
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise BrainConfigError(f"Vault target traverses a symbolic link: {cursor}")


def validate_config(data: Any, *, require_paths: bool = True) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != EXPECTED_KEYS:
        raise BrainConfigError(f"config must contain exactly: {sorted(EXPECTED_KEYS)}")
    if data["schemaVersion"] != SCHEMA_VERSION:
        raise BrainConfigError(f"unsupported schemaVersion: {data['schemaVersion']!r}")
    if not isinstance(data["enabled"], bool):
        raise BrainConfigError("enabled must be boolean")
    if data["writeMode"] != DEFAULT_WRITE_MODE:
        raise BrainConfigError(f"writeMode must be {DEFAULT_WRITE_MODE!r}")
    if data["retrievalScope"] != DEFAULT_RETRIEVAL_SCOPE:
        raise BrainConfigError(f"retrievalScope must be {DEFAULT_RETRIEVAL_SCOPE!r}")
    if not isinstance(data["vaultPath"], str) or not data["vaultPath"]:
        raise BrainConfigError("vaultPath must be a non-empty string")
    if not isinstance(data["projectRoot"], str):
        raise BrainConfigError("projectRoot must be a string")
    project = _validate_project_root(data["projectRoot"])
    if require_paths:
        vault = _require_real_directory(Path(data["vaultPath"]), "Vault")
        for required in ("AGENTS.md", "00-系统/知识库索引.md"):
            candidate = vault / Path(*PurePosixPath(required).parts)
            if not candidate.is_file():
                raise BrainConfigError(f"Vault is missing required file: {required}")
        _assert_no_symlink_chain(vault, vault / Path(*project.parts))
    return data


def load_config(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BrainConfigError(f"cannot read config: {path}") from exc
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise BrainConfigError(f"invalid config JSON: {exc}") from exc
    return validate_config(data)


def _atomic_write(path: Path, payload: str) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise BrainConfigError(f"cannot write {path}: {exc}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _write_if_missing(path: Path, payload: str, actions: list[str], *, dry_run: bool) -> None:
    if path.exists():
        actions.append(f"keep {path}")
        return
    actions.append(f"create {path}")
    if not dry_run:
        _atomic_write(path, payload)


def _append_once(path: Path, marker: str, addition: str, actions: list[str], *, dry_run: bool) -> None:
    current = path.read_text(encoding="utf-8")
    if marker in current:
        actions.append(f"keep {path}")
        return
    actions.append(f"update {path}")
    if not dry_run:
        _atomic_write(path, current.rstrip() + "\n\n" + addition.rstrip() + "\n")


def scaffold_vault(vault: Path, project_root: PurePosixPath, *, dry_run: bool) -> list[str]:
    project = vault / Path(*project_root.parts)
    knowledge = vault / "30-知识" / "考研 22408"
    _assert_no_symlink_chain(vault, project)
    _assert_no_symlink_chain(vault, knowledge)
    actions: list[str] = []
    if not dry_run:
        project.mkdir(parents=True, exist_ok=True)
        knowledge.mkdir(parents=True, exist_ok=True)
    today = local_date()
    common = f"""---
type: project
status: active
created: {today}
updated: {today}
tags:
  - 考研
  - 22408
---
"""
    files = {
        "主页.md": common
        + """
# 考研 22408

- [[学习档案]]
- [[当前进度]]
- [[错题队列]]
- [[记忆索引]]
- [[知识库索引]]
""",
        "学习档案.md": common
        + """
# 学习档案

```json
{
  "schemaVersion": "1.1",
  "recordType": "StudyProfile",
  "targetExam": null,
  "targetDate": null,
  "weeklyHours": null,
  "currentPhase": null,
  "constraints": []
}
```
""",
        "当前进度.md": common
        + """
# 当前进度

尚无用户确认的进度快照。
""",
        "错题队列.md": common
        + """
# 错题队列

```json
{
  "schemaVersion": "1.1",
  "recordType": "ReviewQueue",
  "generatedAt": null,
  "items": []
}
```
""",
        "记忆索引.md": common
        + """
# 记忆索引

## 当前记录

- [[学习档案]]
- [[当前进度]]
- [[错题队列]]

## 主题

暂无。
""",
    }
    for name, payload in files.items():
        _write_if_missing(project / name, payload.lstrip(), actions, dry_run=dry_run)
    index = vault / "00-系统" / "知识库索引.md"
    growth = vault / "00-系统" / "成长日志.md"
    _append_once(
        index,
        "[[考研 22408]]",
        "## 考研 22408\n\n- [[考研 22408]]\n- [[记忆索引]]",
        actions,
        dry_run=dry_run,
    )
    if growth.exists():
        _append_once(
            growth,
            f"{today} | [[考研 22408]] | 初始化 Obsidian 学习大脑",
            f"- {today} | [[考研 22408]] | 初始化 Obsidian 学习大脑",
            actions,
            dry_run=dry_run,
        )
    return actions


def configure(args: argparse.Namespace) -> int:
    vault = _require_real_directory(args.vault, "Vault")
    for required in ("AGENTS.md", "00-系统/知识库索引.md"):
        if not (vault / Path(*PurePosixPath(required).parts)).is_file():
            raise BrainConfigError(f"Vault is missing required file: {required}")
    project_root = _validate_project_root(args.project_root)
    config = {
        "schemaVersion": SCHEMA_VERSION,
        "enabled": True,
        "vaultPath": str(vault),
        "projectRoot": project_root.as_posix(),
        "writeMode": DEFAULT_WRITE_MODE,
        "retrievalScope": DEFAULT_RETRIEVAL_SCOPE,
    }
    validate_config(config)
    actions = scaffold_vault(vault, project_root, dry_run=args.dry_run)
    config_path = args.config.expanduser()
    actions.append(f"write {config_path}")
    if not args.dry_run:
        _atomic_write(config_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    prefix = "[DRY-RUN]" if args.dry_run else "[OK]"
    for action in actions:
        print(f"{prefix} {action}")
    return 0


def set_enabled(args: argparse.Namespace, enabled: bool) -> int:
    config = load_config(args.config.expanduser())
    config["enabled"] = enabled
    validate_config(config)
    if args.dry_run:
        print(f"[DRY-RUN] set enabled={str(enabled).lower()} in {args.config}")
    else:
        _atomic_write(
            args.config.expanduser(),
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        )
        print(f"[OK] enabled={str(enabled).lower()}")
    return 0


def check(args: argparse.Namespace) -> int:
    config = load_config(args.config.expanduser())
    print(f"[OK] config: {args.config.expanduser()}")
    print(f"[OK] enabled: {str(config['enabled']).lower()}")
    print(f"[OK] Vault: {config['vaultPath']}")
    print(f"[OK] projectRoot: {config['projectRoot']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config_path())
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure")
    configure_parser.add_argument("--vault", type=Path, required=True)
    configure_parser.add_argument("--project-root", default=DEFAULT_PROJECT_ROOT)
    configure_parser.add_argument("--dry-run", action="store_true")
    configure_parser.set_defaults(handler=configure)

    check_parser = subparsers.add_parser("check")
    check_parser.set_defaults(handler=check)

    for name, enabled in (("enable", True), ("disable", False)):
        toggle = subparsers.add_parser(name)
        toggle.add_argument("--dry-run", action="store_true")
        toggle.set_defaults(handler=lambda args, value=enabled: set_enabled(args, value))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except BrainConfigError as exc:
        print(f"[FAIL] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
