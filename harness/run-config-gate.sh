#!/usr/bin/env bash
# Native pre-flight gate for THIS configuration repository (MADR-0003, #131):
# zero Docker, < 5 s, fail-fast - the native twin of the per-PR CI gate (ci.yml).
# Usage: harness/run-config-gate.sh [REPO_ROOT]   (default: this repo)
set -euo pipefail
REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO_ROOT}"
fail() { echo "FAIL run-config-gate: $1" >&2; exit 1; }
# 1/9 opencode.jsonc parses as JSON after comment stripping (port of ci.yml's
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
# 2/9 install.sh must be valid bash.
bash -n install.sh || fail "install.sh fails 'bash -n'"
echo "PASS run-config-gate: install.sh syntax OK"
# 3/9 all 7 agent files exist.
for agent in architect coach code-reviewer cyber-security developer devops scrum-master; do
  test -f "agents/${agent}.md" || fail "missing agents/${agent}.md"
done
echo "PASS run-config-gate: agent files present"
# 4/9 all 13 skill directories exist (exact list from ci.yml).
for skill in arc42-documentation coach docker-expert fastmcp-builder find-skills github-scrum-board harness-engineering home-governance madr-adr mermaid-diagrams opentofu-iac release-automation test-driven-development; do
  test -f "skills/${skill}/SKILL.md" || fail "missing skills/${skill}/SKILL.md"
done
echo "PASS run-config-gate: skill directories present"
# 5-7/9 native docs validators (links, MADR schema, mermaid syntax).
python3 harness/docs-validation/check_links.py . || fail "check_links.py failed"
python3 harness/docs-validation/check_madr.py . || fail "check_madr.py failed"
python3 harness/docs-validation/check_mermaid.py --syntax . || fail "check_mermaid.py --syntax failed"
# 8/9 mermaid syntax checker regression suite (#142 A1): stdlib unittest
# regression tests for check_mermaid.py --syntax (defect classes from #134,
# advisory from the #138 review - the suite was not executed by any gate).
python3 harness/docs-validation/test_check_mermaid_syntax.py || fail "test_check_mermaid_syntax.py failed"
# 9/9 coach-exclusivity permission invariant (#150 AC1-AC3): global default-deny
# baseline for the COACH_* MCP namespaces in opencode.jsonc, explicit per-agent
# denies in agents/, and agents/coach.md as the sole COACH_* allow whitelist.
python3 harness/config-validation/check_coach_exclusivity.py . || fail "check_coach_exclusivity.py failed"
echo "PASS run-config-gate: all 9 gates green (${REPO_ROOT})"
