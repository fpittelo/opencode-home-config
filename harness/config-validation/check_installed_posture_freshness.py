#!/usr/bin/env python3
"""Installed-posture freshness gate for the root bash deny tail (#449, gate 20).

The root bash deny tail (``gh run delete*``, ``gh cache delete*``, ``gh auth
*``, ``gh api *``, ...) is a structural control against the #449 failure
class: an agent session deleting gate evidence. It landed on trunk in
``e440e21`` — but the deny tail only protects sessions whose INSTALLED config
carries it. ``opencode serve --service`` and every agent session boot from
``$HOME/.config/opencode/opencode.jsonc``, which ``install.sh`` wires as a
symlink into the repo checkout; that link can keep pointing at a stale clone
after the repo moves, or be silently replaced by a copy, and a session booted
from the stale posture loses the denies with no error anywhere (the #423
boot-chain class).

This check asserts, fail-closed, that the installed file carries **every**
deny entry the validated tree has. Requirement source: ``BASELINE_DENY_TAIL``
from ``check_bash_permission_tiers.py`` (gate 14's pinned tail) — the deny
tail is single-sourced, never duplicated here.

MADR-0029 C3 (#475): membership alone is insufficient. The installed rules
are an ORDERED last-match-wins list, so a posture can carry every wrapper
deny entry and still resolve them to ``allow`` when the ``"*": allow`` head
sits after them (stale copy, hand edit, drifted merge). Gate 20 therefore
also resolves the shared ``WRAPPER_ORDERED_PROBES`` (``xargs pip install …``,
``timeout 5 curl``, ``env gh api``, compound ``true && xargs curl``) against
the ordered installed rules with gate 14's resolver and requires ``deny``.

Scope decisions (fail-closed where it matters):

- **Installed file missing AND no install artifacts** → explicit SKIP
  (exit 0): a bare host (CI runner) has no HOME-profile install, and the
  check's subject does not exist there. The skip is stated in the output so
  silence never masquerades as a verified-fresh posture.
- **Installed file missing BUT ``profiles.sh`` present** → FAIL: install
  artifacts exist while the config is gone — a tampered/uninstalled posture,
  not an uninstalled host.
- **Unreadable / broken-symlink / unparsable installed file** → FAIL: an
  unverifiable posture is not a fresh posture.
- **Extra deny entries in the installed file** → allowed: a stricter posture
  is never a freshness failure (the trunk-vs-installed direction only guards
  against MISSING denies).
- Run outside the repo gate as:
  ``python3 harness/config-validation/check_installed_posture_freshness.py [REPO_ROOT] [HOME]``

Usage: check_installed_posture_freshness.py [REPO_ROOT] [HOME]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from check_bash_permission_tiers import (
    BASELINE_DENY_TAIL,
    WRAPPER_ORDERED_PROBES,
    resolve_command,
)
from jsonc_utils import strip_jsonc

INSTALLED_REL = Path(".config/opencode/opencode.jsonc")
PROFILES_REL = Path(".config/opencode/profiles.sh")


def bash_rules(text: str) -> list[tuple[str, str]]:
    """The ORDERED (pattern, tier) rules of a config's root permission.bash."""
    data = json.loads(strip_jsonc(text))
    bash = data.get("permission", {}).get("bash")
    if not isinstance(bash, dict):
        raise ValueError("missing root permission.bash object")
    return [(str(pattern), str(tier)) for pattern, tier in bash.items()]


def bash_denies(text: str) -> set[str]:
    """The deny-keyed patterns of a config's root permission.bash block."""
    return {pattern for pattern, tier in bash_rules(text) if tier == "deny"}


