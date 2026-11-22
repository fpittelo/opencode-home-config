#!/usr/bin/env python3
"""Regression tests for check_installed_posture_freshness.py (#449, gate 20).

stdlib unittest only: no pytest, no third-party imports, no network. Fixture
cases build throwaway fake-HOME trees (``<home>/.config/opencode/``) and
mutate the real ``opencode.jsonc`` text, so the installed-posture invariant is
exercised in isolation; the last class runs the CLI against THIS host as the
positive control (on an installed host it must PASS fresh; on a bare CI
runner with no HOME-profile install it must take the explicit SKIP path and
still exit 0).

Why this gate exists (#449 AC2a, the #448/#449 lesson): the root bash deny
tail (``gh run delete*``, ``gh cache delete*``, ``gh auth *``, ``gh api *``,
...) landed on trunk in ``e440e21``, but the deny tail only protects sessions
whose INSTALLED config carries it — ``opencode serve --service`` and every
agent session boot from ``$HOME/.config/opencode/opencode.jsonc``, which
``install.sh`` wires as a symlink that can point at a stale clone, or be
replaced by a copy. A session booted from a stale posture silently loses the
structural denies. This check asserts, fail-closed, that the installed file
carries every deny entry the validated tree has.

Run:
    python3 harness/config-validation/test_check_installed_posture_freshness.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_installed_posture_freshness as checker  # noqa: E402
import check_bash_permission_tiers as tiers  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "check_installed_posture_freshness.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SOURCE = (REPO_ROOT / "opencode.jsonc").read_text(encoding="utf-8")

# A single deny-tail entry every host must carry — the #449 incident driver.
CANARY = "gh run delete*"


def build_home(
    *,
    installed: str | None = REAL_SOURCE,
    as_symlink: bool = False,
    broken_symlink: bool = False,
    profiles_sh: bool = False,
) -> Path:
    """Throwaway fake HOME with the installed-config layout install.sh wires."""
    home = Path(tempfile.mkdtemp())
    dest = home / ".config" / "opencode"
    dest.mkdir(parents=True)
    if broken_symlink:
        (dest / "opencode.jsonc").symlink_to(dest / "missing-target.jsonc")
    elif as_symlink:
        (dest / "opencode.jsonc").symlink_to(REPO_ROOT / "opencode.jsonc")
    elif installed is not None:
        (dest / "opencode.jsonc").write_text(installed, encoding="utf-8")
    if profiles_sh:
        (dest / "profiles.sh").write_text("# oc-home()\n", encoding="utf-8")
    return home


def run_cli(root: Path, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root), str(home)],
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


class FreshInstalledPosture(FixtureTestCase):
    """The positive case: installed carries every trunk deny entry."""

    def test_exact_copy_passes(self) -> None:
        self.assert_clean(checker.check_repo(REPO_ROOT, build_home()))

    def test_symlink_to_repo_passes(self) -> None:
        self.assert_clean(
            checker.check_repo(REPO_ROOT, build_home(as_symlink=True))
        )

    def test_extra_deny_is_allowed_strictness(self) -> None:
        """Extras are a stricter posture, never a freshness failure."""
        stricter = REAL_SOURCE.replace(
            f'      "{CANARY}": "deny",',
            f'      "{CANARY}": "deny",\n      "gh run list*": "deny",',
        )
        self.assertNotEqual(stricter, REAL_SOURCE)
        self.assert_clean(
            checker.check_repo(REPO_ROOT, build_home(installed=stricter))
        )


class StaleInstalledPosture(FixtureTestCase):
    """The #449 class: the installed posture lost a trunk deny entry."""

    def test_missing_canary_entry_fails(self) -> None:
        stale = REAL_SOURCE.replace(f'      "{CANARY}": "deny",\n', "")
        self.assertNotEqual(stale, REAL_SOURCE)
        self.assert_finding(
            checker.check_repo(REPO_ROOT, build_home(installed=stale)),
            CANARY,
            "installed",
        )

    def test_each_trunk_deny_entry_is_required(self) -> None:
        """Fail-closed over the whole tail: every entry must be present."""
        for entry in (
            "gh run delete*",
            "gh cache delete*",
            "gh auth *",
            "gh api *",
            "xargs *",
            "timeout *",
        ):
            with self.subTest(entry=entry):
                # The tail's last entry carries no trailing comma.
                stale = REAL_SOURCE.replace(
                    f'      "{entry}": "deny",\n', ""
                )
                if stale == REAL_SOURCE:
                    stale = REAL_SOURCE.replace(
                        f',\n      "{entry}": "deny"\n', "\n"
                    )
                self.assertNotEqual(stale, REAL_SOURCE)
                self.assert_finding(
                    checker.check_repo(
                        REPO_ROOT, build_home(installed=stale)
                    ),
                    entry,
                )

    def test_deny_flipped_to_allow_fails(self) -> None:
        """A flipped tier is valid JSONC and still lacks the deny."""
        stale = REAL_SOURCE.replace(
            f'      "{CANARY}": "deny",', '      "keep": "allow",'
        )
        self.assertNotEqual(stale, REAL_SOURCE)
        self.assert_finding(
            checker.check_repo(REPO_ROOT, build_home(installed=stale)),
            CANARY,
        )

    def test_tiers_baseline_is_the_requirement_source(self) -> None:
        """Single source of truth: the checker requires the pinned tail."""
        self.assertIn(CANARY, tiers.BASELINE_DENY_TAIL)
        self.assertIn("gh api *", tiers.BASELINE_DENY_TAIL)
        # MADR-0027 (#463) parity canary: the tail grew by EXACTLY the three
        # kill-broadcast entries (70 -> 73), no removals, no reordering —
        # verdict §4.8. MADR-0029 (#475) parity canary: the tail then grew by
        # EXACTLY the 13 curated wrapper-family denies (73 -> 86), additions
        # only, no removals, no reordering. MADR-0032 (#485) parity canary:
        # the three over-broad kill-broadcast patterns are REPLACED by 10
        # target-classified deny forms (86 -> 93) — the only reordering-free
        # removal in the tail's history, narrowing the signal-prefix false
        # positives while every destructive target form stays denied. A
        # future tail edit must update this pin deliberately.
        self.assertEqual(len(tiers.BASELINE_DENY_TAIL), 93)
        for entry in tiers.KILL_DENY_PATTERNS:
            self.assertIn(entry, tiers.BASELINE_DENY_TAIL)
        for entry in ("xargs *", "env *", "timeout *", "find * -exec*"):
            self.assertIn(entry, tiers.BASELINE_DENY_TAIL)
        for entry in ("rm -rf /*", "*.env*", "*.key*", "gh api *"):
            self.assertIn(entry, tiers.BASELINE_DENY_TAIL)  # no removals
        for removed in ("kill 0*", "kill -1*", "kill * -1*"):
            self.assertNotIn(removed, tiers.BASELINE_DENY_TAIL)  # R-2 fix


