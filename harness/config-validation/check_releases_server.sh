#!/usr/bin/env bash
# Gate 17: GITHUB_RELEASES server supply-chain + quality gate (#323, MADR-0016
# condition 10). The home-grown Python FastMCP server (tools/
# github-releases-mcp) is a new artifact class with its own dependency surface,
# audited on every config-gate run and PR run by its own dedicated script —
# WITHOUT repointing harness/run.sh (root pyproject intentionally absent,
# MADR-0016). Fail-fast, mirrors run-config-gate.sh echo style.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/tools/github-releases-mcp"
fail() { echo "FAIL check_releases_server: $1" >&2; exit 1; }

[ -f "${PROJECT_DIR}/pyproject.toml" ] || fail "missing ${PROJECT_DIR}/pyproject.toml"
command -v uv >/dev/null 2>&1 || fail "uv not found on PATH — gate 17 requires the pinned uv toolchain"

cd "${PROJECT_DIR}"

# Dependencies: the committed uv.lock is the pin (MADR-0016 condition 10);
# --locked fails on any drift between pyproject.toml and uv.lock.
echo "⏳  uv sync --locked (GITHUB_RELEASES dependency set)..."
uv sync --locked || fail "uv sync --locked failed (uv.lock drift or unresolvable dependency set)"

echo "⏳  ruff (GITHUB_RELEASES)..."
uv run ruff check . || fail "ruff check failed"

echo "⏳  mypy --strict (GITHUB_RELEASES)..."
uv run mypy --strict src tests || fail "mypy --strict failed"

echo "⏳  pytest -W error + coverage >= 80% (GITHUB_RELEASES)..."
uv run pytest -q -W error --cov=github_releases_mcp --cov-fail-under=80 \
    || fail "pytest failed (zero-warning suite with >= 80% coverage required)"

echo "⏳  pip-audit --strict (GITHUB_RELEASES dependency audit)..."
# Audit exactly the committed uv.lock pin set: the lock is exported to a
# requirements file (with per-package hashes, uv export's default) WITHOUT
# the project itself (--no-emit-project — the local GITHUB_RELEASES
# distribution is private-only with no PyPI counterpart), then audited with
# --no-deps so --strict fails the gate on any known vulnerability among the
# locked dependencies without a redundant re-resolution. The project install
# itself is exercised by the test tiers above; the audited supply chain is
# the locked dependency set.
AUDIT_REQS="$(mktemp)"
trap 'rm -f "$AUDIT_REQS"' EXIT
uv export --locked --no-emit-project --format requirements-txt -o "$AUDIT_REQS" \
    || fail "uv export failed (uv.lock drift or unresolvable dependency set)"
uv run pip-audit --strict --no-deps -r "$AUDIT_REQS" \
    || fail "pip-audit --strict found known vulnerabilities"

echo "PASS check_releases_server: GITHUB_RELEASES server gate green (uv sync --locked, ruff, mypy --strict, pytest -W error + coverage >= 80%, pip-audit --strict)"