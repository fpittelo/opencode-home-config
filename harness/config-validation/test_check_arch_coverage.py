#!/usr/bin/env python3
"""Regression tests for check_arch_coverage.sh (#421, gate 21).

stdlib unittest only: no pytest, no third-party imports, no network. Fixture
cases build throwaway git repositories with synthetic two-commit diffs and
invoke the REAL gate script (the exact logic that lands in ci.yml — the
workflow step is a thin invocation), so the path-derived architecture gate is
proven pre-merge against every scenario class that matters.

Why this gate exists (#421): the previous requires-architecture gate
triggered on a human-applied PR label that no agent can set through any
permitted path (no PR-label MCP tool, `gh api *` root-denied, `gh pr edit`
broken for labels — #304), so it passed trivially for every squad PR: a
decorative control. The replacement is path-derived and self-triggering: a
diff touching architecture-relevant paths must carry architecture
documentation in the same diff, or the job fails. `install.sh` is
deliberately EXCLUDED from the trigger set — a mechanical pin bump (e.g.
#447) must not force an ADR.

Run:
    python3 harness/config-validation/test_check_arch_coverage.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_arch_coverage.sh"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def build_repo(changed: dict[str, str | None]) -> tuple[Path, str, str]:
    """Throwaway repo: base commit (README) + head commit applying `changed`.

    A `None` value deletes the file (deletions are part of the diff surface).
    """
    root = Path(tempfile.mkdtemp())
    _git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "commit", "-q", "-m", "base")
    base = (
        subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    for path, content in changed.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(content, encoding="utf-8")
        _git(root, "add", path)
    _git(root, "commit", "-q", "--allow-empty", "-m", "head")
    head = (
        subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return root, base, head


def run_gate(root: Path, base: str, head: str) -> subprocess.CompletedProcess[str]:
    """Invoke the exact script ci.yml invokes, against a synthetic diff."""
    return subprocess.run(
        ["bash", str(SCRIPT), base, head],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )


def gate(*changed: tuple[str, str | None]) -> subprocess.CompletedProcess[str]:
    repo, base, head = build_repo(dict(changed))
    return run_gate(repo, base, head)


class FixtureTestCase(unittest.TestCase):
    def assert_pass(self, proc: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(
            proc.returncode,
            0,
            f"expected PASS, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        self.assertIn("PASS", proc.stdout)

    def assert_fail(self, proc: subprocess.CompletedProcess[str], *fragments: str) -> None:
        self.assertEqual(
            proc.returncode,
            1,
            f"expected FAIL, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        for fragment in fragments:
            self.assertIn(fragment, proc.stdout)


class NegativeControl(FixtureTestCase):
    """AC2 — the gate fails an architecture-relevant diff without docs."""

    def test_opencode_jsonc_without_docs_fails(self) -> None:
        proc = gate(("opencode.jsonc", "{}"))
        self.assert_fail(
            proc,
            "opencode.jsonc",
            "docs/adr/",
            "docs/architecture/arc42/",
        )

    def test_agents_only_fails(self) -> None:
        proc = gate(("agents/devops.md", "spec\n"))
        self.assert_fail(proc, "agents/devops.md")

    def test_workflows_only_fails(self) -> None:
        proc = gate((".github/workflows/ci.yml", "on:\n"))
        self.assert_fail(proc, ".github/workflows/ci.yml")

    def test_harness_and_skills_without_docs_fails(self) -> None:
        proc = gate(
            ("harness/run.sh", "x\n"),
            ("skills/kis-yagni/SKILL.md", "y\n"),
        )
        self.assert_fail(proc, "harness/run.sh", "skills/kis-yagni/SKILL.md")

    def test_deleted_arch_file_fails(self) -> None:
        """Deletions are part of the diff surface (#405-adjacent honesty)."""
        repo, base, head = build_repo({})
        (repo / "harness").mkdir(parents=True, exist_ok=True)
        (repo / "harness" / "gone.sh").write_text("x\n", encoding="utf-8")
        _git(repo, "add", "harness/gone.sh")
        _git(repo, "commit", "-q", "-m", "add")
        mid = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (repo / "harness" / "gone.sh").unlink()
        _git(repo, "add", "harness/gone.sh")
        _git(repo, "commit", "-q", "-m", "delete")
        new_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        proc = run_gate(repo, mid, new_head)
        self.assert_fail(proc, "harness/gone.sh")


class PositiveControl(FixtureTestCase):
    """AC3 — complete diffs pass; docs-only and excluded paths never trip."""

    def test_arch_path_plus_arc42_doc_passes(self) -> None:
        self.assert_pass(
            gate(
                ("opencode.jsonc", "{}"),
                ("docs/architecture/arc42/03-cross-cutting-and-security.md", "x\n"),
            )
        )

    def test_arch_path_plus_adr_passes(self) -> None:
        self.assert_pass(
            gate(
                ("harness/run.sh", "x\n"),
                ("skills/kis-yagni/SKILL.md", "y\n"),
                ("docs/adr/0027-example.md", "adr\n"),
            )
        )

    def test_docs_only_diff_passes(self) -> None:
        self.assert_pass(
            gate(("docs/adr/0027-example.md", "adr\n"))
        )

    def test_install_sh_excluded(self) -> None:
        """install.sh is deliberately out of the trigger set (#447 class)."""
        self.assert_pass(gate(("install.sh", "#!/usr/bin/env bash\n")))

    def test_readme_only_passes(self) -> None:
        self.assert_pass(gate(("README.md", "x\n")))

    def test_empty_diff_passes(self) -> None:
        repo, sha, _ = build_repo({})
        self.assert_pass(run_gate(repo, sha, sha))

    def test_real_repo_noop_diff_passes(self) -> None:
        """Positive control on the real repo: an empty diff passes cleanly."""
        head = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assert_pass(run_gate(REPO_ROOT, head, head))


class MessageQuality(FixtureTestCase):
    """A failure must name the trigger paths hit AND the accepted doc paths."""

    def test_failure_lists_all_hit_paths(self) -> None:
        proc = gate(
            ("agents/devops.md", "x\n"),
            (".github/workflows/ci.yml", "on:\n"),
            ("opencode.jsonc", "{}"),
        )
        for fragment in (
            "agents/devops.md",
            ".github/workflows/ci.yml",
            "opencode.jsonc",
        ):
            self.assertIn(fragment, proc.stdout)

    def test_failure_guides_to_both_accepted_doc_paths(self) -> None:
        proc = gate(("agents/devops.md", "x\n"))
        self.assertIn("docs/adr/", proc.stdout)
        self.assertIn("docs/architecture/arc42/", proc.stdout)
        self.assertIn("install.sh", proc.stdout)  # exclusion rationale visible

    def test_pass_names_the_satisfying_doc_paths(self) -> None:
        proc = gate(
            ("opencode.jsonc", "{}"),
            ("docs/adr/0027-example.md", "adr\n"),
        )
        self.assertIn("docs/adr/0027-example.md", proc.stdout)


class FailClosedOnDiffFailure(FixtureTestCase):
    """Review 5910441948: a diff-command failure must fail the gate loudly.

    The first draft swallowed a git-diff failure with ``|| true``, yielding an
    empty CHANGED list and a misleading PASS — a fail-open on a failure path
    (e.g. an unresolvable base sha beyond the depth-60 checkout on a
    >58-commit PR chain; the OLD inline gate failed loudly in this case, and
    the replacement must too, per the house fail-closed doctrine — gate 20's
    honest-SKIP semantics, MADR-0026 C11 "unknown, never fresh"). The honest
    outcomes are PASS (verified no-op or covered diff) and FAIL (coverage gap
    OR uncomputable diff) — never a silent PASS.
    """

    def test_unresolvable_base_sha_fails_loudly(self) -> None:
        repo, _, head = build_repo({})
        bogus = "1234567890123456789012345678901234567890"
        proc = run_gate(repo, bogus, head)
        self.assertEqual(
            proc.returncode,
            1,
            f"expected FAIL on an uncomputable diff, got {proc.returncode}:\n"
            f"{proc.stdout}{proc.stderr}",
        )
        self.assertIn("could not compute the diff", proc.stdout)
        self.assertNotIn("PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
