from __future__ import annotations

import io
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from install_local import _relay, install_local  # noqa: E402


def completed(command: list[str], code: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, code, stdout, stderr)


class ScriptedRunner:
    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = list(results)
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if not self.results:
            raise AssertionError(f"unexpected command: {command}")
        return self.results.pop(0)


class LocalInstallerTests(unittest.TestCase):
    def test_relay_escapes_characters_unsupported_by_console_encoding(self) -> None:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="ascii", newline="\n")
        _relay(completed(["check"], stdout="✅ checks passed"), stream)
        stream.flush()
        self.assertIn(b"\\u2705 checks passed", raw.getvalue())

    def run_installer(
        self,
        results: list[subprocess.CompletedProcess[str]],
        *,
        validate_only: bool = False,
        codex: str | None = "codex",
    ) -> tuple[int, str, str, ScriptedRunner]:
        runner = ScriptedRunner(results)
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = install_local(
            REPO,
            validate_only=validate_only,
            runner=runner,
            which=lambda _: codex,
            stdout=stdout,
            stderr=stderr,
        )
        return code, stdout.getvalue(), stderr.getvalue(), runner

    def test_validate_only_returns_zero_without_codex(self) -> None:
        code, stdout, stderr, runner = self.run_installer(
            [completed(["check"], stdout="checks passed")],
            validate_only=True,
            codex=None,
        )
        self.assertEqual(code, 0)
        self.assertIn("Validation completed", stdout)
        self.assertNotIn("Installed", stdout)
        self.assertEqual(stderr, "")
        self.assertEqual(len(runner.commands), 1)

    def test_validation_failure_returns_one(self) -> None:
        code, stdout, stderr, _ = self.run_installer(
            [completed(["check"], code=1, stderr="bad repository")]
        )
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("Validation failed", stderr)

    def test_missing_or_unsupported_codex_returns_two(self) -> None:
        code, stdout, stderr, _ = self.run_installer(
            [completed(["check"])],
            codex=None,
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Installed", stdout)
        self.assertIn("Desktop", stderr)

        code, stdout, stderr, _ = self.run_installer(
            [completed(["check"]), completed(["codex", "plugin"], code=2, stderr="unknown command")]
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Installed", stdout)
        self.assertIn("no usable plugin subcommand", stderr)

        code, stdout, stderr, _ = self.run_installer(
            [
                completed(["check"]),
                completed(["codex", "plugin"], stdout="Codex CLI\nCommands: exec mcp help\n"),
            ]
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Installed", stdout)
        self.assertIn("no usable plugin subcommand", stderr)

    def test_success_adds_missing_marketplace_then_installs(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(["list"], stdout="personal"),
            completed(["marketplace-add"]),
            completed(["plugin-add"]),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 0)
        self.assertIn("Installed kaoyan-22408", stdout)
        self.assertEqual(stderr, "")
        self.assertEqual(runner.commands[-2][-3:-1], ["marketplace", "add"])
        self.assertEqual(runner.commands[-1][-2:], ["add", "kaoyan-22408@kaoyan-22408"])

    def test_existing_marketplace_skips_add(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(["list"], stdout=f"kaoyan-22408  {REPO.resolve()}\n"),
            completed(["plugin-add"]),
        ]
        code, stdout, _, runner = self.run_installer(results)
        self.assertEqual(code, 0)
        self.assertIn("Installed", stdout)
        self.assertEqual(len(runner.commands), 4)

    def test_same_name_with_unverified_source_is_rejected(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(["list"], stdout="kaoyan-22408  C:/different/repository"),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("ambiguous source", stderr)
        self.assertEqual(len(runner.commands), 3)

    def test_same_name_with_repo_path_suffix_is_rejected(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(["list"], stdout=f"kaoyan-22408  {REPO.resolve()}-shadow"),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("ambiguous source", stderr)
        self.assertEqual(len(runner.commands), 3)

    def test_failed_install_never_prints_installed(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(["list"], stdout=f"kaoyan-22408  {REPO.resolve()}"),
            completed(["plugin-add"], code=1, stderr="install failed"),
        ]
        code, stdout, stderr, _ = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("Unable to install", stderr)


if __name__ == "__main__":
    unittest.main()
