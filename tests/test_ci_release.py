from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ci"))

from release_metadata import metadata  # noqa: E402
from verify_reproducible import release_pair  # noqa: E402


class ReleaseCiTests(unittest.TestCase):
    def test_metadata_is_derived_from_manifest(self) -> None:
        values = metadata("ubuntu")
        manifest = json.loads(
            (REPO / "plugins/kaoyan-22408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        version = manifest["version"]
        self.assertEqual(values["version"], version)
        self.assertEqual(values["tag"], f"v{version}")
        self.assertEqual(values["archive"], f"kaoyan-22408-{version}.zip")
        self.assertEqual(values["artifact"], f"kaoyan-22408-{version}-ubuntu")

    def test_release_pair_verifies_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / metadata()["archive"]
            archive.write_bytes(b"same bytes")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            checksum = archive.with_name(archive.name + ".sha256")
            checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8", newline="\n")
            found_archive, found_checksum, found_digest = release_pair(directory)
            self.assertEqual(found_archive, archive)
            self.assertEqual(found_checksum, checksum)
            self.assertEqual(found_digest, digest)

    def test_release_pair_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / metadata()["archive"]
            archive.write_bytes(b"tampered")
            checksum = archive.with_name(archive.name + ".sha256")
            checksum.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release_pair(directory)


if __name__ == "__main__":
    unittest.main()
