#!/usr/bin/env python3
"""Shared deterministic hashing and JSON helpers for forward evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "kaoyan-22408"
ROUTE_CASES = REPO / "tests" / "forward-cases.json"
BEHAVIOR_CASES = REPO / "tests" / "behavior-cases.json"
EVIDENCE = REPO / "tests" / "forward-eval-evidence.json"
RESPONSE_MANIFEST = REPO / "tests" / "forward-eval-response-manifest.json"
ATTESTATION_STATEMENT = REPO / "tests" / "forward-eval-attestation.json"
ATTESTATION_SIGNATURE = REPO / "tests" / "forward-eval-attestation.json.sig"
EVIDENCE_SCHEMA = REPO / "evals" / "schemas" / "evidence.schema.json"
EVALS = REPO / "evals"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_named_files(files: Iterable[tuple[str, Path]]) -> str:
    """Hash path names and exact bytes without depending on filesystem metadata."""
    digest = hashlib.sha256()
    for name, path in sorted(files, key=lambda item: item[0]):
        if path.is_symlink():
            raise ValueError(f"refusing symlink in evaluation input: {path}")
        data = path.read_bytes()
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def plugin_tree_sha256(plugin: Path = PLUGIN) -> str:
    files = [
        (path.relative_to(plugin).as_posix(), path)
        for path in plugin.rglob("*")
        if path.is_file()
    ]
    if not files:
        raise ValueError(f"plugin tree is empty: {plugin}")
    return hash_named_files(files)


def cases_sha256(
    route_cases: Path = ROUTE_CASES,
    behavior_cases: Path = BEHAVIOR_CASES,
) -> str:
    return hash_named_files(
        [
            ("tests/behavior-cases.json", behavior_cases),
            ("tests/forward-cases.json", route_cases),
        ]
    )


def evaluator_sha256(evals: Path = EVALS, *, relative_to: Path = REPO) -> str:
    """Bind evidence and caches to every evaluator source file and output schema."""
    files = [
        (path.relative_to(relative_to).as_posix(), path)
        for path in evals.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    ]
    if not files:
        raise ValueError(f"evaluation harness is empty: {evals}")
    return hash_named_files(files)
