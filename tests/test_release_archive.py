from __future__ import annotations

import hashlib
import json
import stat
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_release import (  # noqa: E402
    FIXED_ZIP_TIME,
    UTF8_FLAG,
    Utf8ZipInfo,
    build_archive,
    validate_release_archive,
)
from validate_repository import ALLOWED_RELEASE_FILES, ValidationError  # noqa: E402
try:  # Support both unittest discovery and tests.test_* module execution.
    from .test_support import copy_as_committed_repo  # type: ignore[import-not-found]
except ImportError:
    from test_support import copy_as_committed_repo  # type: ignore[no-redef]


class ReleaseArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = copy_as_committed_repo(self.root / "repo")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_archive_is_deterministic_and_has_checksum(self) -> None:
        first = build_archive(self.repo, self.root / "first.zip")
        second = build_archive(self.repo, self.root / "second.zip")
        self.assertEqual(first.archive.read_bytes(), second.archive.read_bytes())
        self.assertEqual(first.digest, hashlib.sha256(first.archive.read_bytes()).hexdigest())
        self.assertEqual(first.names, tuple(sorted(ALLOWED_RELEASE_FILES)))
        self.assertEqual(
            first.checksum.read_text(encoding="ascii"),
            f"{first.digest}  {first.archive.name}\n",
        )

        with zipfile.ZipFile(first.archive) as archive:
            for info in archive.infolist():
                mode = (info.external_attr >> 16) & 0xFFFF
                self.assertEqual(info.date_time, FIXED_ZIP_TIME)
                self.assertEqual(info.create_system, 3)
                self.assertTrue(stat.S_ISREG(mode))
                self.assertEqual(stat.S_IMODE(mode), 0o644)
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertTrue(info.flag_bits & UTF8_FLAG)

    def test_default_name_is_derived_from_manifest(self) -> None:
        artifact = build_archive(self.repo)
        manifest = json.loads(
            (REPO / "plugins/kaoyan-22408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(artifact.version, manifest["version"])
        self.assertEqual(artifact.archive.name, f"kaoyan-22408-{artifact.version}.zip")
        self.assertEqual(artifact.checksum.name, f"kaoyan-22408-{artifact.version}.zip.sha256")

    def test_release_builder_passes_explicit_evidence_binding_mode(self) -> None:
        with patch("build_release.validate_repo") as validate:
            build_archive(
                self.repo,
                self.root / "protected-main.zip",
                evidence_binding_mode="protected-main",
            )
        validate.assert_called_once_with(
            self.repo.resolve(),
            evidence_binding_mode="protected-main",
        )

    def test_dirty_plugin_tree_is_rejected(self) -> None:
        manifest = self.repo / "plugins/kaoyan-22408/.codex-plugin/plugin.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValidationError, "dirty"):
            build_archive(self.repo, self.root / "dirty.zip")

    def _rewrite_archive(self, source: Path, destination: Path, mutation: str) -> None:
        with zipfile.ZipFile(source) as archive:
            members = [(info.filename, archive.read(info)) for info in archive.infolist()]
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            for index, (name, payload) in enumerate(members):
                target_name = "../escape" if mutation == "traversal" and index == 0 else name
                info = Utf8ZipInfo(target_name, date_time=FIXED_ZIP_TIME)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                if mutation == "symlink" and index == 0:
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                if mutation == "invalid-utf8" and index == 0:
                    payload = b"\xff\xfe"
                archive.writestr(info, payload)
                if mutation == "duplicate" and index == 0:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        archive.writestr(info, payload)

    def test_archive_mutations_are_rejected(self) -> None:
        valid = build_archive(self.repo, self.root / "valid.zip").archive
        for mutation in ("traversal", "symlink", "invalid-utf8", "duplicate"):
            with self.subTest(mutation=mutation):
                mutated = self.root / f"{mutation}.zip"
                self._rewrite_archive(valid, mutated, mutation)
                with self.assertRaises(ValidationError):
                    validate_release_archive(mutated)


if __name__ == "__main__":
    unittest.main()