class OrderedWrapperResolution(FixtureTestCase):
    """MADR-0029 C3 (#475): gate 20 resolves, it does not just count.

    Deny-set membership alone is insufficient: the installed rules are an
    ORDERED last-match-wins list, so a posture can carry every wrapper deny
    entry yet still resolve them to ``allow`` when the ``"*": allow`` head
    sits after them (stale copy, hand edit, drifted merge). Gate 20 must
    therefore resolve representative wrapper commands against the ordered
    installed rules and require ``deny``.
    """

    def test_wrapper_denies_before_the_allow_head_fail(self) -> None:
        moved = REAL_SOURCE.replace('      "*": "allow",\n', "", 1)
        moved = moved.replace(
            '      "xargs *": "deny"\n',
            '      "xargs *": "deny",\n      "*": "allow"\n',
            1,
        )
        self.assertNotEqual(moved, REAL_SOURCE)
        findings = checker.check_repo(REPO_ROOT, build_home(installed=moved))
        self.assert_finding(findings, "xargs pip install pkg", "deny")

    def test_compound_wrapper_probe_is_required(self) -> None:
        probes = checker.WRAPPER_ORDERED_PROBES
        self.assertIn("xargs pip install pkg", probes)
        self.assertIn("timeout 5 curl", probes)
        self.assertIn("env gh api", probes)
        self.assertIn("true && xargs curl", probes)


