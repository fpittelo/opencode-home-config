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
MADR-0011 for the extended GitHub MCP namespaces, #311/MADR-0014 for the
Projects v2 planning namespace, #365/MADR-0008 for the OpenRouter MCP and
code-reviewer GitHub namespaces — audit finding D2):

  ==================  ==========================  ============================
  Namespace           Canonical patterns          Sole allow whitelist
  ==================  ==========================  ============================
  COACH_*             COACH_DEV_*, COACH_QA_*,    coach.md
                      COACH_MAIN_*
  BROWSER_*           BROWSER_*                   developer.md, devops.md
  GITHUB_SECURITY_*   GITHUB_SECURITY_*           cyber-security.md
  openrouter_*        openrouter_*                architect.md, coach.md
  GITHUB_CODE_REVIEWER_*  GITHUB_CODE_REVIEWER_*  code-reviewer.md
  ==================  ==========================  ============================

GITHUB_ACTIONS (#252, MADR-0011) is retired by MADR-0022 (#401): the
`GITHUB_ACTIONS` server block, the `GITHUB_ACTIONS_*` root baseline and all
per-agent rules are removed, and the CI triage surface is re-homed on the
pinned `gh` CLI under the bash tiers gate (`check_bash_permission_tiers.py`,
Gate 16 — root deny tail + @devops write carve-out + @developer read-only
posture). This module enforces the remaining MCP namespaces only.

Partial-allow posture (#252, MADR-0011 C3): one designated agent may hold
specific tool-level permission keys inside an otherwise denied namespace
(``PARTIAL_ALLOW_POLICIES``). Those keys are required verbatim for that
agent and exempt from pattern drift; any other tool-level key — for the
partial-allow agent or anyone else — is pattern drift, so ad-hoc tool
grants outside the governed posture are rejected.

Any permission key outside the canonical namespace patterns is a pattern-drift
error (legacy server-name-as-key keys such as "COACH MAIN" must not return —
servers were renamed COACH_DEV/QA/MAIN by #108, see `arc42/03` §3).

Usage: check_coach_exclusivity.py [REPO_ROOT]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jsonc_utils import strip_jsonc

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

# Governed namespaces: canonical permission patterns plus the only agent
# specs allowed to carry "allow" (#150 for COACH_*, #207/MADR-0009 for the
# Playwright browser MCP namespace, #252/MADR-0011 for the extended GitHub
# MCP namespaces, #311/MADR-0014 for the Projects v2 planning namespace,
# #365/MADR-0008 for the OpenRouter MCP and code-reviewer GitHub
# namespaces — audit finding D2).
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
    "GITHUB_SECURITY": {
        "keys": ("GITHUB_SECURITY_*",),
        "allow_agents": frozenset({"cyber-security.md"}),
        "provenance": "#252 (MADR-0011)",
    },
    # #365 (audit finding D2, MADR-0008): the OpenRouter MCP namespace is
    # @architect/@coach-only (model selection/evals) and the code-reviewer
    # GitHub namespace is @code-reviewer-only (SoD — approvals under the
    # separate @devfpittelo identity); every other agent denies both.
    "openrouter": {
        "keys": ("openrouter_*",),
        "allow_agents": frozenset({"architect.md", "coach.md"}),
        "provenance": "#365 (MADR-0008)",
    },
    "GITHUB_CODE_REVIEWER": {
        "keys": ("GITHUB_CODE_REVIEWER_*",),
        "allow_agents": frozenset({"code-reviewer.md"}),
        "provenance": "#365 (MADR-0008)",
    },
}

# Governed partial-allow postures (#252, MADR-0011 C3):
# namespace -> agent file -> tool-level permission keys required verbatim
# inside an otherwise denied namespace. Both partial-allow postures retired
# with their servers (MADR-0022): the GITHUB_ACTIONS @developer read-only
# triage (#401) moved to the pinned gh CLI under the bash tiers gate
# (check_bash_permission_tiers.py — root deny tail + the @devops write
# carve-out), and the GITHUB_PROJECTS governed writes (#400) retired because
# the Projects v2 namespace is no longer served by any MCP server.
PARTIAL_ALLOW_POLICIES: dict[str, dict[str, dict[str, str]]] = {}


def namespace_key_re(prefix: str) -> re.Pattern[str]:
    """Permission-key matcher for one namespace (pattern-drift detection)."""
    return re.compile(rf"^\s*({prefix}[A-Za-z0-9_]*\*?):\s*(allow|deny)\s*$")


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
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    failures: list[str] = []
    check_global_baseline(root, failures)
    check_agent_specs(root, failures)
    if failures:
        print(
            "FAIL check_coach_exclusivity: namespace-exclusivity invariant " "violated:"
        )
        for failure in failures:
            print(f"  {failure}")
        return 1
    agent_count = len(sorted((root / "agents").glob("*.md")))
    print(
        f"PASS check_coach_exclusivity: global default-deny baselines + "
        f"{agent_count} agent spec(s) verified — COACH_* is @coach-only "
        f"(#150), BROWSER_* is @developer/@devops-only (#207), "
        f"GITHUB_SECURITY_* is @cyber-security-only (#252, MADR-0011), "
        f"openrouter_* is @architect/@coach-only and GITHUB_CODE_REVIEWER_* "
        f"is @code-reviewer-only (#365, MADR-0008); the GITHUB_ACTIONS and "
        f"GITHUB_PROJECTS namespaces retired with their servers "
        f"(MADR-0022, #401 / #400)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
