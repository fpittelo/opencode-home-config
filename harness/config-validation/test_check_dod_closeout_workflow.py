#!/usr/bin/env python3
"""Regression suite for the DoD closeout workflow blast-radius gate (#481, AC11/R5-C12).

The gate (``check_dod_closeout_workflow.py``) machine-pins the report-only
contract of ``.github/workflows/dod-closeout.yml``:

  * job-level permissions EXACTLY ``{contents: read, checks: read,
    statuses: read, pull-requests: read, issues: write}`` — ``statuses: read``
    is mandatory because the DV verdict is a legacy commit status (R5-C1);
  * NO top-level ``permissions:`` block, zero ``secrets.*`` references, the
    built-in ``${{ github.token }}`` as the only credential surface, every
    ``actions/checkout`` step with ``persist-credentials: false`` (R5-C2);
  * a write surface limited to issue-comment create/update — zero
    issue-close, label, commit-status or check-run writes (R5-C10);
  * the always-exit-0 report-only contract (no non-zero exit anywhere);
  * the push-to-main trigger, the single job, the concurrency group, and the
    invocation of the unittest-covered verifier module;
  * the CI-scoping preconditions (AC4): ``ci.yml`` is the single-job
    ``CI Pipeline`` workflow whose job name matches the verifier's
    name-scoping constant.

The suite carries negative fixtures for every invariant plus the real-repo
positive control (#142 A1 pattern). Per #481 AC11 it is wired into the
per-push Tier A gate (gate 17 of ``run-config-gate.sh``) — a suite executed
by no gate is advisory only — so the suite IS the direct check
(``test_pin_consistency.py`` precedent, < 1 s).

Run:
    python3 harness/config-validation/test_check_dod_closeout_workflow.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_dod_closeout_workflow as checker  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "harness" / "config-validation" / "check_dod_closeout_workflow.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "dod-closeout.yml"
VERIFIER = REPO_ROOT / "harness" / "dod_closeout_verify.py"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def real(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def make_root(
    tmp: Path,
    workflow: str | None = None,
    verifier: str | None = None,
    ci: str | None = None,
) -> Path:
    """A minimal repo tree carrying the three pinned files (real by default)."""
    root = tmp / "repo"
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "harness").mkdir()
    (root / ".github" / "workflows" / "dod-closeout.yml").write_text(
        workflow if workflow is not None else real(WORKFLOW), encoding="utf-8"
    )
    (root / "harness" / "dod_closeout_verify.py").write_text(
        verifier if verifier is not None else real(VERIFIER), encoding="utf-8"
    )
    (root / ".github" / "workflows" / "ci.yml").write_text(
        ci if ci is not None else real(CI), encoding="utf-8"
    )
    return root


def findings_for(**overrides: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        return checker.check_repo(make_root(Path(tmp), **overrides))


class PositiveControlTest(unittest.TestCase):
    """The real repository satisfies every pinned invariant (#142 A1)."""

    def test_real_repo_has_no_findings(self) -> None:
        self.assertEqual(checker.check_repo(REPO_ROOT), [])

    def test_checker_exits_zero_on_the_real_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECKER), str(REPO_ROOT)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            result.returncode, 0, f"positive control failed: {result.stdout}"
        )

    def test_checker_exits_nonzero_on_a_broken_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(
                Path(tmp),
                workflow=real(WORKFLOW).replace(
                    "      issues: write", "      issues: write\n      actions: write", 1
                ),
            )
            result = subprocess.run(
                [sys.executable, str(CHECKER), str(root)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 1)


class WorkflowStructureFixturesTest(unittest.TestCase):
    """Negative fixtures: workflow posture violations are findings."""

    def test_missing_workflow_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / "harness").mkdir(parents=True)
            (root / "harness" / "dod_closeout_verify.py").write_text(
                real(VERIFIER), encoding="utf-8"
            )
            findings = checker.check_repo(root)
            self.assertTrue(any("dod-closeout.yml" in f for f in findings))

    def test_top_level_permissions_block_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace(
            "jobs:", "permissions:\n  contents: write\n\njobs:", 1
        )
        self.assertTrue(
            any("top-level permissions" in f for f in findings_for(workflow=workflow))
        )

    def test_extra_job_permission_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace(
            "      issues: write", "      issues: write\n      actions: write", 1
        )
        self.assertTrue(
            any("permissions must be exactly" in f for f in findings_for(workflow=workflow))
        )

    def test_missing_statuses_read_is_a_finding(self) -> None:
        # R5-C1: statuses: read is mandatory — the DV verdict is a legacy
        # commit status, not a check run.
        workflow = real(WORKFLOW).replace("      statuses: read\n", "", 1)
        self.assertTrue(
            any("statuses" in f for f in findings_for(workflow=workflow))
        )

    def test_checkout_without_persist_credentials_false_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace(
            "        with:\n          persist-credentials: false\n", "", 1
        )
        self.assertTrue(
            any("persist-credentials" in f for f in findings_for(workflow=workflow))
        )

    def test_secrets_reference_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace(
            "${{ github.token }}", "${{ secrets.GITHUB_TOKEN }}"
        )
        self.assertTrue(
            any("secrets." in f for f in findings_for(workflow=workflow))
        )

    def test_removed_builtin_token_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace(
            "GH_TOKEN: ${{ github.token }}", "GH_TOKEN: ${{ env.SOMETHING }}"
        )
        self.assertTrue(
            any("github.token" in f for f in findings_for(workflow=workflow))
        )

    def test_wrong_trigger_branch_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace("branches: [main]", "branches: [dev]", 1)
        self.assertTrue(
            any("push" in f and "main" in f for f in findings_for(workflow=workflow))
        )

    def test_removed_concurrency_group_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace(
            "concurrency:\n  group: dod-closeout\n  cancel-in-progress: false\n\n", "", 1
        )
        self.assertTrue(
            any("concurrency" in f for f in findings_for(workflow=workflow))
        )

    def test_verifier_not_invoked_is_a_finding(self) -> None:
        workflow = real(WORKFLOW).replace(
            "python3 harness/dod_closeout_verify.py", "python3 other_script.py"
        )
        self.assertTrue(
            any("dod_closeout_verify.py" in f for f in findings_for(workflow=workflow))
        )

    def test_second_job_is_a_finding(self) -> None:
        workflow = (
            real(WORKFLOW)
            + "\n  second-job:\n    runs-on: ubuntu-latest\n    steps: []\n"
        )
        self.assertTrue(
            any("exactly one job" in f for f in findings_for(workflow=workflow))
        )


