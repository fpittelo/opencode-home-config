#!/usr/bin/env bash
# Docs quality gate orchestrator (ADR-0001, STORY-04 #61).
# Runs the three stdlib validators in sequence and fails fast on the first
# failure. This is the single entry point the harness/CI calls.
# Usage: run_docs_validation.sh [REPO_ROOT]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"

echo "==> [1/3] mermaid block validation"
python3 "${SCRIPT_DIR}/check_mermaid.py" "${ROOT}"
echo "==> [2/3] relative link validation"
python3 "${SCRIPT_DIR}/check_links.py" "${ROOT}"
echo "==> [3/3] MADR schema validation"
python3 "${SCRIPT_DIR}/check_madr.py" "${ROOT}"
echo "PASS docs-validation: all checks passed (${ROOT})"
