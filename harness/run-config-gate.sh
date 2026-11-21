#!/usr/bin/env bash
# Native pre-flight gate for THIS configuration repository (MADR-0003, #131):
# zero Docker, fail-fast - the native twin of the per-PR CI gate (ci.yml).
# Usage: harness/run-config-gate.sh [REPO_ROOT]   (default: this repo)
#
# TIER A of the two-tier config validation doctrine (#479, arc42 §1.2):
# per-push cost tracks real-repo invariants ONLY. Every invariant that used to
# be reachable solely through a `test_*.py` regression suite (#371 removed the
# back-to-back standalone checker runs) is re-expressed here as a DIRECT
# checker invocation against the real repo — identical enforcement semantics,
# fail-closed, same exit code. The checker regression suites (negative
# fixtures + sandboxed behavioral suites) are TIER B and run on the scheduled
# Deep Validation cadence (.github/workflows/deep-validation.yml), fully
# blocking under the MADR-0028 fail-closed rule. Mapping: harness/README.md §9.
set -euo pipefail
REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO_ROOT}"
fail() { echo "FAIL run-config-gate: $1" >&2; exit 1; }
# Gates are numbered sequentially with NO denominator (#441): appending a gate
# must never require rewriting every other gate's index comment.
# gate 1 opencode.jsonc parses as JSON after comment stripping (port of ci.yml's
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
# gate 2 install.sh must be valid bash.
bash -n install.sh || fail "install.sh fails 'bash -n'"
echo "PASS run-config-gate: install.sh syntax OK"
# gate 3 all 7 agent files exist.
for agent in architect coach code-reviewer cyber-security developer devops scrum-master; do
  test -f "agents/${agent}.md" || fail "missing agents/${agent}.md"
done
echo "PASS run-config-gate: agent files present"
# gate 4 all 16 skill directories exist (exact list from ci.yml).
for skill in arc42-documentation coach docker-expert fastmcp-builder find-skills gcp-docs github-scrum-board harness-engineering herdr home-governance kis-yagni madr-adr mermaid-diagrams opentofu-iac release-automation test-driven-development; do
  test -f "skills/${skill}/SKILL.md" || fail "missing skills/${skill}/SKILL.md"