class VerifierSurfaceFixturesTest(unittest.TestCase):
    """Negative fixtures: verifier write-surface / exit / parity violations."""

    def test_delete_call_is_a_finding(self) -> None:
        verifier = real(VERIFIER) + '\ngh_api(["-X", "DELETE", "repos/o/r/issues/comments/1"])\n'
        self.assertTrue(
            any("DELETE" in f for f in findings_for(verifier=verifier))
        )

    def test_put_call_is_a_finding(self) -> None:
        verifier = real(VERIFIER) + '\ngh_api(["-X", "PUT", "repos/o/r/collaborators/x"])\n'
        self.assertTrue(
            any("PUT" in f for f in findings_for(verifier=verifier))
        )

    def test_non_comment_post_is_a_finding(self) -> None:
        # A commit-status write on the POST surface — forbidden by R5-C10.
        verifier = (
            real(VERIFIER)
            + '\ngh_api(["-X", "POST", f"repos/{repo}/statuses/{sha}", "-f", "state=success"])\n'
        )
        self.assertTrue(
            any("issue-comment" in f for f in findings_for(verifier=verifier))
        )

    def test_gh_issue_subcommand_is_a_finding(self) -> None:
        verifier = real(VERIFIER) + '\nsubprocess.run("gh issue close 1", shell=True)\n'
        self.assertTrue(
            any("gh issue" in f for f in findings_for(verifier=verifier))
        )

    def test_nonzero_exit_is_a_finding(self) -> None:
        verifier = real(VERIFIER) + "\nimport sys\nsys.exit(1)\n"
        self.assertTrue(
            any("exit" in f for f in findings_for(verifier=verifier))
        )

    def test_drifted_reviewer_id_is_a_finding(self) -> None:
        # Identity parity with harness/probes/verify-github-identities.py.
        verifier = real(VERIFIER).replace(
            "REVIEWER_ID = 327061373", "REVIEWER_ID = 327061372"
        )
        self.assertTrue(
            any("327061373" in f for f in findings_for(verifier=verifier))
        )

    def test_drifted_reviewer_login_is_a_finding(self) -> None:
        verifier = real(VERIFIER).replace(
            'REVIEWER_LOGIN = "devfpittelo"', 'REVIEWER_LOGIN = "fpittelo"'
        )
        self.assertTrue(
            any("devfpittelo" in f for f in findings_for(verifier=verifier))
        )

    def test_removed_marker_is_a_finding(self) -> None:
        # AC9: the hidden marker locates the one comment per issue.
        verifier = real(VERIFIER).replace(
            'COMMENT_MARKER = "<!-- dod-closeout-signal -->"',
            'COMMENT_MARKER = "<!-- other-marker -->"',
        )
        self.assertTrue(
            any("dod-closeout-signal" in f for f in findings_for(verifier=verifier))
        )

    def test_removed_dv_context_is_a_finding(self) -> None:
        verifier = real(VERIFIER).replace(
            'DV_CONTEXT = "deep-validation"', 'DV_CONTEXT = "other"'
        )
        self.assertTrue(
            any("deep-validation" in f for f in findings_for(verifier=verifier))
        )

    def test_removed_report_only_statement_is_a_finding(self) -> None:
        # AC10/AC11: the comment must state the signal-not-gate contract.
        verifier = real(VERIFIER).replace("does not close the DoD gate", "closes the DoD gate")
        self.assertTrue(
            any("does not close the DoD gate" in f for f in findings_for(verifier=verifier))
        )

    def test_removed_ci_check_run_name_is_a_finding(self) -> None:
        # AC4 preconditions: the name-scoping constant must not drift.
        verifier = real(VERIFIER).replace(
            'CI_CHECK_RUN_NAME = "Quality Gate (native, zero Docker)"',
            'CI_CHECK_RUN_NAME = "Quality Gate (renamed)"',
        )
        self.assertTrue(
            any("Quality Gate (native, zero Docker)" in f for f in findings_for(verifier=verifier))
        )

    def test_label_write_is_a_finding(self) -> None:
        verifier = (
            real(VERIFIER)
            + '\ngh_api(["-X", "POST", f"repos/{repo}/issues/{n}/labels", "-f", "labels[]=status::done"])\n'
        )
        # The labels endpoint has no "comments" segment — caught by the
        # issue-comment write-surface allowlist.
        self.assertTrue(
            any("issue-comment" in f for f in findings_for(verifier=verifier))
        )


class CiPreconditionFixturesTest(unittest.TestCase):
    """AC4 preconditions pinned against ci.yml (the scoping source)."""

    def test_renamed_ci_workflow_is_a_finding(self) -> None:
        ci = real(CI).replace("name: CI Pipeline", "name: Trunk Pipeline", 1)
        self.assertTrue(
            any("CI Pipeline" in f for f in findings_for(ci=ci))
        )

    def test_multi_job_ci_is_a_finding(self) -> None:
        # A second ci.yml job would silently narrow the CI verdict — the
        # scoping must be consciously re-validated (AC4).
        ci = real(CI) + "\n  second-job:\n    runs-on: ubuntu-latest\n    steps: []\n"
        self.assertTrue(
            any("exactly one job" in f for f in findings_for(ci=ci))
        )

    def test_renamed_ci_job_is_a_finding(self) -> None:
        ci = real(CI).replace(
            "name: Quality Gate (native, zero Docker)", "name: Renamed Job", 1
        )
        self.assertTrue(
            any("Quality Gate (native, zero Docker)" in f for f in findings_for(ci=ci))
        )


if __name__ == "__main__":
    unittest.main()
