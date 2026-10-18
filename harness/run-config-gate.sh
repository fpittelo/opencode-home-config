#!/usr/bin/env bash
# Native pre-flight gate for THIS configuration repository (MADR-0003, #131):
# zero Docker, < 5 s, fail-fast - the native twin of the per-PR CI gate (ci.yml).
# Usage: harness/run-config-gate.sh [REPO_ROOT]   (default: this repo)
set -euo pipefail
REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO_ROOT}"
fail() { echo "FAIL run-config-gate: $1" >&2; exit 1; }
# 1/15 opencode.jsonc parses as JSON after comment stripping (port of ci.yml's
# validator; quoted heredoc = no bash expansion, so plain Python quoting).
python3 - <<'PY' || fail "opencode.jsonc is not valid JSONC"
import json, sys
def strip_jsonc(text):
    out, i, in_str, esc = [], 0, False, False
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
        elif c == "/" and text[i + 1:i + 2] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)
with open("opencode.jsonc", encoding="utf-8") as handle:
    try:
        json.loads(strip_jsonc(handle.read()))
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSONC: {exc}")
print("PASS run-config-gate: opencode.jsonc is valid JSONC")
PY
# 2/15 install.sh must be valid bash.
bash -n install.sh || fail "install.sh fails 'bash -n'"
echo "PASS run-config-gate: install.sh syntax OK"
# 3/15 all 7 agent files exist.
for agent in architect coach code-reviewer cyber-security developer devops scrum-master; do
  test -f "agents/${agent}.md" || fail "missing agents/${agent}.md"
done
echo "PASS run-config-gate: agent files present"
# 4/15 all 15 skill directories exist (exact list from ci.yml).
for skill in arc42-documentation coach docker-expert fastmcp-builder find-skills github-scrum-board harness-engineering herdr home-governance kis-yagni madr-adr mermaid-diagrams opentofu-iac release-automation test-driven-development; do
  test -f "skills/${skill}/SKILL.md" || fail "missing skills/${skill}/SKILL.md"
done
echo "PASS run-config-gate: skill directories present"
# 5-7/15 native docs validators (links, MADR schema, mermaid syntax).
python3 harness/docs-validation/check_links.py . || fail "check_links.py failed"
python3 harness/docs-validation/check_madr.py . || fail "check_madr.py failed"
python3 harness/docs-validation/check_mermaid.py --syntax . || fail "check_mermaid.py --syntax failed"
# 8/15 mermaid syntax checker regression suite (#142 A1): stdlib unittest
# regression tests for check_mermaid.py --syntax (defect classes from #134,
# advisory from the #138 review - the suite was not executed by any gate).
python3 harness/docs-validation/test_check_mermaid_syntax.py || fail "test_check_mermaid_syntax.py failed"
# 9/15 namespace-exclusivity permission invariant (#150 AC1-AC3, #207 AC3 /
# MADR-0009): global default-deny baselines for the COACH_* and BROWSER_* MCP
# namespaces in opencode.jsonc, explicit per-agent restatement in agents/,
# and the sole allow whitelists (agents/coach.md for COACH_*; agents/
# developer.md + agents/devops.md for BROWSER_*), enforced by the checker
# regression suite (#142 A1 pattern): stdlib unittest regression tests for
# check_coach_exclusivity.py — both governed namespaces, negative cases per
# invariant layer, real-repo positive control (the single real-repo checker
# run per gate execution since #371 removed the back-to-back standalone run).
python3 harness/config-validation/test_check_coach_exclusivity.py || fail "test_check_coach_exclusivity.py failed"
# 10/15 BROWSER launch-flag invariant (#219 AC3 / MADR-0009): the mcp.BROWSER
# command array in opencode.jsonc carries the mandated hardening flags —
# --isolated (ephemeral profile), --no-webmcp (WebMCP tool-poisoning vector),
# a loopback --allowed-origins allowlist (localhost + 127.0.0.1), and a
# scoped /tmp --output-dir, enforced by the checker regression suite
# (#142 A1 pattern): stdlib unittest regression tests for
# check_browser_launch_flags.py — negative cases per mandated flag and value
# shape, real-repo positive control (the single real-repo checker run per
# gate execution since #371 removed the back-to-back standalone run).
python3 harness/config-validation/test_check_browser_launch_flags.py || fail "test_check_browser_launch_flags.py failed"
# 11/15 harness native-gate toolchain pinning regression suite (#256 AC5):
# stdlib unittest regression tests for harness/run.sh — deps retains dev
# extras (uv sync --all-extras), the native gate resolves tools from the
# project .venv (never host PATH), and exits 3 when the venv or a required
# tool is missing; the container fallback keeps its security flags.
python3 harness/config-validation/test_harness_run.py || fail "test_harness_run.py failed"
# 12/15 per-pane profile selection regression suite (#263, #244): stdlib
# unittest TDD suite for dual-profile coexistence and per-pane secrets
# isolation — profiles.sh provisioning, oc-home wrapper semantics, secrets
# split/migration, legacy switcher cleanup, permission hardening,
# .gitignore coverage. Sandboxed fake $HOME.
python3 tests/test_per_pane_profile_selection.py || fail "test_per_pane_profile_selection.py failed"
# 13/15 install-pin consistency regression suite (#310): stdlib unittest TDD
# suite for the github-mcp-server supply-chain pin — exactly one
# GITHUB_MCP_VERSION assignment in install.sh, the binary at
# $HOME/.local/bin (when present) reports the pinned version, and every
# version literal in opencode.jsonc MCP comment lines citing "pinned" or
# "v<digit>" matches the pin (comment-drift guard).
python3 harness/config-validation/test_pin_consistency.py || fail "test_pin_consistency.py failed"
# 14/15 bash tier root-baseline integrity + clean agent inheritance (#340,
# superseding the MADR-0004/#320 five-file drift guard): the root
# opencode.jsonc permission.bash block is pinned to the MADR-0015 baseline
# (allow head + ask tier + frozen deny tail, order-sensitive), the 17-case
# last-match-wins truth table holds on the root block, and each of the four
# allow-default agent specs either omits bash: entirely (root inheritance,
# verified on opencode 1.19.0: an agent without a bash key receives every
# config-level bash rule; a partial agent bash map appends AFTER the deny
# tail) or carries only documented role-deviation patterns — re-stating
# root tier patterns in an agent is now the defect. #350: every agent spec
# is parsed in block AND flow style (scalar/flow mapping), and the three
# non-inheritance agents (scrum-master, code-reviewer, coach) must match
# their pinned order-sensitive bash shapes — incl. the scrum-master
# trailing secret-file denies that close the append-override of the root
# *.env*/*.pem*/*.key* denies.
python3 harness/config-validation/test_check_bash_permission_tiers.py || fail "test_check_bash_permission_tiers.py failed"
# 15/15 YAML front-matter validity gate for agents/*.md (#338 AC1-AC2):
# every agent file's front-matter block must have proper --- delimiters,
# parse as YAML (duplicate keys rejected), and carry the mandatory schema
# (description, mode, openrouter/<slug> model, temperature in [0, 2],
# non-empty permission mapping). Closes the #325 defect class (corrupted
# front-matter passed the indentation-insensitive namespace checker).
python3 harness/config-validation/test_check_agent_frontmatter.py || fail "test_check_agent_frontmatter.py failed"
echo "PASS run-config-gate: all 15 gates green (${REPO_ROOT})"
