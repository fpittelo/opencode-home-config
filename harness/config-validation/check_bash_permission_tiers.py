#!/usr/bin/env python3
"""Enforce the bash tier invariants after root inheritance (#340).

Design shift (#340): the MADR-0004 five-file mirroring of the bash tiers is
SUPERSEDED by root inheritance. Verified opencode semantics (empirical probe
via ``opencode debug agent``, opencode 1.19.0):

  * An agent spec that OMITS the ``bash:`` key receives every config-level
    bash rule of ``opencode.jsonc`` (probe: agent with no ``bash:`` key
    resolved to exactly the root rule list, zero agent rules).
  * An agent that declares a (partial) ``bash:`` map has its rules APPENDED
    AFTER all config-level rules in the last-match-wins list (probe: an
    agent allow for a root-denied marker pattern overrode the config deny).

Consequences enforced below:

  1. ROOT BASELINE INTEGRITY — the root ``permission.bash`` block of
     opencode.jsonc equals BASELINE_ROOT_RULES exactly (order-sensitive pin
     of the MADR-0015 delta: ``"*"`` allow head + ask tier + frozen deny
     tail). The root block is the single source of truth; any edit must be
     a deliberate, reviewed change to this constant.
  2. CLEAN AGENT INHERITANCE — each of the four allow-default agent specs
     (agents/architect.md, agents/developer.md, agents/devops.md,
     agents/cyber-security.md) either omits ``bash:`` entirely or carries
     ONLY its documented role-deviation patterns (devops: ``docker *``
     allow; cyber-security: audit-tool allows). Re-stating any root tier
     pattern in an agent is now the DEFECT (it appends after the root deny
     tail and can widen the posture), not the requirement.
  3. LAST-MATCH-WINS TRUTH TABLE — a static resolver evaluates command
     strings against the ordered root rule list (fnmatch-style glob,
     last match wins, opencode semantics) and every expected verdict of
     the MADR-0015 delta must hold. A failing verdict against the real
     config is a REAL ordering defect: fix the config, not the table.
  4. NON-INHERITANCE AGENT SHAPES (#350) — scrum-master, code-reviewer
     and coach declare an explicit bash posture instead of inheriting;
     each shape is pinned order-sensitively (NON_INHERITANCE_AGENTS).
     scrum-master's three trailing secret-file denies (``*.env*`` /
     ``*.pem*`` / ``*.key*``) must sit AFTER its gh/git allows: agent
     rules append after the root deny tail, so without them an allow
     like ``gh pr *`` re-enables credential-file commands (e.g.
     ``gh pr edit 1 --body-file foo.env``). Every agent spec — including
     the four allow-default ones — is parsed in block form AND flow
     style (scalar ``bash: deny`` / flow mapping ``bash: {"*": deny}``);
     a flow-style header is no longer silently blessed.

Usage: check_bash_permission_tiers.py [REPO_ROOT]
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

# The four allow-default agent specs that used to mirror the tiers verbatim
# (MADR-0004) and now inherit the root baseline (#340).
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
    # #352 (MADR-0020 no-delete parity, PO decision (a) 2026-10-17): tail
    # append — the retired MADR-0016 server intentionally had no delete
    # capability; release deletion is machine-denied for every agent.
    "gh release delete*",
    # #362 (Sprint 23 spike, upstream anomalyco/opencode#56545): path-scoped
    # deny closing the recursive-read bypass against the secrets directory
    # (grep -r X ~/.config/opencode/ returned .secrets-home.env contents).
    "*/.config/opencode*",
)

# Ask-tier baseline as ratified by the MADR-0015 delta (#320 Slice B),
# order-sensitive: single ask checkpoint per destructive-but-recoverable
# family, plus the three workspace-scoped allow carve-outs.
BASELINE_ASK_TIER: tuple[tuple[str, str], ...] = (
    ("rm *", "ask"),
    ("rm /tmp/opencode/*", "allow"),
    ("rm -r /tmp/opencode/*", "allow"),
    ("pip install*", "ask"),
    ("pip3 install*", "ask"),
    ("uv pip install*", "ask"),
    ("*-m pip install*", "ask"),
    ("npm install -g*", "ask"),
    ("npm i -g*", "ask"),
    ("kill*", "ask"),
    ("pkill*", "ask"),
    ("killall*", "ask"),
    ("chmod *", "ask"),
    ("chmod 600 *", "allow"),
    ("chmod 700 *", "allow"),
    ("chown *", "ask"),
    ("systemctl*", "ask"),
)

# The full pinned root bash block: allow head + ask tier + deny tail. The
# root block of opencode.jsonc must equal this list exactly (#340).
BASELINE_ROOT_RULES: tuple[tuple[str, str], ...] = (
    (("*", "allow"),) + BASELINE_ASK_TIER + tuple(
        (pattern, "deny") for pattern in BASELINE_DENY_TAIL
    )
)

# Documented role-deviation patterns each agent MAY carry instead of the
# full inheritance (#340). Anything else — including any root tier pattern —
# is a defect. These are all redundant under the root "*": allow legibility
# signatures kept from MADR-0004; re-stating them as an agent bash map is
# permitted for documentation but discouraged (they would sit after the
# deny tail in the merged rule list).
AGENT_DEVIATIONS: dict[str, frozenset[str]] = {
    "architect.md": frozenset(),
    "developer.md": frozenset(),
    "devops.md": frozenset({"docker *"}),
    "cyber-security.md": frozenset(
        {
            "gitleaks*",
            "pip-audit*",
            "trivy*",
            "cargo audit *",
            "cargo deny *",
            "cargo metadata *",
            "cargo tree *",
            "sha256sum *",
            "opencode debug *",
            "opencode agent list*",
        }
    ),
}

# Non-inheritance agent specs (#350): these three declare an explicit bash
# posture instead of inheriting the root baseline. Their shapes are pinned
# ORDER-SENSITIVELY because agent rules append AFTER the root deny tail
# (last-match-wins): scrum-master's three trailing secret-file denies must
# stay AFTER its gh/git allows, or an allow like `gh pr *` would re-enable
# credential-file commands (e.g. `gh pr edit 1 --body-file foo.env`) — the
# append-override closed by #350. coach's scalar `bash: deny` normalizes to
# the single catch-all deny rule (flow/block equivalents accepted). Any edit
# is a deliberate, reviewed change to these constants.
NON_INHERITANCE_AGENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "scrum-master.md": (
        ("*", "deny"),
        ("gh issue *", "allow"),
        ("gh pr *", "allow"),
        ("git push origin --delete *", "allow"),
        ("*.env*", "deny"),
        ("*.pem*", "deny"),
        ("*.key*", "deny"),
    ),
    "code-reviewer.md": (
        ("*", "deny"),
        ("git status *", "allow"),
        ("git diff *", "allow"),
        ("git rev-parse *", "allow"),
        ("git cat-file *", "allow"),
        ("cat *", "allow"),
        ("grep *", "allow"),
        ("ls *", "allow"),
        ("*.env*", "deny"),
        ("*.pem*", "deny"),
        ("*.key*", "deny"),
    ),
    "coach.md": (("*", "deny"),),
}

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
    # #352 (MADR-0020 no-delete parity): release deletion is denied; create,
    # view and edit remain allowed (publishing stays governed by the PO
    # approval gate, home-governance Rule 5).
    ("gh release delete v1.0.0", "deny"),
    ("gh release create v1.0.0", "allow"),
    ("gh release view v1.0.0", "allow"),
    ("gh release edit", "allow"),
)

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
# bash: with an empty inline = block form; a non-empty inline = flow style
# (scalar tier or flow mapping) — both parsed since #350.
BASH_HEADER_RE = re.compile(r"^  bash:(?P<inline>.*)$")
NEXT_KEY_RE = re.compile(r"^  \S")
RULE_RE = re.compile(r'^\s*"([^"]+)":\s*(allow|ask|deny)\s*$')
FLOW_PAIR_RE = re.compile(r'"([^"]+)"\s*:\s*(allow|ask|deny)')
SCALAR_TIERS = frozenset({"allow", "ask", "deny"})


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


def parse_inline_bash(
    inline: str, rel: str, failures: list[str]
) -> list[tuple[str, str]]:
    """Normalize a flow-style bash value (#350): scalar or flow mapping.

    ``deny``/``allow``/``ask`` normalize to the equivalent single
    catch-all rule (opencode scalar semantics); ``{"*": deny}``-style
    flow mappings parse pair-wise. Anything else fails closed.
    """
    if inline in SCALAR_TIERS:
        return [("*", inline)]
    pairs = FLOW_PAIR_RE.findall(inline)
    if pairs and inline.startswith("{") and inline.endswith("}"):
        return [(pattern, tier) for pattern, tier in pairs]
    failures.append(
        f"{rel}: unparseable flow-style bash value {inline!r} — use the "
        f"block form, a scalar allow/ask/deny, or a flow mapping (#350)"
    )
    return []


def agent_bash(
    root: Path, agent: Path, failures: list[str]
) -> tuple[bool, list[tuple[str, str]]]:
    """(present, rules) of an agent spec's bash posture.

    present=False means the agent omits the bash key entirely — the
    legitimate inherited posture (#340). All three YAML spellings are
    parsed (#350): the block form (``bash:`` + indented rules), the flow
    mapping (``bash: {"*": deny}``) and the scalar (``bash: deny``).
    Parse/read problems are recorded as failures; comments and blank
    lines inside a block are skipped.
    """
    rel = agent.relative_to(root)
    try:
        text = agent.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{rel}: unreadable ({exc})")
        return False, []
    match = FRONT_MATTER_RE.match(text)
    if not match:
        failures.append(f"{rel}: no YAML front-matter found")
        return False, []
    lines = match.group(1).splitlines()
    start = next(
        (i for i, line in enumerate(lines) if BASH_HEADER_RE.match(line)), None
    )
    if start is None:
        return False, []  # inherited posture — no bash key at all
    inline = BASH_HEADER_RE.match(lines[start]).group("inline").strip()
    if inline:
        return True, parse_inline_bash(inline, rel, failures)
    rules: list[tuple[str, str]] = []
    for line in lines[start + 1 :]:
        if NEXT_KEY_RE.match(line):
            break  # the next permission key (read/edit/GITHUB_*) — block end
        rule = RULE_RE.match(line)
        if rule:
            rules.append((rule.group(1), rule.group(2)))
    return True, rules


def check_root_baseline(
    rules: list[tuple[str, str]], rel: str, failures: list[str]
) -> None:
    """The root block equals BASELINE_ROOT_RULES (order-sensitive pin)."""
    baseline = list(BASELINE_ROOT_RULES)
    ask_len = 1 + len(BASELINE_ASK_TIER)
    if rules == baseline:
        return
    failures.append(
        f"{rel}: root bash block has {len(rules)} rules, the MADR-0015 "
        f"baseline has {len(baseline)} — no removal, no insertion (the root "
        f"block is the single source of truth, #340)"
    )
    diverged_at: int | None = None
    for index in range(min(len(rules), len(baseline))):
        if rules[index] != baseline[index]:
            diverged_at = index
            break
    if diverged_at is None:
        # Prefix equality: the change sits at the end (removal/insertion).
        diverged_at = min(len(rules), len(baseline))
    region = "deny tail" if diverged_at >= ask_len else "ask tier"
    expected = (
        baseline[diverged_at] if diverged_at < len(baseline) else "end-of-list"
    )
    failures.append(
        f"{rel}: root bash block {region} diverges from the MADR-0015 "
        f"baseline at position {diverged_at}: expected {expected!r} — fix "
        f"the config, not the baseline constant"
    )


def check_agent_inheritance(root: Path, failures: list[str]) -> None:
    """Agents inherit the root baseline; only documented deviations may stay."""
    root_patterns = {pattern for pattern, _ in BASELINE_ROOT_RULES}
    for name in AGENT_FILES:
        agent = root / "agents" / name
        rel = agent.relative_to(root)
        present, rules = agent_bash(root, agent, failures)
        if not agent.is_file():
            failures.append(f"{rel}: missing agent spec file")
            continue
        if not present:
            continue  # clean inheritance (#340)
        if not rules:
            failures.append(
                f"{rel}: 'bash:' block present but carries no rules — drop "
                f"the key entirely to inherit the root baseline (#340)"
            )
            continue
        allowed = AGENT_DEVIATIONS[name]
        for pattern, tier in rules:
            if pattern in root_patterns:
                failures.append(
                    f"{rel}: bash pattern {pattern!r} re-states the root "
                    f"baseline (opencode.jsonc) — duplication is the defect "
                    f"since #340 (an agent bash map appends AFTER the root "
                    f"deny tail and can widen the posture); drop it and "
                    f"inherit"
                )
            elif pattern not in allowed:
                failures.append(
                    f"{rel}: bash pattern {pattern!r} is not a documented "
                    f"role deviation for this agent (allowed: "
                    f"{sorted(allowed) if allowed else 'none'}) — route a "
                    f"new role signature through @architect first (#340)"
                )
            elif tier != "allow":
                failures.append(
                    f"{rel}: role deviation {pattern!r} must be allow-tier, "
                    f"found {tier!r} (#340)"
                )


def check_non_inheritance_agents(root: Path, failures: list[str]) -> None:
    """The three non-inheritance agents match their pinned bash shapes (#350).

    scrum-master/code-reviewer/coach do NOT inherit the root baseline:
    they declare an explicit bash posture. Each shape is pinned
    order-sensitively (last-match-wins makes order semantic — the
    scrum-master trailing secret-file denies must stay AFTER its allows,
    else an allow re-enables a root-denied credential-file class).
    """
    for name, expected in NON_INHERITANCE_AGENTS.items():
        agent = root / "agents" / name
        rel = agent.relative_to(root)
        if not agent.is_file():
            failures.append(f"{rel}: missing agent spec file")
            continue
        present, rules = agent_bash(root, agent, failures)
        if not present:
            failures.append(
                f"{rel}: bash posture missing — omitting bash inherits the "
                f"root '*': allow head and widens the posture; declare the "
                f"pinned shape (#350)"
            )
            continue
        if rules != list(expected):
            failures.append(
                f"{rel}: bash posture diverges from the pinned "
                f"order-sensitive shape — expected {list(expected)}, found "
                f"{rules}; agent rules append AFTER the root deny tail "
                f"(last-match-wins), so the trailing '*.env*'/'*.pem*'/"
                f"'*.key*' denies must stay AFTER the allows (#350)"
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
    root_rule_list = root_rules(root, failures)
    if root_rule_list is not None:
        check_root_baseline(root_rule_list, "opencode.jsonc", failures)
        check_truth_table(root_rule_list, "opencode.jsonc", failures)
    check_agent_inheritance(root, failures)
    check_non_inheritance_agents(root, failures)
    if failures:
        print("FAIL check_bash_permission_tiers: bash tier invariant violated:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(
        f"PASS check_bash_permission_tiers: root permission.bash equals the "
        f"MADR-0015 baseline (allow head + {len(BASELINE_ASK_TIER)} ask + "
        f"{len(BASELINE_DENY_TAIL)} deny rules, order-sensitive), "
        f"{len(TRUTH_TABLE)}-case last-match-wins truth table green, "
        f"{len(AGENT_FILES)} allow-default agents inherit the root baseline "
        f"with zero root re-statements, and {len(NON_INHERITANCE_AGENTS)} "
        f"non-inheritance agents match their pinned order-sensitive bash "
        f"shapes incl. the scrum-master trailing secret-file denies "
        f"(#340, #350; opencode 1.19.0 verified)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))