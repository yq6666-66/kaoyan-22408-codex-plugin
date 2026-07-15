from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_release import build_archive  # noqa: E402


class ReleaseArchiveTests(unittest.TestCase):
    def test_archive_contains_only_allowlisted_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "release.zip"
            archive, digest, names = build_archive(REPO, output)
            self.assertTrue(archive.is_file())
            self.assertEqual(len(digest), 64)
            self.assertTrue(names)
            self.assertEqual(names, sorted(names))
            self.assertEqual(
                {name.split("/", 1)[0] for name in names},
                {".codex-plugin", "skills", "references", "assets"},
            )
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.namelist(), names)
                self.assertIn(".codex-plugin/plugin.json", names)


if __name__ == "__main__":
    unittest.main()
