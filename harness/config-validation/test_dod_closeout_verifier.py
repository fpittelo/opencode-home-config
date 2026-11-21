#!/usr/bin/env python3
"""Verifier-logic regression suite for the DoD closeout signal (#481, AC12/R5-C13).

stdlib unittest only: no pytest, no third-party imports, no network. The suite
imports ``harness/dod_closeout_verify.py`` — the exact module the
``dod-closeout`` workflow executes on every push to ``main`` — and pins the
tri-state fact semantics with negative fixtures:

  * issue linkage derives ONLY from GitHub-native closing linkage; zero or
    more than one candidate is unknown (AC7);
  * a missing or not-yet-published signal is never green (AC4): CI check
    runs absent/incomplete render unknown; a DV status that is absent or
    pending renders ``pending`` and is never a failure (AC5);
  * the CI verdict is computed ONLY over the ``CI Pipeline`` workflow's
    check runs — the DV workflow's own check runs on the same sha are
    ignored, even when still in progress (AC4);
  * the APPROVE fact requires login AND id parity with the identity probe
    (``harness/probes/verify-github-identities.py``, #423) and a reviewer
    distinct from the PR author (AC6);
  * the comment body carries machine-derived values only (AC8) and states
    the report-only contract (AC10).

Run:
    python3 harness/config-validation/test_dod_closeout_verifier.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "harness" / "dod_closeout_verify.py"

_spec = importlib.util.spec_from_file_location("dod_closeout_verify", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
MODULE = importlib.util.module_from_spec(_spec)
# Register before exec_module: the verifier uses @dataclass, whose PEP 562
# resolution requires the module to be present in sys.modules.
sys.modules.setdefault("dod_closeout_verify", MODULE)
_spec.loader.exec_module(MODULE)

SHA = "0123456789abcdef0123456789abcdef01234567"


def graphql_payload(total: int, numbers: list[int]) -> dict:
    """A closingIssuesReferences GraphQL response fixture (AC7)."""
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "closingIssuesReferences": {
                        "totalCount": total,
                        "nodes": [{"number": n} for n in numbers],
                    }
                }
            }
        }
    }


def merged_pr(sha: str, base: str = "main") -> dict:
    """A merged-PR fixture whose merge commit is sha (AC1 fact 1)."""
    return {
        "number": 7,
        "merged": True,
        "merge_commit_sha": sha,
        "base": {"ref": base},
        "user": {"id": 3135901},
    }


def check_run(
    name: str, conclusion: str | None, status: str = "completed", suite: int = 1
) -> dict:
    """A check-run fixture (AC4: the verdict is name-scoped)."""
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "check_suite": {"id": suite},
    }


def status_entry(state: str, context: str, entry_id: int) -> dict:
    """A legacy commit-status fixture (AC5: the DV verdict surface)."""
    return {"id": entry_id, "state": state, "context": context}


class DeriveIssueNumberTest(unittest.TestCase):
    """AC7: native closing linkage only; 0 or >1 candidates are unknown."""

    def test_single_closing_issue_is_derived(self) -> None:
        self.assertEqual(
            MODULE.derive_issue_number(graphql_payload(1, [481])), 481
        )

    def test_zero_closing_issues_is_unknown(self) -> None:
        self.assertIsNone(MODULE.derive_issue_number(graphql_payload(0, [])))

    def test_multiple_closing_issues_is_unknown(self) -> None:
        self.assertIsNone(MODULE.derive_issue_number(graphql_payload(2, [481, 482])))

    def test_missing_graphql_payload_is_unknown(self) -> None:
        self.assertIsNone(MODULE.derive_issue_number(None))

    def test_count_disagreeing_with_nodes_is_unknown(self) -> None:
        self.assertIsNone(MODULE.derive_issue_number(graphql_payload(1, [])))


class FilterMergedPrsTest(unittest.TestCase):
    """The PR selector keeps only merged PRs whose merge commit is the sha."""

    def test_keeps_the_merged_pr_matching_the_sha(self) -> None:
        candidates = [merged_pr(SHA), merged_pr("f" * 40)]
        self.assertEqual(len(MODULE.filter_merged_prs(candidates, SHA)), 1)

    def test_drops_unmerged_prs(self) -> None:
        pr = merged_pr(SHA)
        pr["merged"] = False
        self.assertEqual(MODULE.filter_merged_prs([pr], SHA), [])

    def test_no_candidate_is_empty(self) -> None:
        self.assertEqual(MODULE.filter_merged_prs([], SHA), [])


class SquashFactTest(unittest.TestCase):
    """AC1 fact 1 + AC3/AC4: squash merge into main on the pushed sha."""

    def test_squash_merge_into_main_is_green(self) -> None:
        fact, rendered = MODULE.evaluate_squash_fact(merged_pr(SHA), SHA, 1, 1)
        self.assertEqual((fact, rendered), ("green", "green"))

    def test_unmerged_pr_is_red(self) -> None:
        pr = merged_pr(SHA)
        pr["merged"] = False
        self.assertEqual(MODULE.evaluate_squash_fact(pr, SHA, 1, 1)[0], "red")

    def test_wrong_base_branch_is_red(self) -> None:
        self.assertEqual(
            MODULE.evaluate_squash_fact(merged_pr(SHA, base="dev"), SHA, 1, 1)[0],
            "red",
        )

    def test_merge_commit_sha_mismatch_is_red(self) -> None:
        self.assertEqual(
            MODULE.evaluate_squash_fact(merged_pr("f" * 40), SHA, 1, 1)[0], "red"
        )

    def test_two_parent_commit_is_red(self) -> None:
        # A "create a merge commit" merge lands a 2-parent commit — not a
        # squash merge (AC1 fact 1).
        self.assertEqual(
            MODULE.evaluate_squash_fact(merged_pr(SHA), SHA, 1, 2)[0], "red"
        )

    def test_multi_commit_push_is_red(self) -> None:
        # A multi-commit push matching a merged PR is the rebase-merge or
        # direct-push shape, never the squash protocol.
        self.assertEqual(
            MODULE.evaluate_squash_fact(merged_pr(SHA), SHA, 3, 1)[0], "red"
        )

    def test_no_associated_pr_is_unknown(self) -> None:
        self.assertEqual(
            MODULE.evaluate_squash_fact(None, SHA, 1, 1)[0], "unknown"
        )

    def test_missing_parent_count_is_unknown(self) -> None:
        # A missing input is never green (AC4).
        self.assertEqual(
            MODULE.evaluate_squash_fact(merged_pr(SHA), SHA, 1, None)[0], "unknown"
        )

    def test_missing_pushed_count_is_unknown(self) -> None:
        self.assertEqual(
            MODULE.evaluate_squash_fact(merged_pr(SHA), SHA, None, 1)[0], "unknown"
        )


class CiFactTest(unittest.TestCase):
    """AC4: verdict computed ONLY over the CI Pipeline workflow's check runs."""

    def test_all_success_is_green(self) -> None:
        runs = [check_run(MODULE.CI_CHECK_RUN_NAME, "success")]
        self.assertEqual(MODULE.evaluate_ci_fact(runs), ("green", "green"))

    def test_failure_is_red(self) -> None:
        runs = [check_run(MODULE.CI_CHECK_RUN_NAME, "failure")]
        self.assertEqual(MODULE.evaluate_ci_fact(runs), ("red", "red"))

    def test_cancelled_is_red(self) -> None:
        runs = [check_run(MODULE.CI_CHECK_RUN_NAME, "cancelled")]
        self.assertEqual(MODULE.evaluate_ci_fact(runs)[0], "red")

    def test_timed_out_is_red(self) -> None:
        runs = [check_run(MODULE.CI_CHECK_RUN_NAME, "timed_out")]
        self.assertEqual(MODULE.evaluate_ci_fact(runs)[0], "red")

    def test_dv_check_runs_are_ignored_when_ci_run_is_green(self) -> None:
        # The exact AC4 trap: the DV workflow's own jobs are on the same sha
        # and still pending at push time — they must not pollute the verdict.
        runs = [
            check_run(MODULE.CI_CHECK_RUN_NAME, "success"),
            check_run("Secret Scan (gitleaks, full history)", None, status="in_progress"),
            check_run("Config Checker Regression Suites (Tier B)", None, status="queued"),
        ]
        self.assertEqual(MODULE.evaluate_ci_fact(runs), ("green", "green"))

    def test_dv_check_runs_do_not_create_a_verdict(self) -> None:
        # Only-DV check runs on the sha: no CI Pipeline run visible yet ->
        # unknown (missing signal is never green, AC4).
        runs = [check_run("Docs Render Validation (mermaid render, links, MADR)", "success")]
        self.assertEqual(MODULE.evaluate_ci_fact(runs), ("unknown", "unknown"))

    def test_no_matching_check_run_is_unknown(self) -> None:
        self.assertEqual(MODULE.evaluate_ci_fact([]), ("unknown", "unknown"))

    def test_missing_payload_is_unknown(self) -> None:
        self.assertEqual(MODULE.evaluate_ci_fact(None), ("unknown", "unknown"))

    def test_in_progress_run_is_unknown(self) -> None:
        runs = [check_run(MODULE.CI_CHECK_RUN_NAME, None, status="in_progress")]
        self.assertEqual(MODULE.evaluate_ci_fact(runs), ("unknown", "unknown"))

    def test_queued_run_is_unknown(self) -> None:
        runs = [check_run(MODULE.CI_CHECK_RUN_NAME, None, status="queued")]
        self.assertEqual(MODULE.evaluate_ci_fact(runs), ("unknown", "unknown"))

    def test_mixed_success_and_in_progress_is_unknown(self) -> None:
        runs = [
            check_run(MODULE.CI_CHECK_RUN_NAME, "success", suite=1),
            check_run(MODULE.CI_CHECK_RUN_NAME, None, status="in_progress", suite=2),
        ]
        self.assertEqual(MODULE.evaluate_ci_fact(runs)[0], "unknown")


