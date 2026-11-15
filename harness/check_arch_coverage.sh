#!/usr/bin/env bash
# Path-derived, self-triggering architecture-coverage gate (#421).
#
# The former requires-architecture gate triggered on a human-applied PR label
# that no agent can set through any permitted path (no PR-label MCP tool,
# `gh api *` root-denied for every agent, `gh pr edit` broken for label
# writes #304), so it passed trivially for every squad PR — decorative, not a
# control. This replacement derives the requirement from the CHANGED PATHS:
# a PR diff that touches architecture-relevant behaviour must carry
# architecture documentation in the same diff, or the CI job fails. Zero
# human action, zero API calls (the gate is read-only over the local diff),
# and no bypass by omission.
#
# Trigger set (final, per grooming #421 comment 6893579054): agents/**,
# opencode.jsonc, .github/workflows/**, harness/**, skills/**.
# install.sh is deliberately EXCLUDED: a mechanical pin bump (e.g. #447,
# herdr binary digest refresh) changes supply-chain material but not
# architecture-relevant behaviour — forcing an ADR per pin would spam the
# MADR index and train humans to wave docs through.
#
# The requires-architecture LABEL remains, advisory-only: a reviewer may set
# it as a hint, but the gate no longer reads it and no requirement hangs on
# it (AC4). Do not delete the label.
#
# Usage: check_arch_coverage.sh BASE_SHA HEAD_SHA
# Operates on the git repo of the CURRENT working directory (ci.yml runs it
# at the repository root after checkout). Exit 0 = pass, exit 1 = coverage
# gap (the CI step must fail), exit 2 = usage/invocation error.
set -u

BASE_SHA="${1:-}"
HEAD_SHA="${2:-}"
if [ -z "$BASE_SHA" ] || [ -z "$HEAD_SHA" ]; then
  echo "usage: check_arch_coverage.sh BASE_SHA HEAD_SHA" >&2
  exit 2
fi
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: not inside a git work tree (run at the repository root)" >&2
  exit 2
fi

# Architecture-relevant trigger set; ^-anchored subtree prefixes + the exact
# config file. `install.sh` intentionally absent (see header).
TRIGGER_RE='^(agents/|\.github/workflows/|harness/|skills/|opencode\.jsonc$)'
# The two accepted documentation paths (either satisfies the gate).
DOC_RE='^(docs/adr/|docs/architecture/arc42/)'

CHANGED="$(git diff --name-only "$BASE_SHA" "$HEAD_SHA" || true)"
HITS="$(printf '%s\n' "$CHANGED" | grep -E "$TRIGGER_RE" || true)"
DOCS="$(printf '%s\n' "$CHANGED" | grep -E "$DOC_RE" || true)"

if [ -z "$HITS" ]; then
  echo "PASS: no architecture-relevant paths changed (gate not tripped, #421)."
  exit 0
fi

if [ -n "$DOCS" ]; then
  echo "PASS: architecture documentation present in the same diff (satisfying paths):"
  printf '%s\n' "$DOCS" | sed 's/^/  - /'
  echo "Architecture-relevant paths changed:"
  printf '%s\n' "$HITS" | sed 's/^/  - /'
  exit 0
fi

# Coverage gap: name exactly which trigger paths were hit and which doc
# paths would satisfy the gate (message quality = actionable triage).
echo "::error::architecture-relevant paths changed without architecture documentation (#421)."
echo "Trigger paths hit in this diff:"
printf '%s\n' "$HITS" | sed 's/^/  - /'
echo "Accepted documentation paths (add at least ONE of these to the same diff):"
echo "  - docs/adr/**          (a new or updated ADR, MADR schema)"
echo "  - docs/architecture/arc42/**  (an arc42 documentation update)"
echo "The install.sh path is deliberately excluded from the trigger set: mechanical pin bumps (e.g. #447) must not force ADRs."
echo "Full changed-path list:"
printf '%s\n' "$CHANGED" | sed 's/^/  - /'
exit 1
