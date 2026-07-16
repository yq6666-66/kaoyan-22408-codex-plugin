from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

try:  # Support both unittest discovery and tests.test_* module execution.
    from .test_support import commit_all, copy_as_committed_repo  # type: ignore[import-not-found]
except ImportError:
    from test_support import commit_all, copy_as_committed_repo  # type: ignore[no-redef]
from validate_repository import ValidationError, check_git_history, validate_repo  # noqa: E402


class RepositoryMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = copy_as_committed_repo(Path(self.temporary.name) / "repo")
        self.plugin = self.repo / "plugins/kaoyan-22408"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            validate_repo(self.repo, verify_evidence=False, scan_history=False)

    def test_extra_release_file_is_rejected(self) -> None:
        (self.plugin / ".codex-plugin" / "extra.json").write_text("{}\n", encoding="utf-8")
        self.assert_invalid()

    def test_crlf_release_text_is_rejected(self) -> None:
        path = self.plugin / "references" / "capability-routing-contract.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assert_invalid()

    def test_invalid_utf8_is_rejected(self) -> None:
        path = self.plugin / "references" / "evidence-copyright-contract.md"
        path.write_bytes(b"\xff\xfe")
        self.assert_invalid()

    def test_malformed_yaml_is_rejected(self) -> None:
        path = self.plugin / "skills" / "kaoyan-408-tutor" / "agents" / "openai.yaml"
        path.write_text("interface: [unterminated\n", encoding="utf-8", newline="\n")
        self.assert_invalid()

    def test_duplicate_yaml_key_is_rejected(self) -> None:
        path = self.plugin / "skills" / "kaoyan-408-tutor" / "agents" / "openai.yaml"
        text = path.read_text(encoding="utf-8")
        path.write_text(text + "interface: {}\n", encoding="utf-8", newline="\n")
        self.assert_invalid()

    def test_likely_secret_is_rejected(self) -> None:
        path = self.plugin / "references" / "evidence-copyright-contract.md"
        fake_token = "ghp_" + ("A" * 36)
        path.write_text(path.read_text(encoding="utf-8") + fake_token + "\n", encoding="utf-8", newline="\n")
        self.assert_invalid()

    def test_jwt_and_cloud_credentials_are_rejected(self) -> None:
        path = self.plugin / "references" / "evidence-copyright-contract.md"
        original = path.read_text(encoding="utf-8")
        mutations = {
            "jwt": "eyJ" + ("A" * 12) + "." + ("B" * 20) + "." + ("C" * 20),
            "slack": "xoxb-" + ("1" * 24),
            "aws-secret": "aws_secret_access_key=" + ("A" * 40),
            "azure-account-key": "AccountKey=" + ("Q" * 44),
        }
        for label, value in mutations.items():
            with self.subTest(label=label):
                path.write_text(original + value + "\n", encoding="utf-8", newline="\n")
                self.assert_invalid()
        path.write_text(original, encoding="utf-8", newline="\n")

    def test_additional_private_key_and_source_token_categories_are_rejected(self) -> None:
        path = self.plugin / "references" / "evidence-copyright-contract.md"
        original = path.read_text(encoding="utf-8")
        mutations = {
            "encrypted-private-key": "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
            "pgp-private-key": "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----",
            "npm-token": "npm_" + ("N" * 36),
            "gitlab-token": "glpat-" + ("G" * 24),
        }
        for label, value in mutations.items():
            with self.subTest(label=label):
                path.write_text(original + value + "\n", encoding="utf-8", newline="\n")
                self.assert_invalid()
        path.write_text(original, encoding="utf-8", newline="\n")

    def test_removed_system_marker_is_rejected(self) -> None:
        path = self.plugin / "references" / "evidence-copyright-contract.md"
        marker = "local" + "Storage"
        path.write_text(path.read_text(encoding="utf-8") + marker + "\n", encoding="utf-8", newline="\n")
        self.assert_invalid()

    def test_deleted_secret_is_still_rejected_from_git_history(self) -> None:
        path = self.repo / "private-note.txt"
        path.write_text("xoxb-" + ("9" * 24) + "\n", encoding="utf-8", newline="\n")
        commit_all(self.repo, "add accidental secret")
        path.unlink()
        commit_all(self.repo, "remove accidental secret")
        with self.assertRaisesRegex(ValidationError, "Git history contains a likely secret"):
            check_git_history(self.repo)

    def test_deleted_generic_cloud_secret_is_rejected_from_git_history(self) -> None:
        path = self.repo / "temporary-config.txt"
        value = "client_secret=" + ("S" * 40)
        path.write_text(value + "\n", encoding="utf-8", newline="\n")
        commit_all(self.repo, "add temporary config")
        path.unlink()
        commit_all(self.repo, "remove temporary config")
        with self.assertRaisesRegex(ValidationError, "Git history contains a likely secret"):
            check_git_history(self.repo)

    def test_deleted_private_data_path_is_still_rejected_from_git_history(self) -> None:
        path = self.repo / "corpus" / "private.txt"
        path.parent.mkdir()
        path.write_text("private\n", encoding="utf-8", newline="\n")
        commit_all(self.repo, "add private data path")
        path.unlink()
        path.parent.rmdir()
        commit_all(self.repo, "remove private data path")
        with self.assertRaisesRegex(ValidationError, "removed private-data path"):
            check_git_history(self.repo)

    def test_secret_in_commit_message_is_rejected(self) -> None:
        marker = "ghp_" + ("Z" * 36)
        path = self.repo / "harmless.txt"
        path.write_text("harmless\n", encoding="utf-8", newline="\n")
        commit_all(self.repo, marker)
        with self.assertRaisesRegex(ValidationError, "Git history contains a likely secret"):
            check_git_history(self.repo)

    def test_additional_secret_categories_are_rejected_from_git_history(self) -> None:
        mutations = {
            "encrypted-private-key": "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
            "pgp-private-key": "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----",
            "npm-token": "npm_" + ("N" * 36),
            "gitlab-token": "glpat-" + ("G" * 24),
        }
        for label, value in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                repo = copy_as_committed_repo(Path(temporary) / "repo")
                path = repo / "temporary-secret.txt"
                path.write_text(value + "\n", encoding="utf-8", newline="\n")
                commit_all(repo, f"add {label} fixture")
                with self.assertRaisesRegex(
                    ValidationError,
                    "Git history contains a likely secret",
                ):
                    check_git_history(repo)


if __name__ == "__main__":
    unittest.main()