class OrderedKillResolution(FixtureTestCase):
    """MADR-0032 C3 (#485): gate 20 also resolves the kill posture in order.

    The R-1 path-qualified bypass is invisible to deny-set membership: an
    installed posture can carry ``*/kill *`` and still resolve it to allow
    when the ``"*": allow`` head sits after it. Gate 20 therefore resolves the
    shared ``KILL_ORDERED_PROBES`` (including ``/usr/bin/kill 754``) against
    the ordered installed rules and requires ``deny``.
    """

    def test_kill_ordered_probes_are_shared_and_denied(self) -> None:
        probes = checker.KILL_ORDERED_PROBES
        self.assertIn("/usr/bin/kill 754", probes)
        self.assertIn("/bin/kill -9 1234", probes)
        installed = checker.bash_rules(REAL_SOURCE)
        for command in probes:
            with self.subTest(command=command):
                self.assertEqual(
                    checker.resolve_command(installed, command), "deny"
                )

    def test_missing_path_general_deny_fails(self) -> None:
        stale = REAL_SOURCE.replace('      "*/kill *": "deny",\n', "")
        self.assertNotEqual(stale, REAL_SOURCE)
        self.assert_finding(
            checker.check_repo(REPO_ROOT, build_home(installed=stale)),
            "/usr/bin/kill 754",
        )

    def test_kill_deny_after_the_allow_head_fails(self) -> None:
        moved = REAL_SOURCE.replace('      "*": "allow",\n', "", 1)
        moved = moved.replace(
            '      "*/kill *": "deny",\n',
            '      "*/kill *": "deny",\n      "*": "allow",\n',
            1,
        )
        self.assertNotEqual(moved, REAL_SOURCE)
        findings = checker.check_repo(REPO_ROOT, build_home(installed=moved))
        self.assert_finding(findings, "/usr/bin/kill 754", "deny")


class UnreadableInstalledPosture(FixtureTestCase):
    """Fail-closed when the installed posture cannot be verified at all."""

    def test_broken_symlink_fails(self) -> None:
        self.assert_finding(
            checker.check_repo(REPO_ROOT, build_home(broken_symlink=True)),
            "installed",
        )

    def test_unparsable_installed_fails(self) -> None:
        self.assert_finding(
            checker.check_repo(REPO_ROOT, build_home(installed="not jsonc {")),
            "installed",
        )

    def test_missing_file_with_install_artifacts_fails(self) -> None:
        """profiles.sh present but config gone = tampered/uninstalled posture."""
        self.assert_finding(
            checker.check_repo(
                REPO_ROOT, build_home(installed=None, profiles_sh=True)
            ),
            "installed",
            "profiles.sh",
        )


class NoInstallDetected(FixtureTestCase):
    """Bare hosts (CI runners) have no HOME-profile install: explicit skip."""

    def test_missing_file_without_artifacts_skips(self) -> None:
        findings = checker.check_repo(
            REPO_ROOT, build_home(installed=None, profiles_sh=False)
        )
        self.assertEqual(findings, [])
        self.assertTrue(checker.skip_reason(
            REPO_ROOT, build_home(installed=None, profiles_sh=False)
        ))

    def test_real_repo_control(self) -> None:
        """Installed host → PASS fresh; bare runner → explicit SKIP; both exit 0."""
        home = Path(os.environ["HOME"])
        installed_present = (home / ".config/opencode/opencode.jsonc").exists()
        proc = run_cli(REPO_ROOT, home)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        if installed_present:
            self.assertIn("PASS check_installed_posture_freshness", proc.stdout)
        else:
            self.assertIn("SKIP check_installed_posture_freshness", proc.stdout)


if __name__ == "__main__":
    unittest.main()
