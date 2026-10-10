#!/usr/bin/env python3
"""Enforce the namespace-exclusivity permission invariant (#150 AC1-AC3, #207 AC3).

Defense-in-depth scoping for the governed MCP namespaces, verified in one
pass per namespace:

  1. Global baseline: the root ``permission`` object of opencode.jsonc denies
     every canonical namespace pattern, so built-in subagents (explore,
     general, task) and any unconfigured persona have zero access by default.
  2. Per-agent explicit restatement: every agent spec in agents/ states every
     canonical namespace pattern of every governed namespace explicitly in
     its YAML front-matter.
  3. Sole allow whitelists: only the designated agent specs may allow a
     namespace; every other agent must deny it explicitly.

Governed namespaces (#150 for COACH_*, #207/MADR-0009 for BROWSER_*, #252 /
MADR-0011 for the extended GitHub MCP namespaces):

  ==================  ==========================  ============================
  Namespace           Canonical patterns          Sole allow whitelist
  ==================  ==========================  ============================
  COACH_*             COACH_DEV_*, COACH_QA_*,    coach.md
                      COACH_MAIN_*
  BROWSER_*           BROWSER_*                   developer.md, devops.md
  GITHUB_ACTIONS_*    GITHUB_ACTIONS_*            devops.md; developer.md holds
                                                  the governed partial allow
                                                  (read-only triage tools,
                                                  actions_run_trigger denied)
  GITHUB_SECURITY_*   GITHUB_SECURITY_*           cyber-security.md
  ==================  ==========================  ============================

Partial-allow posture (#252, MADR-0011 C3): one designated agent may hold
specific tool-level permission keys inside an otherwise denied namespace
(``PARTIAL_ALLOW_POLICIES``). Those keys are required verbatim for that
agent and exempt from pattern drift; any other tool-level key — for the
partial-allow agent or anyone else — is pattern drift, so ad-hoc tool
grants outside the governed posture are rejected.

Any permission key outside the canonical namespace patterns is a pattern-drift
error (legacy server-name-as-key keys such as "COACH MAIN" must not return —
servers were renamed COACH_DEV/QA/MAIN by #108, see arc42 §11).

Usage: check_coach_exclusivity.py [REPO_ROOT]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

# Governed namespaces: canonical permission patterns plus the only agent
# specs allowed to carry "allow" (#150 for COACH_*, #207/MADR-0009 for the
# Playwright browser MCP namespace, #252/MADR-0011 for the extended GitHub
# MCP namespaces).
NAMESPACE_POLICIES = {
    "COACH": {
        "keys": ("COACH_DEV_*", "COACH_QA_*", "COACH_MAIN_*"),
        "allow_agents": frozenset({"coach.md"}),
        "provenance": "#150",
    },
    "BROWSER": {
        "keys": ("BROWSER_*",),
        "allow_agents": frozenset({"developer.md", "devops.md"}),
        "provenance": "#207 (MADR-0009)",
    },
    "GITHUB_ACTIONS": {
        "keys": ("GITHUB_ACTIONS_*",),
        "allow_agents": frozenset({"devops.md"}),
        "provenance": "#252 (MADR-0011)",
    },
    "GITHUB_SECURITY": {
        "keys": ("GITHUB_SECURITY_*",),
        "allow_agents": frozenset({"cyber-security.md"}),
        "provenance": "#252 (MADR-0011)",
    },
}

# Governed partial-allow postures (#252, MADR-0011 C3): namespace -> agent
# file -> tool-level permission keys required verbatim inside an otherwise
# denied namespace. @developer keeps read-only CI triage (actions_get,
# actions_list, get_job_logs — the exact tool set exposed by the pinned
# v1.12.2 binary's actions toolset) while the monolithic actions_run_trigger
# (dispatch/cancel/log-delete in one tool) stays explicitly denied; every
# other tool of the namespace remains covered by the GITHUB_ACTIONS_* deny.
PARTIAL_ALLOW_POLICIES: dict[str, dict[str, dict[str, str]]] = {
    "GITHUB_ACTIONS": {
        "developer.md": {
            "GITHUB_ACTIONS_actions_get": "allow",
            "GITHUB_ACTIONS_actions_list": "allow",
            "GITHUB_ACTIONS_get_job_logs": "allow",
            "GITHUB_ACTIONS_actions_run_trigger": "deny",
        },
    },
}


def namespace_key_re(prefix: str) -> re.Pattern[str]:
    """Permission-key matcher for one namespace (pattern-drift detection)."""
    return re.compile(rf"^\s*({prefix}[A-Za-z0-9_]*\*?):\s*(allow|deny)\s*$")


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
    """Every governed namespace is default-denied at the root permission level."""
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
    for namespace, policy in NAMESPACE_POLICIES.items():
        for key in policy["keys"]:
            if permission.get(key) != "deny":
                failures.append(
                    f"{rel}: permission '{key}' must be \"deny\" (global "
                    f"default-deny baseline, {policy['provenance']}); found "
                    f"{permission.get(key)!r}"
                )
        for key in permission:
            if key.startswith(namespace) and key not in policy["keys"]:
                failures.append(
                    f"{rel}: unexpected {namespace} permission key '{key}' — "
                    f"only {', '.join(policy['keys'])} are canonical (pattern "
                    f"drift, see #108)"
                )


def agent_rules(agent: Path, key_re: re.Pattern[str]) -> dict[str, str]:
    """Namespace permission rules declared in an agent spec's YAML front-matter."""
    text = agent.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}
    rules: dict[str, str] = {}
    for line in match.group(1).splitlines():
        m = key_re.match(line)
        if m:
            rules[m.group(1)] = m.group(2)
    return rules