class DvFactTest(unittest.TestCase):
    """AC5: the DV verdict is a legacy commit status; absent renders pending."""

    def test_success_status_is_green(self) -> None:
        payload = {"statuses": [status_entry("success", MODULE.DV_CONTEXT, 2)]}
        self.assertEqual(MODULE.evaluate_dv_fact(payload), ("green", "green"))

    def test_failure_status_is_red(self) -> None:
        payload = {"statuses": [status_entry("failure", MODULE.DV_CONTEXT, 2)]}
        self.assertEqual(MODULE.evaluate_dv_fact(payload), ("red", "red"))

    def test_error_status_is_red(self) -> None:
        payload = {"statuses": [status_entry("error", MODULE.DV_CONTEXT, 2)]}
        self.assertEqual(MODULE.evaluate_dv_fact(payload)[0], "red")

    def test_absent_status_renders_pending_never_failure(self) -> None:
        # AC5: a status that does not exist yet is never a failure comment.
        payload = {"statuses": []}
        self.assertEqual(MODULE.evaluate_dv_fact(payload), ("unknown", "pending"))

    def test_pending_status_renders_pending(self) -> None:
        payload = {"statuses": [status_entry("pending", MODULE.DV_CONTEXT, 2)]}
        self.assertEqual(MODULE.evaluate_dv_fact(payload), ("unknown", "pending"))

    def test_missing_payload_is_unknown_not_pending(self) -> None:
        # An unreadable status (API failure) is unknown; only a clean read
        # with no DV status renders the bounded-window `pending` (AC5).
        self.assertEqual(MODULE.evaluate_dv_fact(None), ("unknown", "unknown"))

    def test_other_contexts_are_ignored(self) -> None:
        payload = {"statuses": [status_entry("success", "ci/other", 2)]}
        self.assertEqual(MODULE.evaluate_dv_fact(payload), ("unknown", "pending"))

    def test_latest_status_wins_newer_success(self) -> None:
        payload = {
            "statuses": [
                status_entry("failure", MODULE.DV_CONTEXT, 1),
                status_entry("success", MODULE.DV_CONTEXT, 2),
            ]
        }
        self.assertEqual(MODULE.evaluate_dv_fact(payload)[0], "green")

    def test_latest_status_wins_newer_failure(self) -> None:
        payload = {
            "statuses": [
                status_entry("success", MODULE.DV_CONTEXT, 1),
                status_entry("failure", MODULE.DV_CONTEXT, 2),
            ]
        }
        self.assertEqual(MODULE.evaluate_dv_fact(payload)[0], "red")


