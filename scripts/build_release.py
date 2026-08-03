#!/usr/bin/env python3
"""Build a byte-for-byte reproducible release ZIP from committed Git blobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

from validate_repository import (
    ALLOWED_RELEASE_FILES,
    PLUGIN_RELATIVE_PATH,
    ValidationError,
    validate_repo,
)


FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
UTF8_FLAG = 0x800


class Utf8ZipInfo(zipfile.ZipInfo):
    """ZipInfo that always marks names as UTF-8, including ASCII-only names."""

    def _encodeFilenameFlags(self) -> tuple[bytes, int]:  # noqa: N802 - zipfile API name
        return self.filename.encode("utf-8"), self.flag_bits | UTF8_FLAG


@dataclass(frozen=True)
class ReleaseArtifact:
    archive: Path
    checksum: Path
    digest: str
    names: tuple[str, ...]
    version: str


def _git(repo: Path, arguments: list[str], *, text: bool = False) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            encoding="utf-8" if text else None,
            errors="strict" if text else None,
            check=False,
        )
    except OSError as exc:
        raise ValidationError(f"cannot run git: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode("utf-8", "replace")
        raise ValidationError(f"git {' '.join(arguments)} failed: {stderr.strip()}")
    return result


def _require_clean_plugin_tree(repo: Path) -> None:
    result = _git(
        repo,
        [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            PLUGIN_RELATIVE_PATH.as_posix(),
        ],
        text=True,
    )
    if result.stdout.strip():
        raise ValidationError("plugin tree is dirty; commit the exact release payload before building")


def committed_plugin_blobs(repo: Path) -> dict[str, bytes]:
    """Return the exact allowlisted plugin files from HEAD, never from the worktree."""

    _require_clean_plugin_tree(repo)
    tree = _git(
        repo,
        ["ls-tree", "-r", "-z", "HEAD", "--", PLUGIN_RELATIVE_PATH.as_posix()],
    ).stdout
    entries: dict[str, tuple[str, str]] = {}
    prefix = PLUGIN_RELATIVE_PATH.as_posix() + "/"
    for raw_record in tree.split(b"\x00"):
        if not raw_record:
            continue
        metadata, separator, raw_path = raw_record.partition(b"\t")
        if not separator:
            raise ValidationError("malformed git tree entry")
        try:
            mode, object_type, object_id = metadata.decode("ascii").split()
            full_path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValidationError("malformed or non-UTF-8 git tree entry") from exc
        if not full_path.startswith(prefix):
            raise ValidationError(f"unexpected plugin path from Git: {full_path}")
        relative = full_path[len(prefix) :]
        if mode != "100644" or object_type != "blob":
            raise ValidationError(f"release Git entry must be a regular 0644 blob: {relative}")
        entries[relative] = (mode, object_id)

    if set(entries) != set(ALLOWED_RELEASE_FILES):
        missing = sorted(set(ALLOWED_RELEASE_FILES) - set(entries))
        extra = sorted(set(entries) - set(ALLOWED_RELEASE_FILES))
        raise ValidationError(f"committed plugin tree violates exact allowlist; missing={missing}, extra={extra}")

    payloads: dict[str, bytes] = {}
    for relative in sorted(entries):
        object_id = entries[relative][1]
        payload = _git(repo, ["cat-file", "blob", object_id]).stdout
        if b"\x00" in payload:
            raise ValidationError(f"release text contains NUL bytes: {relative}")
        if b"\r" in payload:
            raise ValidationError(f"committed release text must use LF: {relative}")
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"committed release file is not UTF-8: {relative}") from exc
        payloads[relative] = payload
    return payloads


def plugin_tree_digest(payloads: Mapping[str, bytes]) -> str:
    """Hash a plugin tree unambiguously by path and payload length."""

    digest = hashlib.sha256()
    for name in sorted(payloads):
        encoded_name = name.encode("utf-8")
        payload = payloads[name]
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _manifest_version(payloads: Mapping[str, bytes]) -> str:
    try:
        manifest = json.loads(payloads[".codex-plugin/plugin.json"].decode("utf-8"))
        version = manifest["version"]
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"cannot derive release version from committed manifest: {exc}") from exc
    if not isinstance(version, str) or not version:
        raise ValidationError("committed manifest version must be a non-empty string")
    return version


def _zip_info(name: str) -> Utf8ZipInfo:
    info = Utf8ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.create_system = 3
    info.create_version = 20
    info.extract_version = 20
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.internal_attr = 0
    info.extra = b""
    info.comment = b""
    return info


def validate_release_archive(archive_path: Path) -> tuple[str, ...]:
    """Reject malformed, ambiguous, or non-reproducible release ZIPs."""

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            duplicates = [name for name, count in Counter(names).items() if count > 1]
            if duplicates:
                raise ValidationError(f"release ZIP contains duplicate members: {sorted(duplicates)}")
            if set(names) != set(ALLOWED_RELEASE_FILES) or names != sorted(ALLOWED_RELEASE_FILES):
                raise ValidationError("release ZIP does not match the exact ordered allowlist")
            if archive.comment:
                raise ValidationError("release ZIP comment must be empty")
            for info in infos:
                name = info.filename
                pure = PurePosixPath(name)
                if (
                    not name
                    or "\\" in name
                    or pure.is_absolute()
                    or any(part in {"", ".", ".."} for part in pure.parts)
                    or pure.as_posix() != name
                ):
                    raise ValidationError(f"unsafe or non-canonical ZIP path: {name}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if info.create_system != 3 or not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o644:
                    raise ValidationError(f"ZIP member metadata is not canonical regular 0644: {name}")
                if info.date_time != FIXED_ZIP_TIME:
                    raise ValidationError(f"ZIP member timestamp is not canonical: {name}")
                if info.compress_type != zipfile.ZIP_STORED:
                    raise ValidationError(f"ZIP member must use ZIP_STORED: {name}")
                if not (info.flag_bits & UTF8_FLAG):
                    raise ValidationError(f"ZIP member is missing the UTF-8 flag: {name}")
                payload = archive.read(info)
                if b"\x00" in payload or b"\r" in payload:
                    raise ValidationError(f"ZIP member is not canonical UTF-8/LF text: {name}")
                try:
                    payload.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValidationError(f"ZIP member is not valid UTF-8: {name}") from exc
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValidationError(f"ZIP CRC check failed: {bad_member}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValidationError(f"invalid release ZIP: {archive_path}: {exc}") from exc
    return tuple(names)


def build_archive(
    repo: Path,
    output: Path | None = None,
) -> ReleaseArtifact:
    repo = repo.resolve()
    _require_clean_plugin_tree(repo)
    validate_repo(repo)
    payloads = committed_plugin_blobs(repo)
    version = _manifest_version(payloads)
    archive_path = (output or repo / "dist" / f"kaoyan-22408-{version}.zip").resolve()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    for path in (archive_path, checksum_path):
        if path.exists():
            path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.comment = b""
        for name in sorted(payloads):
            archive.writestr(_zip_info(name), payloads[name])

    names = validate_release_archive(archive_path)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_bytes(f"{digest}  {archive_path.name}\n".encode("ascii"))
    return ReleaseArtifact(
        archive=archive_path,
        checksum=checksum_path,
        digest=digest,
        names=names,
        version=version,
    )


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional ZIP path; default name is derived from plugin.json.version",
    )
    args = parser.parse_args()
    output = args.output
    if output is not None and not output.is_absolute():
        output = repo / output
    try:
        artifact = build_archive(repo, output)
    except ValidationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] release: {artifact.archive}")
    print(f"[OK] checksum: {artifact.checksum}")
    print(f"[OK] files: {len(artifact.names)}")
    print(f"[OK] sha256: {artifact.digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
