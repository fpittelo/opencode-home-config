#!/usr/bin/env python3
"""Regression tests for check_gitleaks_allowlist.py (#448, gate 18).

stdlib unittest only: no pytest, no third-party imports, no network, no
container. Fixture cases build throwaway git repositories (``git init`` +
``git add``) and mutate the real ``.gitleaks.toml`` text, so every assertion
is exercised in isolation; the last class runs the CLI against this
repository as the positive control.

Why this gate exists (#448, the #405 defect class): a wide ``git add -A``
swept an untracked opencode runtime artifact (``service.json``, holding a
daemon credential) into a commit, and it stayed in public history for 22
days. The gate has two fail-closed assertions:

  1. no opencode runtime artifact is ever **tracked** (``git ls-files``), and
  2. the incident's ``.gitleaks.toml`` allowlist stays exactly ONE entry,
     scoped to the single historical commit AND the artifact path with
     ``condition = "AND"`` — never a path-only waiver (a future commit at that
     path must still be caught), and never carrying secret material.

Run:
    python3 harness/config-validation/test_check_gitleaks_allowlist.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_gitleaks_allowlist as checker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "check_gitleaks_allowlist.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_CONFIG = (REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
# The exact anchored path line the real config declares (fixtures mutate it).
REAL_PATH_PATTERN = r"'''^service\.json$'''"

# A fake high-entropy value, assembled from short fragments on purpose: no
# committed literal here may itself be value-shaped, or the repository's own
# diff-scoped gitleaks scan flags this test file (observed on the first CI run).
# The assembled string is 40 chars, three character classes, entropy > 4.0 —
# enough to exercise the detector at runtime.
_FRAGMENTS = ("Zx7Qw2Er", "9Tyu3Iop", "4As6Df8G", "j1Kl5Mn0", "Bv3Cx7Za")
FAKE_SECRET_LITERAL = "".join(_FRAGMENTS)
FAKE_SHA256 = "2b099acd25c872b0" + "b" * 48


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def build_repo(
    *, tracked: tuple[str, ...] = (), config: str | None = REAL_CONFIG
) -> Path:
    """Throwaway git repo with the given tracked files and gitleaks config."""
    root = Path(tempfile.mkdtemp())
    _git(root, "init", "-q", "-b", "main")
    if config is not None:
        (root / ".gitleaks.toml").write_text(config, encoding="utf-8")
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(root, "add", "README.md")
    if config is not None:
        _git(root, "add", ".gitleaks.toml")
    for name in tracked:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"password": "fixture"}\n', encoding="utf-8")
        _git(root, "add", name)
    return root


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker CLI against a repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


class FixtureTestCase(unittest.TestCase):
    def assert_finding(self, findings: list[str], *fragments: str) -> None:
        self.assertTrue(findings, "expected at least one finding, got none")
        joined = "\n".join(findings)
        for fragment in fragments:
            self.assertIn(fragment, joined)

    def assert_clean(self, findings: list[str]) -> None:
        self.assertEqual(findings, [], f"expected no findings, got: {findings}")


class TrackedRuntimeArtifacts(FixtureTestCase):
    """Assertion 1 — the #405 class can never recur silently."""

    def test_clean_repo_passes(self) -> None:
        findings = checker.check_repo(build_repo())
        self.assert_clean(findings)

    def test_tracked_service_json_fails(self) -> None:
        findings = checker.check_repo(build_repo(tracked=("service.json",)))
        self.assert_finding(findings, "service.json", "tracked")

    def test_tracked_cli_json_fails(self) -> None:
        findings = checker.check_repo(build_repo(tracked=("cli.json",)))
        self.assert_finding(findings, "cli.json", "tracked")

    def test_tracked_artifact_in_subdirectory_fails(self) -> None:
        findings = checker.check_repo(build_repo(tracked=("nested/service.json",)))
        self.assert_finding(findings, "service.json", "tracked")

    def test_non_git_directory_fails_closed(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / ".gitleaks.toml").write_text(REAL_CONFIG, encoding="utf-8")
        self.assert_finding(checker.check_repo(root), "git")