done
echo "PASS run-config-gate: skill directories present"
# gate 5-7 native docs validators (links, MADR schema, mermaid syntax).
python3 harness/docs-validation/check_links.py . || fail "check_links.py failed"
python3 harness/docs-validation/check_madr.py . || fail "check_madr.py failed"
python3 harness/docs-validation/check_mermaid.py --syntax . || fail "check_mermaid.py --syntax failed"
# gate 8 YAML front-matter validity for agents/*.md (#338 AC1-AC2): proper ---
# delimiters, YAML parseability (duplicate keys rejected), mandatory schema
# (description, mode, openrouter/<slug> model, temperature in [0, 2], non-empty
# permission mapping). Closes the #325 defect class (corrupted front-matter
# passed the indentation-insensitive namespace checker). Direct checker run:
# the negative-fixture suite is Tier B (test_check_agent_frontmatter.py).
python3 harness/config-validation/check_agent_frontmatter.py . || fail "check_agent_frontmatter.py failed"
# gate 9 namespace-exclusivity permission invariant (#150 AC1-AC3, #207 AC3 /
# MADR-0009, #252/MADR-0011, #365/MADR-0008): global default-deny baselines in
# opencode.jsonc, explicit per-agent restatement in agents/, and the sole allow
# whitelists (COACH_*, BROWSER_*, GITHUB_SECURITY_*, openrouter_*,
# GITHUB_CODE_REVIEWER_*). Direct checker run: the negative-fixture suite is
# Tier B (test_check_coach_exclusivity.py).
python3 harness/config-validation/check_coach_exclusivity.py . || fail "check_coach_exclusivity.py failed"
# gate 10 BROWSER launch-flag invariant (#219 AC3 / MADR-0009): the mcp.BROWSER
# command array carries the mandated hardening flags — --isolated (ephemeral
# profile), --no-webmcp (WebMCP tool-poisoning vector), a loopback
# --allowed-origins allowlist (localhost + 127.0.0.1), and a scoped /tmp
# --output-dir. Direct checker run: the negative-fixture suite is Tier B
# (test_check_browser_launch_flags.py).
python3 harness/config-validation/check_browser_launch_flags.py . || fail "check_browser_launch_flags.py failed"
# gate 11 bash tier root-baseline integrity + clean agent inheritance (#340,
# superseding the MADR-0004/#320 five-file drift guard; #350 flow-style +
# pinned non-inheritance shapes; MADR-0027/#463 carve-out canary;
# MADR-0029/#475 wrapper family): the root permission.bash block is pinned to
# the MADR-0015 baseline (allow head + ask tier + frozen deny tail,
# order-sensitive), the last-match-wins truth table and the per-segment
# compound table hold, and each agent spec either inherits the root baseline
# (no bash key / no root re-statements) or matches its pinned order-sensitive
# shape. Direct checker run: the fixture suite is Tier B
# (test_check_bash_permission_tiers.py).
python3 harness/config-validation/check_bash_permission_tiers.py . || fail "check_bash_permission_tiers.py failed"
# gate 12 gitleaks allowlist + tracked-runtime-artifact gate (#448): no opencode
# runtime artifact (service.json, cli.json) may ever be TRACKED — the #405
# `git add -A` class that put a daemon credential in public history for 22
# days — and the incident's .gitleaks.toml allowlist must stay exactly ONE
# entry, attached to a rule with condition = "AND", scoped to the public commit
# fd15509 + the anchored service.json path, carrying no secret material.
# Direct checker run: the git-backed fixture suite is Tier B
# (test_check_gitleaks_allowlist.py).
python3 harness/config-validation/check_gitleaks_allowlist.py . || fail "check_gitleaks_allowlist.py failed"
# gate 13 external-prerequisite inventory (#441): every external command the
# config invokes is declared and correctly guarded — MCP command[0] launchers
# must be declared (the #435 npx class), a `command -v` entry must have its
# guard line in install.sh, a `provisioned` entry must be installed by the
# script itself, `unjustified` always fails, and a guarded entry that is no
# longer invoked is a stale-inventory finding. Direct checker run: the
# negative-fixture suite is Tier B (test_check_external_prerequisites.py).
python3 harness/config-validation/check_external_prerequisites.py . || fail "check_external_prerequisites.py failed"
# gate 14 installed-posture freshness (#449 AC2a, MADR-0029 C3): the installed
# $HOME/.config/opencode/opencode.jsonc must carry EVERY deny entry of the
# pinned root deny tail and resolve representative wrapper commands to deny in
# order — the #423 boot-chain class (a stale symlink or a replaced copy
# silently drops the denies). Explicit SKIP (exit 0) when no HOME-profile
# install exists (bare CI runners). Direct checker run: the fixture suite is
# Tier B (test_check_installed_posture_freshness.py).
python3 harness/config-validation/check_installed_posture_freshness.py . || fail "check_installed_posture_freshness.py failed"
# gate 15 MADR-0026 pin-freshness workflow gate (#446, C6): the O3 signal
# workflow's blast radius is machine-checkable — exact job permissions,
# built-in token only, checkout persist-credentials: false, tri-state failure
# paths, non-failing, weekly Monday cron staggered off the deep-validation
# slot, and the deterministic drift-issue mechanics. Direct checker run: the
# negative-fixture suite is Tier B (test_check_pin_freshness_workflow.py).
python3 harness/config-validation/check_pin_freshness_workflow.py . || fail "check_pin_freshness_workflow.py failed"
# gate 16 install-pin consistency (#310): exactly one GITHUB_MCP_VERSION
# assignment in install.sh, the binary at $HOME/.local/bin (when present)
# reports the pinned version, and every version literal in opencode.jsonc MCP
# comment lines citing "pinned" or "v<digit>" matches the pin (comment-drift
# guard). Kept in Tier A by #479: the suite asserts real-repo invariants only
# (no fixtures), so it IS the direct check.
python3 harness/config-validation/test_pin_consistency.py || fail "test_pin_consistency.py failed"
echo "PASS run-config-gate: all gates green (${REPO_ROOT})"
