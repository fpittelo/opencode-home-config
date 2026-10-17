#!/usr/bin/env python3
"""Enforce the bash ask/deny tier invariants (#320 Slice B, MADR-0015).

Three checks over the mirrored bash permission tiers:

  1. DRIFT GUARD — the ask-tier list and the deny-tier list are identical
     (order-sensitive) across all five mirrored locations: the root
     ``permission.bash`` block of opencode.jsonc and the four allow-default
     agent specs (agents/architect.md, agents/developer.md,
     agents/devops.md, agents/cyber-security.md). The tiers are duplicated
     verbatim by design (MADR-0004); a single-file edit silently changes
     the fleet's effective policy, so any divergence is a finding.
  2. DENY-TAIL FROZEN — the deny tier of the root block equals
     BASELINE_DENY_TAIL, the exact ordered pattern list captured from
     origin/dev before the MADR-0015 delta: no removal, no reorder, and no
     allow/ask rule interleaved inside the tail.
  3. LAST-MATCH-WINS TRUTH TABLE — a static resolver evaluates command
     strings against the ordered root rule list (fnmatch-style glob,
     last match wins, opencode semantics) and every expected verdict of
     the MADR-0015 delta must hold. A failing verdict against the real
     config is a REAL ordering defect: fix the config, not the table.

Usage: check_bash_permission_tiers.py [REPO_ROOT]
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

# The five mirrored locations: root config + the four allow-default agents.
AGENT_FILES = ("architect.md", "developer.md", "devops.md", "cyber-security.md")

# Deny-tail baseline captured from origin/dev HEAD before the #320 Slice B
# delta (MADR-0015): the ordered deny patterns that must never move.
BASELINE_DENY_TAIL: tuple[str, ...] = (
    "sudo*",
    "rm -rf /*",
    "rm -fr /*",
    "rm -rf /",
    "rm -rf ~*",
    "rm -rf $HOME*",
    "rm -rf ${HOME}*",
    "mkfs*",
    "dd *of=/dev/*",
    "shred*",
    "wipefs*",
    "blockdev*",
    "fdisk*",
    "sfdisk*",
    "gdisk*",
    "parted*",
    "truncate * /dev/*",
    "* > /dev/sd*",
    "* > /dev/nvme*",
    "* > /dev/mmcblk*",
    "* > /dev/vd*",
    "* > /dev/hd*",
    "mv * /dev/sd*",
    "mv * /dev/nvme*",
    "mv * /dev/mmcblk*",
    "shutdown*",
    "reboot*",
    "halt*",
    "poweroff*",
    "systemctl poweroff*",
    "systemctl reboot*",
    "systemctl halt*",
    "crontab*",
    "systemd-run*",
    "chmod -R * /*",
    "chown -R * /*",
    "find * -delete*",
    "find * -exec rm*",
    "git push --force*",
    "git push -f*",
    "git filter-branch*",
    "git filter-repo*",
    "git clean*",
    "git reset --hard*",
    "curl*",
    "wget*",
    "bash -c *",
    "sh *",
    "python* -c*",
    "node -e*",
    "node --eval*",
    "perl -e*",
    "ruby -e*",
    "printenv*",
    "env",
    "cat /proc/*/environ*",
    "*.env*",
    "*.pem*",
    "*.key*",
)

# Last-match-wins truth table of the ratified delta (MADR-0015): every
# verdict must hold against the real ordered rule list.
TRUTH_TABLE: tuple[tuple[str, str], ...] = (
    ("rm /tmp/opencode/x", "allow"),
    ("rm -r /tmp/opencode/x", "allow"),
    ("rm -rf /tmp/opencode/x", "deny"),
    ("rm -rf /", "deny"),
    ("rm secrets-home.env", "deny"),
    ("rm x", "ask"),
    ("chmod 600 x", "allow"),
    ("chmod 700 x", "allow"),
    ("chmod 755 x", "ask"),
    ("chmod +x x", "ask"),
    ("chmod -R 777 /", "deny"),
    ("pip install pkg", "ask"),
    ("pip3 install pkg", "ask"),
    ("uv pip install pkg", "ask"),
    ("python -m pip install pkg", "ask"),
    ("env", "deny"),
    ("printenv HOST", "deny"),
)

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
BASH_HEADER_RE = re.compile(r"^  bash:\s*$")
NEXT_KEY_RE = re.compile(r"^  \S")
RULE_RE = re.compile(r'^\s*"([^"]+)":\s*(allow|ask|deny)\s*$')


def strip_jsonc(text: str) -> str:
    """Strip // comments (mirrors the run-config-gate/ci.yml JSONC validator)."""
    out: list[str] = []
    i, in_str, esc = 0, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and text[i + 1 : i + 2] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def root_rules(root: Path, failures: list[str]) -> list[tuple[str, str]] | None:
    """Ordered (pattern, tier) pairs of the root permission.bash block."""
    config = root / "opencode.jsonc"
    rel = config.relative_to(root)
    try:
        data = json.loads(strip_jsonc(config.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        failures.append(f"{rel}: unreadable or invalid JSONC ({exc})")
        return None
    permission = data.get("permission")
    if not isinstance(permission, dict):
        failures.append(f"{rel}: missing root 'permission' object")
        return None
    bash = permission.get("bash")
    if not isinstance(bash, dict):
        failures.append(f"{rel}: missing root 'permission.bash' object")
        return None
    return [(str(pattern), str(tier)) for pattern, tier in bash.items()]


def agent_rules(
    root: Path, agent: Path, failures: list[str]
) -> list[tuple[str, str]] | None:
    """Ordered (pattern, tier) pairs of an agent spec's YAML bash block."""
    rel = agent.relative_to(root)
    try:
        text = agent.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{rel}: unreadable ({exc})")
        return None
    match = FRONT_MATTER_RE.match(text)
    if not match:
        failures.append(f"{rel}: no YAML front-matter found")
        return None
    lines = match.group(1).splitlines()
    start = next(
        (i for i, line in enumerate(lines) if BASH_HEADER_RE.match(line)), None
    )
    if start is None:
        failures.append(f"{rel}: no 'bash:' permission block in YAML front-matter")
        return None
    rules: list[tuple[str, str]] = []
    for line in lines[start + 1 :]:
        if NEXT_KEY_RE.match(line) or not line.strip():
            break  # the next permission key (read/edit/GITHUB_*) or block end
        rule = RULE_RE.match(line)
        if rule:
            rules.append((rule.group(1), rule.group(2)))
    if not rules:
        failures.append(f"{rel}: no permission rules found under 'bash:'")
        return None
    return rules


def tier_lists(rules: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """Ordered ask patterns and ordered deny patterns of one location."""
    ask = [pattern for pattern, tier in rules if tier == "ask"]
    deny = [pattern for pattern, tier in rules if tier == "deny"]
    return ask, deny


def check_tier_drift(
    locations: dict[str, list[tuple[str, str]]], failures: list[str]
) -> None:
    """Ask and deny tiers must be identical (order-sensitive) everywhere."""
    reference = locations.get("opencode.jsonc")
    if reference is None:
        return  # the root failure is already recorded
    ref_ask, ref_deny = tier_lists(reference)
    for name, rules in locations.items():
        if name == "opencode.jsonc":
            continue
        ask, deny = tier_lists(rules)
        if ask != ref_ask:
            failures.append(
                f"{name}: ask tier diverges from opencode.jsonc "
                f"(drift guard, MADR-0015): found {ask}, expected {ref_ask}"
            )
        if deny != ref_deny:
            failures.append(
                f"{name}: deny tier diverges from opencode.jsonc "
                f"(drift guard, MADR-0015): found {deny}, expected {ref_deny}"
            )


def check_deny_tail_frozen(
    rules: list[tuple[str, str]], rel: str, failures: list[str]
) -> None:
    """The root deny tier equals the baseline, contiguous and unmodified."""
    deny = [pattern for pattern, tier in rules if tier == "deny"]
    baseline = list(BASELINE_DENY_TAIL)
    if deny != baseline:
        if len(deny) != len(baseline):
            failures.append(
                f"{rel}: deny tail has {len(deny)} patterns, the MADR-0015 "
                f"baseline has {len(baseline)} — no removal, no insertion"
            )
        else:
            for index, (actual, expected) in enumerate(zip(deny, baseline)):
                if actual != expected:
                    failures.append(
                        f"{rel}: deny tail diverges from the MADR-0015 "
                        f"baseline at position {index}: found {actual!r}, "
                        f"expected {expected!r}"
                    )
                    break
    # Structural freeze: the deny tier is a contiguous tail — no allow/ask
    # rule may be interleaved inside it (MADR-0015: the deny tail is the
    # load-bearing wall of fleet isolation).
    first_deny = next((i for i, (_, tier) in enumerate(rules) if tier == "deny"), None)
    if first_deny is not None:
        interleaved = [
            pattern for pattern, tier in rules[first_deny:] if tier != "deny"
        ]
        if interleaved:
            failures.append(
                f"{rel}: non-deny rule(s) {interleaved} sit inside the deny "
                f"tail — the MADR-0015 baseline forbids insertions there"
            )


def resolve(rules: list[tuple[str, str]], command: str) -> str:
    """opencode last-match-wins resolution over the ordered rule list."""
    verdict = "allow"  # opencode's default posture when no rule matches
    for pattern, tier in rules:
        if fnmatch.fnmatchcase(command, pattern):
            verdict = tier
    return verdict


def check_truth_table(
    rules: list[tuple[str, str]], rel: str, failures: list[str]
) -> None:
    """Every expected verdict of the MADR-0015 delta must hold on the root."""
    for command, expected in TRUTH_TABLE:
        actual = resolve(rules, command)
        if actual != expected:
            failures.append(
                f"{rel}: command {command!r} resolves to {actual!r}, "
                f"expected {expected!r} (last-match-wins ordering defect, "
                f"fix the config ordering)"
            )


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    failures: list[str] = []
    locations: dict[str, list[tuple[str, str]]] = {}
    root_rule_list = root_rules(root, failures)
    if root_rule_list is not None:
        locations["opencode.jsonc"] = root_rule_list
        check_deny_tail_frozen(root_rule_list, "opencode.jsonc", failures)
        check_truth_table(root_rule_list, "opencode.jsonc", failures)
    for name in AGENT_FILES:
        agent = root / "agents" / name
        rules = agent_rules(root, agent, failures)
        if rules is not None:
            locations[f"agents/{name}"] = rules
    check_tier_drift(locations, failures)
    if failures:
        print("FAIL check_bash_permission_tiers: bash tier invariant violated:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(
        f"PASS check_bash_permission_tiers: ask/deny tiers identical across "
        f"{len(locations)} mirrored locations, deny tail frozen at the "
        f"MADR-0015 baseline ({len(BASELINE_DENY_TAIL)} patterns), "
        f"{len(TRUTH_TABLE)}-case last-match-wins truth table green "
        f"(#320, MADR-0015)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