class AllowlistShape(FixtureTestCase):
    """Assertion 2 — exactly one entry, commit+path AND-scoped, no secrets."""

    def test_missing_config_fails(self) -> None:
        self.assert_finding(
            checker.check_repo(build_repo(config=None)), ".gitleaks.toml"
        )

    def test_malformed_config_fails(self) -> None:
        broken = REPO_ROOT / ".gitleaks.toml"
        self.assertTrue(broken.exists())
        self.assert_finding(
            checker.check_repo(build_repo(config="[[rules]\nnot toml")),
            ".gitleaks.toml",
        )

    def test_second_allowlist_entry_fails(self) -> None:
        config = REAL_CONFIG + (
            "\n[allowlist]\ncommits = [\"fd15509fa6cebebbb8bd02bd7a50caa639a7588a\"]\n"
        )
        self.assert_finding(
            checker.check_repo(build_repo(config=config)), "allowlist", "exactly one"
        )

    def test_path_only_allowlist_fails(self) -> None:
        """C3: a path-only waiver would mask any future commit at that path."""
        config = REAL_CONFIG.replace(
            '  condition = "AND"\n'
            '  commits = ["fd15509fa6cebebbb8bd02bd7a50caa639a7588a"]\n',
            "",
        )
        self.assert_finding(
            checker.check_repo(build_repo(config=config)), "allowlist", "commits"
        )

    def test_or_condition_fails(self) -> None:
        config = REAL_CONFIG.replace('condition = "AND"', 'condition = "OR"')
        self.assert_finding(
            checker.check_repo(build_repo(config=config)), "allowlist", "AND"
        )

    def test_missing_condition_fails(self) -> None:
        config = REAL_CONFIG.replace('  condition = "AND"\n', "")
        self.assert_finding(
            checker.check_repo(build_repo(config=config)), "allowlist", "AND"
        )

    def test_unanchored_or_broad_path_regex_fails(self) -> None:
        for broad in (r"'''service\.json'''", "'''.*'''", "'''^.*$'''"):
            with self.subTest(pattern=broad):
                self.assertIn(REAL_PATH_PATTERN, REAL_CONFIG)
                config = REAL_CONFIG.replace(REAL_PATH_PATTERN, broad)
                self.assertNotEqual(config, REAL_CONFIG)
                self.assert_finding(
                    checker.check_repo(build_repo(config=config)),
                    "allowlist",
                    "service.json",
                )

    def test_other_commit_fails(self) -> None:
        config = REAL_CONFIG.replace(
            "fd15509fa6cebebbb8bd02bd7a50caa639a7588a", "0" * 40
        )
        self.assert_finding(
            checker.check_repo(build_repo(config=config)),
            "allowlist",
            checker.PUBLIC_COMMIT,
        )

    def test_value_shaped_literal_fails(self) -> None:
        config = REAL_CONFIG + f'\n# {FAKE_SECRET_LITERAL}\n'
        self.assert_finding(
            checker.check_repo(build_repo(config=config)), "secret material"
        )

    def test_sha256_literal_fails(self) -> None:
        config = REAL_CONFIG + f'\n# {FAKE_SHA256}\n'
        self.assert_finding(checker.check_repo(build_repo(config=config)), "sha256")

    def test_password_assignment_fails(self) -> None:
        config = REAL_CONFIG + f'\n# password = "{FAKE_SECRET_LITERAL}"\n'
        self.assert_finding(
            checker.check_repo(build_repo(config=config)), "secret material"
        )

    def test_description_without_incident_context_fails(self) -> None:
        config = REAL_CONFIG.replace("Incident #448:", "Something:")
        self.assert_finding(
            checker.check_repo(build_repo(config=config)), "description"
        )


class RealRepositoryControl(unittest.TestCase):
    """Positive control: the real repo is clean and the entry is exact."""

    def test_real_repo_passes(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        self.assertIn("PASS check_gitleaks_allowlist", proc.stdout)

    def test_public_commit_constant_matches_the_incident_record(self) -> None:
        self.assertEqual(
            checker.PUBLIC_COMMIT, "fd15509fa6cebebbb8bd02bd7a50caa639a7588a"
        )


if __name__ == "__main__":
    unittest.main()
