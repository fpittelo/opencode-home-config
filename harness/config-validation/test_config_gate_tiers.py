#!/usr/bin/env python3
"""Regression suite for the config-gate TIER SPLIT (#479).

The config repository validates itself in two tiers:

- **Tier A — per-push** (``harness/run-config-gate.sh``, invoked by ``ci.yml``):
  real-repo invariants only, re-expressed as DIRECT checker invocations where
  the invariant used to be reachable only through a ``test_*.py`` suite
  (#371 removed the standalone checker runs; the suites kept the real-repo
  positive control as a side effect).
- **Tier B — scheduled** (``.github/workflows/deep-validation.yml``): the
  checker regression suites — negative fixtures + sandboxed behavioral suites
  — on the deep cadence, fully blocking under the MADR-0028 fail-closed rule.

This suite pins the split so it cannot silently regress:

1. Tier A invokes every mandated direct checker against the real repo.
2. Tier A invokes NO Tier B regression suite (only the real-repo-only
   pin-consistency suite is kept, per #479 Tier A item 2).
3. The DV workflow runs every Tier B suite in a dedicated failing job, and
   its schedule is unchanged.
4. ``harness/README.md`` carries the Tier A / Tier B mapping table accounting
   for every current gate (1-23) — no gate silently dropped.

stdlib unittest only, no network, < 1 s.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO_ROOT / "harness" / "run-config-gate.sh"
DV_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deep-validation.yml"
README = REPO_ROOT / "harness" / "README.md"

# #479 Tier A item 2: direct real-repo checker invocations.
TIER_A_DIRECT_CHECKERS = (
    "check_agent_frontmatter.py",
    "check_coach_exclusivity.py",
    "check_browser_launch_flags.py",
    "check_bash_permission_tiers.py",
    "check_gitleaks_allowlist.py",
    "check_external_prerequisites.py",
    "check_installed_posture_freshness.py",
    "check_pin_freshness_workflow.py",
)

# Kept in Tier A: suites invoked DIRECTLY as gate steps because they carry
# real-repo invariants. test_pin_consistency.py asserts real-repo pin
# invariants only (#479); the two #481 suites each carry the real-repo
# positive control for the DoD closeout signal (#481 AC11/R5-C12/R5-C13
# mandates per-push execution — a suite executed by no gate is advisory
# only) and stay inside the < 5 s per-push budget.
TIER_A_KEPT_SUITES = (
    "test_pin_consistency.py",
    "test_check_dod_closeout_workflow.py",
    "test_dod_closeout_verifier.py",
)

# #479 Tier B: the regression suites moved to the scheduled DV cadence.
TIER_B_SUITES = (
    "test_check_mermaid_syntax.py",
    "test_check_coach_exclusivity.py",
    "test_check_browser_launch_flags.py",
    "test_check_bash_permission_tiers.py",
    "test_check_agent_frontmatter.py",
    "test_github_identity_probe.py",
    "test_check_external_prerequisites.py",
    "test_check_gitleaks_allowlist.py",
    "test_check_pin_freshness_workflow.py",
    "test_check_installed_posture_freshness.py",
    "test_check_arch_coverage.py",
    "test_doctor_script.py",
    "test_harness_run.py",
    "test_per_pane_profile_selection.py",
)

# Gates whose only per-push home disappears (suite-only today, no direct
# real-repo invariant to re-express) — and the ones that keep a Tier A home.
# Gate 21 keeps its per-push home (the ci.yml check_arch_coverage.sh
# invocation, unchanged) and only its suite moves to Tier B.
GATES_TIER_A_ONLY = {1, 2, 3, 4, 5, 6, 7, 9, 10, 13, 14, 15, 17, 18, 19, 20, 21, 23}
GATES_TIER_B_ONLY = {8, 11, 12, 16, 22}
GATES_TIER_B_EMPTY = {1, 2, 3, 4, 5, 6, 7, 13, 23}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TierAGateScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = read(GATE_SCRIPT)

    def test_invokes_every_mandated_direct_checker_on_the_real_repo(self) -> None:
        for checker in TIER_A_DIRECT_CHECKERS:
            with self.subTest(checker=checker):
                self.assertIn(
                    f"python3 harness/config-validation/{checker} .",
                    self.script,
                    f"Tier A must invoke {checker} directly against the repo root",
                )

    def test_keeps_the_real_repo_kept_suites(self) -> None:
        for suite in TIER_A_KEPT_SUITES:
            with self.subTest(suite=suite):
                self.assertIn(
                    f"python3 harness/config-validation/{suite}", self.script
                )

    def test_runs_no_tier_b_regression_suite(self) -> None:
        # Comments may (and do) point at the Tier B suite that guards each
        # direct checker; what must not exist is an INVOCATION of it.
        executed = "\n".join(
            line for line in self.script.splitlines() if not line.lstrip().startswith("#")
        )
        for suite in TIER_B_SUITES:
            with self.subTest(suite=suite):
                self.assertNotIn(
                    suite,
                    executed,
                    f"{suite} belongs to Tier B (scheduled DV), not the per-push gate",
                )

    def test_keeps_gates_one_to_seven(self) -> None:
        for needle in (
            "opencode.jsonc is not valid JSONC",
            "bash -n install.sh",
            "agents/${agent}.md",
            "skills/${skill}/SKILL.md",
            "check_links.py .",
            "check_madr.py .",
            "check_mermaid.py --syntax .",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.script)


class TierBWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = read(DV_WORKFLOW)

    def test_runs_every_tier_b_suite(self) -> None:
        for suite in TIER_B_SUITES:
            with self.subTest(suite=suite):
                self.assertIn(suite, self.workflow)

    def test_has_a_dedicated_fail_closed_job(self) -> None:
        self.assertIn("config-regression-suites:", self.workflow)
        self.assertIn("set -euo pipefail", self.workflow)

    def test_durable_status_reflects_the_tier_b_job(self) -> None:
        self.assertIn("config-regression-suites", self.workflow.split("needs:", 1)[1])
        self.assertIn("needs.config-regression-suites.result", self.workflow)

    def test_schedule_is_unchanged(self) -> None:
        self.assertIn('- cron: "0 5 * * 1"', self.workflow)


class MappingTableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = {}
        for line in read(README).splitlines():
            match = re.match(r"^\|\s*(\d+)\s*\|", line)
            if match:
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                self.rows[int(match.group(1))] = cells

    def test_accounts_for_every_current_gate(self) -> None:
        self.assertEqual(sorted(self.rows), list(range(1, 24)))

    def test_every_gate_has_a_home_and_the_right_one(self) -> None:
        tier_a_only: set[int] = set()
        tier_b_only: set[int] = set()
        tier_b_empty: set[int] = set()
        for gate, cells in self.rows.items():
            self.assertEqual(len(cells), 4, f"gate {gate} must have 4 columns")
            tier_a, tier_b = cells[2], cells[3]
            self.assertTrue(
                tier_a != "—" or tier_b != "—", f"gate {gate} maps to no tier"
            )
            if tier_a == "—":
                tier_b_only.add(gate)
            else:
                tier_a_only.add(gate)
            if tier_b == "—":
                tier_b_empty.add(gate)
        self.assertEqual(tier_a_only, GATES_TIER_A_ONLY)
        self.assertEqual(tier_b_only, GATES_TIER_B_ONLY)
        self.assertEqual(tier_b_empty, GATES_TIER_B_EMPTY)

    def test_names_every_moved_suite_and_direct_checker(self) -> None:
        text = read(README)
        for suite in TIER_B_SUITES:
            with self.subTest(suite=suite):
                self.assertIn(suite, text)
        for checker in TIER_A_DIRECT_CHECKERS:
            with self.subTest(checker=checker):
                self.assertIn(checker, text)


if __name__ == "__main__":
    unittest.main()