def check_agent_specs(root: Path, failures: list[str]) -> None:
    """Explicit restatement everywhere; allow reserved to the whitelist agents."""
    agents_dir = root / "agents"
    agent_files = sorted(agents_dir.glob("*.md"))
    if not agent_files:
        failures.append(f"agents/: no agent specs found under {agents_dir}")
        return
    for agent in agent_files:
        rel = agent.relative_to(root)
        text = agent.read_text(encoding="utf-8")
        has_front_matter = bool(FRONT_MATTER_RE.match(text))
        for namespace, policy in NAMESPACE_POLICIES.items():
            rules = agent_rules(agent, namespace_key_re(namespace))
            if not rules and not has_front_matter:
                failures.append(f"{rel}: no YAML front-matter found")
            expected = "allow" if agent.name in policy["allow_agents"] else "deny"
            for key in policy["keys"]:
                if key not in rules:
                    failures.append(
                        f"{rel}: missing required permission key '{key}' "
                        f"(every agent must state its {namespace} posture "
                        f"explicitly, {policy['provenance']})"
                    )
                elif rules[key] != expected:
                    failures.append(
                        f"{rel}: '{key}' must be '{expected}' "
                        f"(namespace-exclusivity invariant, "
                        f"{policy['provenance']}); found '{rules[key]}'"
                    )
            # #252 (MADR-0011 C3): governed partial-allow posture — the
            # designated agent's tool-level keys are required verbatim and
            # exempt from pattern drift below; any other tool-level key is
            # drift, for the partial-allow agent and everyone else.
            partial = PARTIAL_ALLOW_POLICIES.get(namespace, {}).get(agent.name, {})
            for key, value in partial.items():
                if key not in rules:
                    failures.append(
                        f"{rel}: missing required partial-allow key '{key}' "
                        f"(governed partial-allow posture, "
                        f"{policy['provenance']})"
                    )
                elif rules[key] != value:
                    failures.append(
                        f"{rel}: '{key}' must be '{value}' "
                        f"(governed partial-allow posture, "
                        f"{policy['provenance']}); found '{rules[key]}'"
                    )
            for key in rules:
                if key not in policy["keys"] and key not in partial:
                    failures.append(
                        f"{rel}: unexpected {namespace} permission key '{key}' "
                        f"— only {', '.join(policy['keys'])} are canonical "
                        f"(pattern drift, see #108)"
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
        print(
            "FAIL check_coach_exclusivity: namespace-exclusivity invariant "
            "violated:"
        )
        for failure in failures:
            print(f"  {failure}")
        return 1
    agent_count = len(sorted((root / "agents").glob("*.md")))
    print(
        f"PASS check_coach_exclusivity: global default-deny baselines + "
        f"{agent_count} agent spec(s) verified — COACH_* is @coach-only "
        f"(#150), BROWSER_* is @developer/@devops-only (#207), "
        f"GITHUB_ACTIONS_* is @devops-only with the @developer read-only "
        f"partial allow and GITHUB_SECURITY_* is @cyber-security-only "
        f"(#252, MADR-0011)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
