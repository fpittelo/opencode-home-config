#!/usr/bin/env python3
"""Enforce the coach-exclusivity permission invariant (AC1-AC3 of #150).

Three-layer defense in depth, verified in one pass:

  1. Global baseline (AC1): the root ``permission`` object of opencode.jsonc
     denies all three Coach MCP namespaces (``COACH_DEV_*``, ``COACH_QA_*``,
     ``COACH_MAIN_*`` = "deny"), so built-in subagents (explore, general, task)
     and any unconfigured persona have zero Coach MCP access by default.
  2. Per-agent explicit denies (AC2): every agent spec in agents/ EXCEPT
     coach.md carries all three namespace denies in its YAML front-matter.
  3. Sole whitelist (AC3): agents/coach.md is the ONLY agent file whose
     front-matter allows the three namespaces.

Any COACH* permission key outside the three canonical namespace patterns is a
pattern-drift error (legacy server-name-as-key keys such as "COACH MAIN" must
not return — servers were renamed COACH_DEV/QA/MAIN by #108, see arc42 §11).

Usage: check_coach_exclusivity.py [REPO_ROOT]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

COACH_NAMESPACE_KEYS = ("COACH_DEV_*", "COACH_QA_*", "COACH_MAIN_*")
COACH_KEY_RE = re.compile(r"^\s*(COACH[A-Za-z0-9_]*\*?):\s*(allow|deny)\s*$")
FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


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


def check_global_baseline(root: Path, failures: list[str]) -> None:
    """AC1: the root permission object denies the three Coach namespaces."""
    config = root / "opencode.jsonc"
    rel = config.relative_to(root)
    try:
        data = json.loads(strip_jsonc(config.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        failures.append(f"{rel}: unreadable or invalid JSONC ({exc})")
        return
    permission = data.get("permission")
    if not isinstance(permission, dict):
        failures.append(f"{rel}: missing root 'permission' object")
        return
    for key in COACH_NAMESPACE_KEYS:
        if permission.get(key) != "deny":
            failures.append(
                f"{rel}: permission '{key}' must be \"deny\" (global default-deny "
                f"baseline, AC1 of #150); found {permission.get(key)!r}"
            )
    for key in permission:
        if key.startswith("COACH") and key not in COACH_NAMESPACE_KEYS:
            failures.append(
                f"{rel}: unexpected Coach permission key '{key}' — only "
                f"{', '.join(COACH_NAMESPACE_KEYS)} are canonical (pattern "
                f"drift, see #108)"
            )


def coach_rules(agent: Path) -> dict[str, str]:
    """COACH* permission rules declared in an agent spec's YAML front-matter."""
    text = agent.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}
    rules: dict[str, str] = {}
    for line in match.group(1).splitlines():
        m = COACH_KEY_RE.match(line)
        if m:
            rules[m.group(1)] = m.group(2)
    return rules


def check_agent_specs(root: Path, failures: list[str]) -> None:
    """AC2/AC3: explicit denies everywhere, sole allow whitelist on @coach."""
    agents_dir = root / "agents"
    agent_files = sorted(agents_dir.glob("*.md"))
    if not agent_files:
        failures.append(f"agents/: no agent specs found under {agents_dir}")
        return
    for agent in agent_files:
        rel = agent.relative_to(root)
        rules = coach_rules(agent)
        if not rules and not FRONT_MATTER_RE.match(
            agent.read_text(encoding="utf-8")
        ):
            failures.append(f"{rel}: no YAML front-matter found")
        expected = "allow" if agent.name == "coach.md" else "deny"
        for key in COACH_NAMESPACE_KEYS:
            if key not in rules:
                failures.append(
                    f"{rel}: missing required permission key '{key}' "
                    f"(every agent must state its Coach posture explicitly, "
                    f"AC2/AC3 of #150)"
                )
        for key, value in rules.items():
            if key not in COACH_NAMESPACE_KEYS:
                failures.append(
                    f"{rel}: unexpected Coach permission key '{key}' — only "
                    f"{', '.join(COACH_NAMESPACE_KEYS)} are canonical (pattern "
                    f"drift, see #108)"
                )
            elif value != expected:
                failures.append(
                    f"{rel}: '{key}' must be '{expected}' (coach-exclusivity "
                    f"invariant, AC2/AC3 of #150); found '{value}'"
                )


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    failures: list[str] = []
    check_global_baseline(root, failures)
    check_agent_specs(root, failures)
    if failures:
        print("FAIL check_coach_exclusivity: coach-exclusivity invariant violated:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    agent_count = len(sorted((root / "agents").glob("*.md")))
    print(
        f"PASS check_coach_exclusivity: global default-deny baseline + "
        f"{agent_count} agent spec(s) verified — Coach MCP is @coach-only (#150)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