class ReviewFactTest(unittest.TestCase):
    """AC6: login AND id parity (#423) and author != PR author."""

    def approval(self, login: str, user_id: int) -> dict:
        return {"state": "APPROVED", "user": {"login": login, "id": user_id}}

    def test_genuine_reviewer_approval_is_green(self) -> None:
        reviews = [self.approval(MODULE.REVIEWER_LOGIN, MODULE.REVIEWER_ID)]
        self.assertEqual(
            MODULE.evaluate_review_fact(reviews, 3135901), ("green", "green")
        )

    def test_login_only_match_is_unmet(self) -> None:
        # The #423 defect class: a login-only check passes a drifted id.
        reviews = [self.approval(MODULE.REVIEWER_LOGIN, 999999999)]
        self.assertEqual(MODULE.evaluate_review_fact(reviews, 3135901), ("red", "unmet"))

    def test_id_only_match_is_unmet(self) -> None:
        reviews = [self.approval("fpittelo", MODULE.REVIEWER_ID)]
        self.assertEqual(MODULE.evaluate_review_fact(reviews, 3135901), ("red", "unmet"))

    def test_self_approval_is_unmet(self) -> None:
        # The reviewer identity IS the PR author identity.
        reviews = [self.approval(MODULE.REVIEWER_LOGIN, MODULE.REVIEWER_ID)]
        self.assertEqual(
            MODULE.evaluate_review_fact(reviews, MODULE.REVIEWER_ID), ("red", "unmet")
        )

    def test_owner_self_approval_is_unmet(self) -> None:
        reviews = [self.approval("fpittelo", 3135901)]
        self.assertEqual(MODULE.evaluate_review_fact(reviews, 3135901), ("red", "unmet"))

    def test_no_reviews_is_unmet(self) -> None:
        self.assertEqual(MODULE.evaluate_review_fact([], 3135901), ("red", "unmet"))

    def test_request_changes_only_is_unmet(self) -> None:
        reviews = [{"state": "CHANGES_REQUESTED", "user": {"login": "devfpittelo", "id": 327061373}}]
        self.assertEqual(MODULE.evaluate_review_fact(reviews, 3135901), ("red", "unmet"))

    def test_missing_reviews_payload_is_unknown(self) -> None:
        self.assertEqual(MODULE.evaluate_review_fact(None, 3135901), ("unknown", "unknown"))

    def test_missing_pr_author_is_unknown_never_green(self) -> None:
        reviews = [self.approval(MODULE.REVIEWER_LOGIN, MODULE.REVIEWER_ID)]
        self.assertEqual(MODULE.evaluate_review_fact(reviews, None), ("unknown", "unknown"))


