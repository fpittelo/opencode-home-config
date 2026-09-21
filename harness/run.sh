#!/usr/bin/env bash
# HOME target-project quality-gates harness (STORY-04 #61, deliverable 3; KIS per #38).
#
# Usage: run.sh <python|rust> [deps|gate|all] [REPO_ROOT]
#   deps : network-ON phase  - resolve/fetch dependencies (uv sync / cargo fetch)
#   gate : network-OFF phase - lint, format, type-check, tests (fail-fast)
#   all  : deps then gate (default)
#
# Native fast path (MADR-0003, #131): when the host has the required toolchain
# the gates run natively (no docker cold start, no image pull, no volume
# warm-up); if ANY required tool is missing, the run falls back to the
# container path below unchanged (same security flags, same two-phase
# deps/gate design, same coverage threshold). Each phase prints which path it
# took and why. The network-off guarantee of the gate phase is container-only;
# native runs execute on the host under the operator's own controls.
#
# Coverage threshold: pytest --cov-fail-under=80 (80% minimum line coverage).
# The gate phase exits non-zero on ANY lint/format/type failure or coverage
# below threshold (AC6 of #61). Containers run with the harness security flags
# (non-root UID 1000, read-only root, dropped capabilities, no-new-privileges,
# bounded CPU/memory); the gate phase additionally runs with --network=none.
set -euo pipefail

STACK="${1:?usage: run.sh <python|rust> [deps|gate|all] [repo_root]}"
PHASE="${2:-all}"
REPO_ROOT="${3:-$(git rev-parse --show-toplevel)}"

PYTHON_IMAGE="ghcr.io/fpittelo/harness-runner-python:dev"
RUST_IMAGE="ghcr.io/fpittelo/harness-runner-rust:dev"

# Harness security flags (harness/README.md §5); network policy is per-phase.
SECURITY_FLAGS=(
  --read-only --user 1000:1000 --cap-drop=ALL
  --security-opt no-new-privileges
  --memory=4g --memory-swap=4g --cpus=2.0
  --tmpfs /tmp:noexec,nosuid,size=1g
  -v "${REPO_ROOT}:/workspace:rw" -w /workspace
)

python_deps() {
  echo "==> [deps] python dependency resolution (network ON)"
  if [[ ! -f "${REPO_ROOT}/pyproject.toml" ]]; then
    echo "SKIP deps: no pyproject.toml in ${REPO_ROOT}"
    return 0
  fi
  docker run --rm "${SECURITY_FLAGS[@]}" \
    -v harness-uv-cache:/home/harness/.cache/uv \
    -v harness-pip-cache:/home/harness/.cache/pip \
    "${PYTHON_IMAGE}" uv sync
}

python_gate() {
  echo "==> [gate] python quality gates (network OFF, fail-fast, coverage >= 80%)"
  docker run --rm --network=none "${SECURITY_FLAGS[@]}" \
    -v harness-uv-cache:/home/harness/.cache/uv \
    -v harness-pip-cache:/home/harness/.cache/pip \
    "${PYTHON_IMAGE}" bash -c '
      set -euo pipefail
      ruff check .
      black --check .
      isort --check-only .
      mypy --strict .
      pytest -W error --cov=. --cov-fail-under=80
    '
}

rust_deps() {
  echo "==> [deps] rust dependency fetch (network ON)"
  if [[ ! -f "${REPO_ROOT}/Cargo.toml" ]]; then
    echo "SKIP deps: no Cargo.toml in ${REPO_ROOT}"
    return 0
  fi
  docker run --rm "${SECURITY_FLAGS[@]}" \
    -v harness-cargo-registry:/home/harness/.cargo/registry \
    -v harness-cargo-git:/home/harness/.cargo/git \
    "${RUST_IMAGE}" cargo fetch
}

rust_gate() {
  echo "==> [gate] rust quality gates (network OFF, fail-fast)"
  docker run --rm --network=none "${SECURITY_FLAGS[@]}" \
    -v harness-cargo-registry:/home/harness/.cargo/registry \
    -v harness-cargo-git:/home/harness/.cargo/git \
    -v harness-cargo-target:/workspace/target \
    "${RUST_IMAGE}" bash -c '
      set -euo pipefail
      cargo fmt --check
      cargo clippy -- -D warnings
      cargo test
    '
}

# --- native fast path (MADR-0003, #131) --------------------------------------
# Host toolchain detection: the gate needs the FULL toolset (identical command
# chain as the container gate); deps needs uv/cargo only when a manifest exists.

python_native_tools_ok() {
  local tool
  for tool in ruff black isort mypy pytest; do
    command -v "${tool}" >/dev/null 2>&1 || return 1
  done
}

rust_native_tools_ok() {
  command -v cargo >/dev/null 2>&1
}

run_deps() {
  if [[ "${STACK}" == "python" ]]; then
    if [[ ! -f "${REPO_ROOT}/pyproject.toml" ]]; then
      echo "==> [deps] native path: SKIP (no pyproject.toml in ${REPO_ROOT})"
      return 0
    fi
    if command -v uv >/dev/null 2>&1; then
      echo "==> [deps] native path: host uv found - resolving python deps on the host (network ON)"
      (cd "${REPO_ROOT}" && uv sync)
      return 0
    fi
    echo "==> [deps] uv not on host PATH - container fallback (security flags preserved)"
  else
    if [[ ! -f "${REPO_ROOT}/Cargo.toml" ]]; then
      echo "==> [deps] native path: SKIP (no Cargo.toml in ${REPO_ROOT})"
      return 0
    fi
    if rust_native_tools_ok; then
      echo "==> [deps] native path: host cargo found - fetching rust deps on the host (network ON)"
      (cd "${REPO_ROOT}" && cargo fetch)
      return 0
    fi
    echo "==> [deps] cargo not on host PATH - container fallback (security flags preserved)"
  fi
  "${DEPS}"
}

run_gate() {
  if [[ "${STACK}" == "python" ]]; then
    if python_native_tools_ok; then
      echo "==> [gate] native path: host toolchain complete (ruff, black, isort, mypy, pytest) - fail-fast, coverage >= 80%"
      (cd "${REPO_ROOT}" &&
        ruff check . &&
        black --check . &&
        isort --check-only . &&
        mypy --strict . &&
        pytest -W error --cov=. --cov-fail-under=80)
      return 0
    fi
    echo "==> [gate] python toolchain incomplete on host (need ruff+black+isort+mypy+pytest) - container fallback (security flags, network-off, coverage threshold preserved)"
  else
    if rust_native_tools_ok; then
      echo "==> [gate] native path: host cargo found - fail-fast"
      (cd "${REPO_ROOT}" && cargo fmt --check && cargo clippy -- -D warnings && cargo test)
      return 0
    fi
    echo "==> [gate] cargo not on host PATH - container fallback (security flags, network-off preserved)"
  fi
  "${GATE}"
}

case "${STACK}" in
  python) DEPS=python_deps; GATE=python_gate ;;
  rust)   DEPS=rust_deps;   GATE=rust_gate ;;
  *) echo "error: unknown stack '${STACK}' (expected: python|rust)" >&2; exit 2 ;;
esac

case "${PHASE}" in
  deps) run_deps ;;
  gate) run_gate ;;
  all)  run_deps && run_gate ;;
  *) echo "error: unknown phase '${PHASE}' (expected: deps|gate|all)" >&2; exit 2 ;;
esac
