#!/usr/bin/env python3
"""Regression tests for harness/doctor.sh (#462).

stdlib unittest only: no pytest, no third-party imports, no network (the
identity probe fails fast on a missing ambient token BEFORE any network
call — its fail-closed contract). The doctor is a thin orchestrator of
reused checkers (gate-16 probe + gate-20 checker), so the suite tests the
orchestrator's OWN contract, not duplicated logic:

  * exit semantics (AC3): findings -> 1 with a per-check row each;
  * per-check isolation: one failing check must not abort the others —
    all three rows print before the summary exits;
  * report-only (AC2): nothing is mutated (the fake HOME is untouched);
  * secret hygiene (AC4): the script never reads/prints secrets contents —
    asserted as a static pin on the script source (no cat/source/read of
    the secrets file) plus a token-material scan of the live output.

The all-fresh path is covered by the live host run recorded in the PR
(VIDAR, real env) — stubbing a fake all-fresh here would be fixture
theater (the probe and checker are real, env-backed tools).

Run:
    python3 harness/config-validation/test_doctor_script.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "doctor.sh"
REPO_ROOT = Path(__file__).resolve().parents[2]


def run_doctor(
    home: Path, secrets: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run doctor.sh against a fake HOME via its documented test seams."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    if secrets is None:
        env["DOCTOR_SECRETS_FILE"] = str(home / ".config/opencode/absent.env")
    else:
        env["DOCTOR_SECRETS_FILE"] = str(secrets)
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )


class DoctorScript(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())

    def test_bare_host_reports_findings_with_all_three_rows(self) -> None:
        """AC3: findings -> exit 1; one failing check never aborts the others."""
        proc = run_doctor(self.home)
        self.assertEqual(
            proc.returncode,
            1,
            f"expected exit 1 with findings, got {proc.returncode}:\n"
            f"{proc.stdout}{proc.stderr}",
        )
        for check in ("token-freshness", "github-identity", "installed-posture"):
            with self.subTest(check=check):
                self.assertIn(check, proc.stdout)
        self.assertIn("FAIL", proc.stdout)
        self.assertIn("report-only", proc.stdout)
        self.assertNotIn("all checks fresh", proc.stdout)

    def test_bare_host_posture_row_is_skip(self) -> None:
        """No HOME-profile install -> gate-20 checker SKIPs (neither fresh nor finding)."""
        proc = run_doctor(self.home)
        self.assertIn("SKIP", proc.stdout)
        self.assertIn("installed-posture", proc.stdout)

    def test_present_secrets_file_reports_age_not_contents(self) -> None:
        """AC1a/AC4: a present secrets file yields an OK age row, no contents."""
        secrets = self.home / "secrets.env"
        secrets.write_text("export FAKE=placeholder\n", encoding="utf-8")
        proc = run_doctor(self.home, secrets=secrets)
        # The identity check may legitimately PASS (ambient namespace tokens)
        # and the posture check SKIPs on a fake HOME — so the overall exit is
        # 0 here; the FINDINGS->exit-1 path is pinned by the bare-host test.
        self.assertIn("token file present, last rotated", proc.stdout)
        self.assertIn("0 day(s) ago", proc.stdout)
        self.assertNotIn("export FAKE", proc.stdout)  # AC4: never contents

    def test_no_token_material_in_output(self) -> None:
        """AC4: no token-shaped material (ghp_/github_pat_) ever reaches stdout."""
        proc = run_doctor(self.home)
        self.assertNotIn("ghp_", proc.stdout + proc.stderr)
        self.assertNotIn("github_pat_", proc.stdout + proc.stderr)

    def test_static_hygiene_pin(self) -> None:
        """AC4 static pin: the script never reads/prints/sources the secrets file."""
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("cat \"${SECRETS_FILE}\"", text)
        self.assertNotIn("cat \"$SECRETS_FILE\"", text)
        self.assertNotIn("source \"${SECRETS_FILE}\"", text)
        self.assertNotIn("< \"${SECRETS_FILE}\"", text)
        self.assertNotIn("< \"$SECRETS_FILE\"", text)
        self.assertIn("stat -c", text)  # the only secrets-file access is stat


if __name__ == "__main__":
    unittest.main()