class TraceabilityFactTest(unittest.TestCase):
    """AC1 fact 5 / AC7: a uniquely linked issue and its PR."""

    def test_unique_linkage_is_green(self) -> None:
        self.assertEqual(
            MODULE.evaluate_traceability_fact(481, merged_pr(SHA)), ("green", "green")
        )

    def test_unknown_linkage_is_unknown(self) -> None:
        self.assertEqual(
            MODULE.evaluate_traceability_fact(None, merged_pr(SHA))[0], "unknown"
        )

    def test_missing_pr_is_unknown(self) -> None:
        self.assertEqual(MODULE.evaluate_traceability_fact(481, None)[0], "unknown")


class OverallSignalTest(unittest.TestCase):
    """The closeout signal fires only when all five facts are green (AC1)."""

    def green_facts(self) -> dict[str, tuple[str, str]]:
        return {name: ("green", "green") for name in MODULE.FACT_ORDER}

    def test_all_green_is_the_signal(self) -> None:
        self.assertTrue(MODULE.overall_signal(self.green_facts()))

    def test_any_non_green_is_not_the_signal(self) -> None:
        for name in MODULE.FACT_ORDER:
            facts = self.green_facts()
            facts[name] = ("unknown", "pending" if name == "dv" else "unknown")
            with self.subTest(fact=name):
                self.assertFalse(MODULE.overall_signal(facts))

    def test_any_red_is_not_the_signal(self) -> None:
        for name in MODULE.FACT_ORDER:
            facts = self.green_facts()
            facts[name] = ("red", "unmet" if name == "review" else "red")
            with self.subTest(fact=name):
                self.assertFalse(MODULE.overall_signal(facts))


class RenderCommentTest(unittest.TestCase):
    """AC8 (machine-derived values only) + AC9 marker + AC10 statement."""

    def green_facts(self) -> dict[str, tuple[str, str]]:
        return {name: ("green", "green") for name in MODULE.FACT_ORDER}

    def render(self, facts: dict[str, tuple[str, str]]) -> str:
        return MODULE.render_comment(SHA, 7, 481, facts)

    def test_body_is_one_line_starting_with_the_marker(self) -> None:
        body = self.render(self.green_facts())
        self.assertNotIn("\n", body)
        self.assertTrue(body.startswith(MODULE.COMMENT_MARKER))

    def test_body_carries_the_machine_derived_values(self) -> None:
        body = self.render(self.green_facts())
        self.assertIn(f"`{SHA}`", body)
        self.assertIn("PR #7", body)
        self.assertIn("issue #481", body)

    def test_body_lists_all_five_fact_verdicts(self) -> None:
        body = self.render(self.green_facts())
        for name in MODULE.FACT_ORDER:
            with self.subTest(fact=name):
                self.assertIn(f"{name}: green", body)

    def test_body_states_the_report_only_contract(self) -> None:
        body = self.render(self.green_facts())
        self.assertIn("does not close the DoD gate", body)
        self.assertIn("@scrum-master", body)

    def test_pending_dv_is_rendered_as_pending(self) -> None:
        facts = self.green_facts()
        facts["dv"] = ("unknown", "pending")
        body = self.render(facts)
        self.assertIn("dv: pending", body)
        self.assertNotIn("dv: green", body)

    def test_unmet_review_is_rendered_as_unmet(self) -> None:
        facts = self.green_facts()
        facts["review"] = ("red", "unmet")
        self.assertIn("review: unmet", self.render(facts))

    def test_green_and_non_green_bodies_differ_visibly(self) -> None:
        facts = self.green_facts()
        facts["ci"] = ("red", "red")
        self.assertNotEqual(self.render(self.green_facts()), self.render(facts))


if __name__ == "__main__":
    unittest.main()
