#!/usr/bin/env bash
# Native pre-flight gate for THIS configuration repository (MADR-0003, #131):
# zero Docker, < 5 s, fail-fast - the native twin of the per-PR CI gate (ci.yml).
# Usage: harness/run-config-gate.sh [REPO_ROOT]   (default: this repo)
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
# gate 8 mermaid syntax checker regression suite (#142 A1): stdlib unittest
# regression tests for check_mermaid.py --syntax (defect classes from #134,
# advisory from the #138 review - the suite was not executed by any gate).
python3 harness/docs-validation/test_check_mermaid_syntax.py || fail "test_check_mermaid_syntax.py failed"
# gate 9 namespace-exclusivity permission invariant (#150 AC1-AC3, #207 AC3 /
# MADR-0009): global default-deny baselines for the COACH_* and BROWSER_* MCP
# namespaces in opencode.jsonc, explicit per-agent restatement in agents/,
# and the sole allow whitelists (agents/coach.md for COACH_*; agents/
# developer.md + agents/devops.md for BROWSER_*), enforced by the checker
# regression suite (#142 A1 pattern): stdlib unittest regression tests for
# check_coach_exclusivity.py — both governed namespaces, negative cases per
# invariant layer, real-repo positive control (the single real-repo checker
# run per gate execution since #371 removed the back-to-back standalone run).
python3 harness/config-validation/test_check_coach_exclusivity.py || fail "test_check_coach_exclusivity.py failed"
# gate 10 BROWSER launch-flag invariant (#219 AC3 / MADR-0009): the mcp.BROWSER
# command array in opencode.jsonc carries the mandated hardening flags —
# --isolated (ephemeral profile), --no-webmcp (WebMCP tool-poisoning vector),
# a loopback --allowed-origins allowlist (localhost + 127.0.0.1), and a
# scoped /tmp --output-dir, enforced by the checker regression suite
# (#142 A1 pattern): stdlib unittest regression tests for
# check_browser_launch_flags.py — negative cases per mandated flag and value
# shape, real-repo positive control (the single real-repo checker run per
# gate execution since #371 removed the back-to-back standalone run).
python3 harness/config-validation/test_check_browser_launch_flags.py || fail "test_check_browser_launch_flags.py failed"
# gate 11 harness native-gate toolchain pinning regression suite (#256 AC5):
# stdlib unittest regression tests for harness/run.sh — deps retains dev
# extras (uv sync --all-extras), the native gate resolves tools from the
# project .venv (never host PATH), and exits 3 when the venv or a required
# tool is missing; the container fallback keeps its security flags.
python3 harness/config-validation/test_harness_run.py || fail "test_harness_run.py failed"
# gate 12 per-pane profile selection regression suite (#263, #244): stdlib
# unittest TDD suite for dual-profile coexistence and per-pane secrets
# isolation — profiles.sh provisioning, oc-home wrapper semantics, secrets
# split/migration, legacy switcher cleanup, permission hardening,
# .gitignore coverage. Sandboxed fake $HOME.
python3 tests/test_per_pane_profile_selection.py || fail "test_per_pane_profile_selection.py failed"
# gate 13 install-pin consistency regression suite (#310): stdlib unittest TDD
# suite for the github-mcp-server supply-chain pin — exactly one
# GITHUB_MCP_VERSION assignment in install.sh, the binary at
# $HOME/.local/bin (when present) reports the pinned version, and every
# version literal in opencode.jsonc MCP comment lines citing "pinned" or
# "v<digit>" matches the pin (comment-drift guard).
python3 harness/config-validation/test_pin_consistency.py || fail "test_pin_consistency.py failed"
# gate 14 bash tier root-baseline integrity + clean agent inheritance (#340,
# superseding the MADR-0004/#320 five-file drift guard): the root
# opencode.jsonc permission.bash block is pinned to the MADR-0015 baseline
# (allow head + ask tier + frozen deny tail, order-sensitive), the 24-case
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
# gate 15 YAML front-matter validity gate for agents/*.md (#338 AC1-AC2):
# every agent file's front-matter block must have proper --- delimiters,
# parse as YAML (duplicate keys rejected), and carry the mandatory schema
# (description, mode, openrouter/<slug> model, temperature in [0, 2],
# non-empty permission mapping). Closes the #325 defect class (corrupted
# front-matter passed the indentation-insensitive namespace checker).
python3 harness/config-validation/test_check_agent_frontmatter.py || fail "test_check_agent_frontmatter.py failed"
# gate 16 GitHub namespace identity probe regression suite (#423 AC3): stdlib
# unittest TDD suite for harness/probes/verify-github-identities.py — the
# read-only SoD drift probe. Asserts the expected login AND id per namespace
# (a login-only check passed the #423 defect), fails closed on a missing token
# and on a non-loopback GITHUB_API_BASE_URL override, and keeps the expected
# identity map single-sourced and in parity with the Admin guide §2.3 table.
# Offline: a loopback http.server stands in for /user, driven by dummy tokens.
python3 harness/config-validation/test_github_identity_probe.py || fail "test_github_identity_probe.py failed"
# gate 17 external-prerequisite inventory (#441): every external command the
# config invokes is declared and correctly guarded — MCP command[0] launchers
# must be declared (the #435 npx class), a `command -v` entry must have its
# guard line in install.sh (runtime-token guards accepted when the token is
# assigned the same tool), a `provisioned` entry must be installed by the
# script itself, `unjustified` always fails, and a guarded entry that is no
# longer invoked is a stale-inventory finding. #142 A1 pattern: negative
# fixtures + real-repo positive control, offline, stdlib-only.
python3 harness/config-validation/test_check_external_prerequisites.py || fail "test_check_external_prerequisites.py failed"
# gate 18 gitleaks allowlist + tracked-runtime-artifact gate (#448): no
# opencode runtime artifact (service.json, cli.json) may ever be TRACKED — the
# #405 `git add -A` class that put a daemon credential in public history for 22
# days — and the incident's .gitleaks.toml allowlist must stay exactly ONE
# entry, attached to a rule with condition = "AND", scoped to the public commit
# fd15509 + the anchored service.json path (a path-only or OR entry would be a
# blanket waiver), carrying no secret material. Fail-closed; git-backed
# fixtures + real-repo positive control.
python3 harness/config-validation/test_check_gitleaks_allowlist.py || fail "test_check_gitleaks_allowlist.py failed"
# gate 19 MADR-0026 pin-freshness workflow gate (#446, C6): the O3 signal
# workflow's blast radius is machine-checkable — job-level permissions exactly
# {contents: read, issues: write} (no top-level block, no contents: write /
# pull-requests: write / actions: write / id-token), built-in token only (zero
# secrets.*/PAT references), checkout persist-credentials: false, tri-state
# failure paths (unknown on every API/parse failure branch, fresh assigned
# exactly once by the semver comparison, never a || fallback-to-fresh),
# non-failing (no non-zero exit), weekly Monday cron staggered off the
# deep-validation slot (fail-closed on that file), and the deterministic
# drift-issue mechanics (hidden marker, fixed agent::devops + type::task
# labels, @devfpittelo notification statement, asset + checksums naming, no
# status:: label, no auto-close, no cache, no second version literal).
# #142 A1 pattern: negative fixtures + real-repo positive control, offline.
python3 harness/config-validation/test_check_pin_freshness_workflow.py || fail "test_check_pin_freshness_workflow.py failed"
# gate 20 installed-posture freshness (#449 AC2a): the root bash deny tail
# (gh run delete*, gh cache delete*, gh auth *, gh api *, ...) only protects
# sessions whose INSTALLED config carries it — opencode serve --service and
# every agent session boot from $HOME/.config/opencode/opencode.jsonc, which
# install.sh wires as a symlink that can go stale (moved checkout) or be
# replaced by a copy, silently dropping the denies (the #423 boot-chain
# class). The check asserts the installed file carries EVERY deny entry of
# the pinned BASELINE_DENY_TAIL (single-sourced from gate 14's checker);
# fail-closed on unreadable/broken-symlink/unparsable/tampered-posture
# shapes; explicit SKIP (exit 0) when no HOME-profile install exists (bare
# CI runners). #142 A1 pattern: negative fixtures + real-host positive
# control, offline, stdlib-only.
python3 harness/config-validation/test_check_installed_posture_freshness.py || fail "test_check_installed_posture_freshness.py failed"
# gate 21 architecture-coverage gate logic (#421): the path-derived
# self-triggering gate that replaced the requires-architecture label read —
# a PR diff touching agents/**, opencode.jsonc, .github/workflows/**,
# harness/** or skills/** must carry docs/adr/** or docs/architecture/arc42/**
# changes in the same diff, or the CI job fails; install.sh deliberately
# excluded (mechanical pin bumps must not force ADRs, #447 class). The test
# suite drives the REAL script (harness/check_arch_coverage.sh — the exact
# logic ci.yml invokes) against synthetic two-commit diffs: per-path
# negative cases, both accepted doc paths as satisfiers, docs-only and
# excluded-path positives, deletion-surface, empty-diff, message quality
# (failure names hit paths + accepted doc paths + the exclusion rationale),
# and a real-repo no-op control. #142 A1 pattern: synthetic fixtures +
# real-repo positive control, offline, stdlib-only.
python3 harness/config-validation/test_check_arch_coverage.py || fail "test_check_arch_coverage.py failed"
# gate 22 operator-doctor orchestrator semantics (#462): harness/doctor.sh is
# a thin REPORT-ONLY orchestrator of reused checkers (gate-16 identity probe
# + gate-20 posture checker) — the suite pins its OWN contract: exit
# semantics (findings -> 1 with per-check rows), per-check isolation (one
# failing check never aborts the others), the SKIP mapping, report-only
# behavior (fake HOME untouched), and the #448 iron rule as a static pin
# (the script stat()s the secrets file, never cat/source/read-redirects it;
# no token material in output). Offline: the probe fails fast on a missing
# ambient token; the all-fresh path is covered by the live host run in the
# PR. Two-tier doctrine: the doctor itself is never wired into CI — only
# its regression suite runs here.
python3 harness/config-validation/test_doctor_script.py || fail "test_doctor_script.py failed"
echo "PASS run-config-gate: all gates green (${REPO_ROOT})"
