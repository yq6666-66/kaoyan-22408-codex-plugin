from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from check import (  # noqa: E402
    pinned_requirement_version,
    verify_python_dependency_versions,
    verify_semgrep_version,
)


class CheckScriptTests(unittest.TestCase):
    def test_semgrep_pin_is_read_from_requirements(self) -> None:
        self.assertEqual(
            pinned_requirement_version(REPO / "requirements-dev.txt", "semgrep"),
            "1.162.0",
        )

    def test_semgrep_version_mismatch_is_rejected(self) -> None:
        result = subprocess.CompletedProcess(["semgrep", "--version"], 0, "1.146.0\n", "")
        with patch("check.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "expected 1.162.0"):
                verify_semgrep_version("semgrep", "1.162.0", REPO, {})

    def test_python_dependency_versions_match_pins(self) -> None:
        verify_python_dependency_versions(
            REPO / "requirements-dev.txt",
            ("PyYAML", "jsonschema"),
        )

    def test_matching_semgrep_version_passes(self) -> None:
        result = subprocess.CompletedProcess(["semgrep", "--version"], 0, "semgrep 1.162.0\n", "")
        with patch("check.subprocess.run", return_value=result):
            verify_semgrep_version("semgrep", "1.162.0", REPO, {})


if __name__ == "__main__":
    unittest.main()