def skip_reason(root: Path, home: Path) -> str | None:
    """Why the check skips (no HOME-profile install detected), else None.

    A symlink that exists but points nowhere counts as an INSTALLED posture
    (broken), not as an uninstalled host: ``Path.exists()`` is False for a
    dangling symlink, so the explicit ``is_symlink()`` test keeps the
    moved-checkout case fail-closed instead of skipping it.
    """
    installed = home / INSTALLED_REL
    if installed.exists() or installed.is_symlink():
        return None
    if (home / PROFILES_REL).exists():
        return None
    return (
        f"no HOME-profile install detected under {home / '.config/opencode'} "
        "(no opencode.jsonc, no profiles.sh) — nothing to verify; run "
        "install.sh to provision the posture"
    )


def check_repo(root: Path, home: Path) -> list[str]:
    """Return every finding for the installed posture (empty list = clean)."""
    findings: list[str] = []
    installed = home / INSTALLED_REL
    if skip := skip_reason(root, home):
        # No findings: the caller prints the SKIP line; exit stays 0.
        return findings

    if not installed.exists():
        # Reachable only for a dangling symlink or the tampered layout —
        # skip_reason() would have returned a skip otherwise.
        if installed.is_symlink():
            findings.append(
                f"installed config {installed} is a BROKEN symlink (target "
                "missing) — sessions booted from this posture resolve no "
                "config at all; re-run install.sh (#449 AC2a, fail-closed)"
            )
        else:
            findings.append(
                f"installed config {installed} MISSING while install "
                "artifacts (profiles.sh) are present — tampered or "
                "half-uninstalled posture; sessions boot with no structural "
                "denies (#449 AC2a, fail-closed). Re-run install.sh to "
                "re-provision"
            )
        return findings

    try:
        installed_text = installed.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            f"installed config {installed} unreadable ({exc}) — cannot verify "
            "the posture is fresh; a broken symlink or moved checkout means "
            "sessions may boot without the current deny tail (#449 AC2a, "
            "fail-closed)"
        )
        return findings

    try:
        installed_denies = bash_denies(installed_text)
        installed_rules = bash_rules(installed_text)
    except (json.JSONDecodeError, ValueError) as exc:
        findings.append(
            f"installed config {installed} unparsable ({exc}) — cannot verify "
            "the posture is fresh (#449 AC2a, fail-closed)"
        )
        return findings

    missing = sorted(set(BASELINE_DENY_TAIL) - installed_denies)
    for entry in missing:
        findings.append(
            f"installed config {installed} is MISSING the deny entry "
            f"{entry!r} that the validated tree carries — sessions booted "
            "from this posture lose the structural deny (stale install, "
            "replaced symlink, or drifted copy; #449 AC2a). Re-run "
            "install.sh to re-provision"
        )

    # MADR-0029 C3 (#475): resolve, do not just count. Order is semantic —
    # an installed file can carry every wrapper deny and still resolve them
    # to `allow` when the "*": allow head sits after them.
    for command in WRAPPER_ORDERED_PROBES:
        verdict = resolve_command(installed_rules, command)
        if verdict != "deny":
            findings.append(
                f"installed config {installed} resolves the wrapper command "
                f"{command!r} to {verdict!r}, expected 'deny' — the ordered "
                "rule list defeats the MADR-0029 wrapper tail (deny entry "
                "misplaced or shadowed; #449/gate 20, MADR-0029 C3). Re-run "
                "install.sh to re-provision"
            )
    return findings


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parents[2]
    )
    home = Path(argv[2]).resolve() if len(argv) > 2 else Path.home()
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    findings = check_repo(root, home)
    if findings:
        print("FAIL check_installed_posture_freshness: installed posture gate violated:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    if skip := skip_reason(root, home):
        print(
            f"SKIP check_installed_posture_freshness: {skip} (#449 gate 20)"
        )
        return 0
    print(
        "PASS check_installed_posture_freshness: installed config "
        f"{home / INSTALLED_REL} carries every deny entry of the pinned "
        f"root deny tail ({len(BASELINE_DENY_TAIL)} entries) and resolves "
        f"{len(WRAPPER_ORDERED_PROBES)} representative wrapper commands to "
        "deny in order — posture fresh (#449 gate 20, MADR-0029 C3)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
