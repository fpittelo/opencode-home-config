#!/usr/bin/env python3
"""Regression tests for check_pin_freshness_workflow.py (#446, gate 19).

stdlib unittest only: no pytest, no third-party imports beyond the checker's
own, no network, no container. Fixture cases write throwaway
``.github/workflows`` trees and mutate the real ``pin-freshness.yml`` text,
so every MADR-0026 invariant (C1–C12) is exercised in isolation; the last
class runs the CLI against this repository as the positive control.

Why this gate exists (#446, MADR-0026 C6): the pin-freshness workflow is a
read-only signal over a supply-chain control, and its blast radius must be
machine-checkable so it cannot regress silently on the next workflow edit —
an over-privileged token, a PAT reference, a silent-fresh-on-failure branch,
or an unstaggered cron each defeat the decision's drivers (least privilege,
credential hygiene, signal integrity, zero-lag cadence).

Run:
    python3 harness/config-validation/test_check_pin_freshness_workflow.py
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_pin_freshness_workflow as checker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "check_pin_freshness_workflow.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_WORKFLOW = (REPO_ROOT / ".github/workflows/pin-freshness.yml").read_text(
    encoding="utf-8"
)
REAL_DEEP = (REPO_ROOT / ".github/workflows/deep-validation.yml").read_text(
    encoding="utf-8"
)

# Exact lines of the real workflow the fixtures mutate (asserted present, so a
# rename of the real file breaks loudly here instead of silently).
REAL_JOB_PERMS = "      contents: read\n      issues: write\n"
REAL_CHECKOUT_WITH = "        with:\n          persist-credentials: false\n"

# C9 (review 5910211237): each inconclusive branch carries its clears BEFORE
# finish() exports the values. Sentinels locate the branch; the *_CLEARS blocks
# are the exact target text the negative fixtures mutate.
PIN_SENTINEL = 'if [ -z "$PINNED" ] || ! semver_shaped "$PINNED"; then'
TAG_SENTINEL = 'if ! semver_shaped "$UPSTREAM_TAG"; then'
PUB_SENTINEL = 'if ! iso_shaped "$PUBLISHED"; then'
TAG_CLEARS = (
    '            UPSTREAM_TAG=""\n'
    '            PUBLISHED=""\n'
    '            RESULT="unknown"\n'
    '            REASON="upstream tag missing or not semver-shaped (parse failure)"\n'
    '            finish\n'
)
PUB_CLEARS = (
    '            PUBLISHED=""\n'
    '            RESULT="unknown"\n'
    '            REASON="upstream published_at missing or not ISO-8601 Z (parse failure)"\n'
    '            finish\n'
)
PIN_CLEARS = (
    '            PINNED=""\n'
    '            RESULT="unknown"\n'
    '            REASON="install.sh pin read or semver parse failed"\n'
    '            finish\n'
)


def build_repo(
    *,
    workflow: str | None = REAL_WORKFLOW,
    deep: str | None = REAL_DEEP,
) -> Path:
    """Throwaway repo tree with the given workflow texts (None = file absent)."""
    root = Path(tempfile.mkdtemp())
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    if workflow is not None:
        (workflows / "pin-freshness.yml").write_text(workflow, encoding="utf-8")
    if deep is not None:
        (workflows / "deep-validation.yml").write_text(deep, encoding="utf-8")
    return root


def mutated(needle: str, replacement: str) -> str:
    """Real workflow text with one exact replacement (fails loudly if absent)."""
    assert needle in REAL_WORKFLOW, f"fixture needle absent from real file: {needle!r}"
    return REAL_WORKFLOW.replace(needle, replacement)


def run_checker(root: Path) -> subprocess.CompletedProcess:
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


class FilePresence(FixtureTestCase):
    """Fail-closed on missing or unparsable inputs."""

    def test_missing_workflow_fails(self) -> None:
        self.assert_finding(
            checker.check_repo(build_repo(workflow=None)), "pin-freshness.yml"
        )

    def test_missing_deep_validation_fails(self) -> None:
        self.assert_finding(
            checker.check_repo(build_repo(deep=None)), "deep-validation.yml"
        )

    def test_unparsable_workflow_fails(self) -> None:
        self.assert_finding(
            checker.check_repo(build_repo(workflow="jobs: [unclosed")), "YAML"
        )


class PermissionsExact(FixtureTestCase):
    """C1 — job permissions exactly {{contents: read, issues: write}}."""

    def test_real_permissions_pass(self) -> None:
        self.assertIn(REAL_JOB_PERMS, REAL_WORKFLOW)
        self.assert_clean(checker.check_repo(build_repo()))

    def test_no_top_level_permissions(self) -> None:
        self.assertNotIn("\npermissions:", REAL_WORKFLOW)

    def test_extra_permission_key_fails(self) -> None:
        workflow = mutated(
            REAL_JOB_PERMS, REAL_JOB_PERMS + "      metadata: read\n"
        )
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "exactly"
        )

    def test_wrong_value_fails(self) -> None:
        workflow = mutated(REAL_JOB_PERMS, "      contents: read\n      issues: read\n")
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "exactly"
        )

    def test_contents_write_fails(self) -> None:
        workflow = mutated(
            REAL_JOB_PERMS, "      contents: write\n      issues: write\n"
        )
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "contents: write"
        )

    def test_pull_requests_write_fails(self) -> None:
        workflow = REAL_WORKFLOW + "  # pull-requests: write\n"
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "pull-requests: write"
        )

    def test_actions_write_fails(self) -> None:
        workflow = REAL_WORKFLOW + "  # actions: write\n"
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "actions: write"
        )

    def test_id_token_fails(self) -> None:
        workflow = REAL_WORKFLOW + "  # id-token: write\n"
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "id-token"
        )

    def test_missing_job_permissions_fails(self) -> None:
        workflow = mutated("    permissions:\n" + REAL_JOB_PERMS, "")
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "permissions"
        )


class TokenHygiene(FixtureTestCase):
    """C4/C5 — built-in token only, zero secrets, no persisted credentials."""

    def test_secrets_reference_fails(self) -> None:
        workflow = mutated(
            "GH_TOKEN: ${{ github.token }}", "GH_TOKEN: ${{ secrets.RELEASE_PAT }}"
        )
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "secrets."
        )

    def test_pat_env_var_fails(self) -> None:
        workflow = mutated(
            "GH_TOKEN: ${{ github.token }}", "GITHUB_TOKEN: ${{ secrets.CI_PAT }}"
        )
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "secrets."
        )

    def test_persist_credentials_true_fails(self) -> None:
        workflow = mutated("persist-credentials: false", "persist-credentials: true")
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "persist-credentials"
        )

    def test_persist_credentials_removed_fails(self) -> None:
        workflow = mutated(REAL_CHECKOUT_WITH, "")
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "persist-credentials"
        )

    def test_builtin_token_present_in_real_file(self) -> None:
        self.assertIn("${{ github.token }}", REAL_WORKFLOW)


class TriState(FixtureTestCase):
    """C11 — fresh | drift | unknown; failures map to unknown, never fresh."""

    def test_all_three_states_present(self) -> None:
        for state in ("fresh", "drift", "unknown"):
            self.assertIn(state, REAL_WORKFLOW)

    def test_unknown_failure_paths_present(self) -> None:
        self.assertGreaterEqual(REAL_WORKFLOW.count('RESULT="unknown"'), 2)

    def test_fresh_on_failure_branch_fails(self) -> None:
        workflow = mutated('RESULT="unknown"', 'RESULT="fresh"')
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "failure"
        )

    def test_fresh_fallback_or_branch_fails(self) -> None:
        workflow = REAL_WORKFLOW + '  # gh api ... || echo "result=fresh"\n'
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "failure"
        )

    def test_non_failing_no_exit_nonzero(self) -> None:
        self.assertNotRegex(REAL_WORKFLOW, r"\bexit [1-9]")

    def test_exit_nonzero_injected_fails(self) -> None:
        workflow = REAL_WORKFLOW + "  # exit 1\n"
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "exit 1"
        )

    def test_warning_annotation_present(self) -> None:
        self.assertIn("::warning::", REAL_WORKFLOW)

    def test_summary_written(self) -> None:
        self.assertIn("GITHUB_STEP_SUMMARY", REAL_WORKFLOW)


class UnvalidatedInterpolation(FixtureTestCase):
    """C9 — an inconclusive branch must blank what it could not validate.

    Review 5910211237 (PR #453): the tag-shape and published-shape failure
    branches finished with RESULT=unknown but left the raw upstream-controlled
    string in scope, and the reconcile step interpolates it into the
    bot-managed issue body (table cell + constructed URLs). Agents read issues
    over MCP, so that is the indirect prompt-injection surface C9 closes:
    every interpolated value must be validated or empty.
    """

    def branch(self, text: str, sentinel: str) -> str:
        """The branch body from its `if` line through the matching `fi`."""
        start = text.find(sentinel)
        self.assertGreaterEqual(start, 0, f"branch sentinel absent: {sentinel!r}")
        lines = text[start:].splitlines()
        collected = [lines[0]]
        for line in lines[1:]:
            collected.append(line)
            if line.strip() == "fi":
                break
        return "\n".join(collected)

    def assert_cleared_first(self, branch: str, variable: str) -> None:
        assignment = f'{variable}=""'
        self.assertIn(
            assignment,
            branch,
            f"{variable} is interpolated into the issue body but this "
            "inconclusive branch never blanks it (MADR-0026 C9, review "
            "5910211237)",
        )
        # The `finish` COMMAND line — not the word inside a comment.
        finish_match = re.search(r"(?m)^\s*finish\s*$", branch)
        self.assertIsNotNone(finish_match, "branch does not call finish")
        assert finish_match is not None
        self.assertLess(
            branch.index(assignment),
            finish_match.start(),
            f"{variable} must be blanked BEFORE finish() exports it "
            "(MADR-0026 C9)",
        )

    def test_tag_failure_branch_blanks_upstream_values(self) -> None:
        branch = self.branch(REAL_WORKFLOW, TAG_SENTINEL)
        self.assertIn('RESULT="unknown"', branch)
        self.assert_cleared_first(branch, "UPSTREAM_TAG")
        self.assert_cleared_first(branch, "PUBLISHED")

    def test_published_failure_branch_blanks_published(self) -> None:
        branch = self.branch(REAL_WORKFLOW, PUB_SENTINEL)
        self.assertIn('RESULT="unknown"', branch)
        self.assert_cleared_first(branch, "PUBLISHED")

    def test_pin_failure_branch_blanks_pinned(self) -> None:
        """Same class, third site: the pin read can fail shape validation."""
        branch = self.branch(REAL_WORKFLOW, PIN_SENTINEL)
        self.assertIn('RESULT="unknown"', branch)
        self.assert_cleared_first(branch, "PINNED")

    def test_validated_paths_keep_their_values(self) -> None:
        """The drift path must keep both values: they are validated there."""
        drift_line = 'RESULT="drift"'
        self.assertIn(drift_line, REAL_WORKFLOW)
        semver_idx = REAL_WORKFLOW.index(TAG_SENTINEL)
        drift_idx = REAL_WORKFLOW.index(drift_line)
        self.assertLess(semver_idx, drift_idx, "drift must follow both shape checks")

    def test_tag_branch_leaving_upstream_tag_fails(self) -> None:
        workflow = mutated(TAG_CLEARS, TAG_CLEARS.replace('            UPSTREAM_TAG=""\n', ""))
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "UPSTREAM_TAG", "C9"
        )

    def test_tag_branch_leaving_published_fails(self) -> None:
        workflow = mutated(TAG_CLEARS, TAG_CLEARS.replace('            PUBLISHED=""\n', ""))
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "PUBLISHED", "C9"
        )

    def test_published_branch_leaving_published_fails(self) -> None:
        workflow = mutated(PUB_CLEARS, PUB_CLEARS.replace('            PUBLISHED=""\n', ""))
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "PUBLISHED", "C9"
        )

    def test_pin_branch_leaving_pinned_fails(self) -> None:
        workflow = mutated(PIN_CLEARS, PIN_CLEARS.replace('            PINNED=""\n', ""))
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "PINNED", "C9"
        )

    def test_clear_after_finish_fails(self) -> None:
        """Ordering matters: a clear after finish() never reaches the output."""
        swapped = (
            '            RESULT="unknown"\n'
            '            REASON="upstream tag missing or not semver-shaped (parse failure)"\n'
            '            finish\n'
            '            UPSTREAM_TAG=""\n'
            '            PUBLISHED=""\n'
        )
        workflow = mutated(TAG_CLEARS, swapped)
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "before finish"
        )


class CronStagger(FixtureTestCase):
    """AC1 — weekly Monday cron staggered off the deep-validation slot."""

    def test_real_crons_differ(self) -> None:
        pin = checker.crons_of(REAL_WORKFLOW)
        deep = checker.crons_of(REAL_DEEP)
        self.assertEqual(pin, ["30 5 * * 1"])
        self.assertEqual(deep, ["0 5 * * 1"])

    def test_unstaggered_cron_fails(self) -> None:
        workflow = mutated('"30 5 * * 1"', '"0 5 * * 1"')
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "stagger"
        )

    def test_non_monday_cron_fails(self) -> None:
        workflow = mutated('"30 5 * * 1"', '"30 5 * * 2"')
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "Monday"
        )

    def test_schedule_removed_fails(self) -> None:
        workflow = mutated(
            '  schedule:\n    - cron: "30 5 * * 1" # Mondays 05:30 UTC — staggered off deep-validation (05:00 UTC, C12)\n',
            "",
        )
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "schedule"
        )

    def test_workflow_dispatch_present(self) -> None:
        self.assertIn("workflow_dispatch", REAL_WORKFLOW)


class DriftIssueMechanics(FixtureTestCase):
    """C7–C10 — deterministic issue, fixed labels, notification posture."""

    def test_managed_marker_present(self) -> None:
        self.assertIn(checker.MANAGED_MARKER, REAL_WORKFLOW)

    def test_marker_removed_fails(self) -> None:
        workflow = mutated(checker.MANAGED_MARKER, "<!-- other-bot -->")
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "marker"
        )

    def test_fixed_labels_present(self) -> None:
        self.assertIn("type::task", REAL_WORKFLOW)
        self.assertIn("agent::devops", REAL_WORKFLOW)

    def test_status_label_write_fails(self) -> None:
        workflow = REAL_WORKFLOW + '  # --label "status::in-progress"\n'
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "status::"
        )

    def test_issue_auto_close_fails(self) -> None:
        workflow = REAL_WORKFLOW + "  # gh issue close 1\n"
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "gh issue close"
        )

    def test_reviewer_statement_present(self) -> None:
        self.assertIn("@devfpittelo", REAL_WORKFLOW)

    def test_reviewer_statement_removed_fails(self) -> None:
        workflow = mutated("@devfpittelo", "@someone-else")
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "@devfpittelo"
        )

    def test_asset_and_checksums_named(self) -> None:
        self.assertIn(checker.ASSET_NAME, REAL_WORKFLOW)
        self.assertIn("checksums", REAL_WORKFLOW)

    def test_upstream_latest_read_present(self) -> None:
        self.assertIn("releases/latest", REAL_WORKFLOW)
        self.assertIn(checker.UPSTREAM_REPO, REAL_WORKFLOW)


class NoPersistedState(FixtureTestCase):
    """C2 — install.sh is the single pin; no cache, no second literal."""

    def test_no_second_version_literal(self) -> None:
        import re

        self.assertIsNone(
            re.search(r"\bv?\d+\.\d+\.\d+", REAL_WORKFLOW),
            "the workflow must not carry a version literal (reads install.sh)",
        )

    def test_version_literal_injected_fails(self) -> None:
        workflow = REAL_WORKFLOW + "  # pin was 2.1.0 as of 2026-11-15\n"
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "version literal"
        )

    def test_no_cache_action(self) -> None:
        self.assertNotIn("actions/cache", REAL_WORKFLOW)

    def test_cache_step_injected_fails(self) -> None:
        workflow = REAL_WORKFLOW + "  # - uses: actions/cache@v4\n"
        self.assert_finding(
            checker.check_repo(build_repo(workflow=workflow)), "cache"
        )


class RealRepositoryControl(unittest.TestCase):
    """Positive control: the real repo's workflow passes the CLI checker."""

    def test_real_repo_passes(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        self.assertIn("PASS check_pin_freshness_workflow", proc.stdout)

    def test_constants_match_madr_0026(self) -> None:
        self.assertEqual(
            checker.ALLOWED_PERMISSIONS, {"contents": "read", "issues": "write"}
        )
        self.assertEqual(checker.DRIFT_LABELS, ("agent::devops", "type::task"))
        self.assertEqual(
            checker.MANAGED_MARKER, "<!-- pin-freshness:managed-issue -->"
        )
        self.assertEqual(checker.UPSTREAM_REPO, "github/github-mcp-server")
        self.assertEqual(
            checker.ASSET_NAME, "github-mcp-server_Linux_x86_64.tar.gz"
        )


if __name__ == "__main__":
    unittest.main()
