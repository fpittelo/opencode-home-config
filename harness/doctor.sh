#!/usr/bin/env bash
# harness/doctor.sh — operator doctor: one-command posture check (#462).
#
# Report-only diagnostic for the three recurring posture concerns (audit
# #460 R4): (a) service token freshness, (b) GitHub identity resolution,
# (c) installed-config posture. Zero mutations, zero auto-remediation —
# findings name the remediation command, never run it (AC2/KIS).
#
# Two-tier doctrine (AC5): this is an OPERATOR diagnostic in the gate-16
# probe class — never wired into CI as a required check; static invariants
# stay in the config gates.
#
# Secret hygiene (AC4, #448 iron rule): the secrets file is `stat`-ed only
# (existence + mtime age). Its contents are NEVER read, printed, or
# written. The identity check reuses the gate-16 probe
# (harness/probes/verify-github-identities.py), whose output is
# token-material-free by construction (login/id only). The doctor itself
# never sources the secrets file — run it under the oc-home wrapper so the
# ambient environment carries the tokens the probe needs.
#
# Reuse, not duplication (AC1): posture integrity delegates verbatim to the
# gate-20 checker (harness/config-validation/check_installed_posture_freshness.py);
# identity delegates verbatim to the gate-16 probe. No second implementation
# of either.
#
# Env overrides (testability seams; defaults are the host paths):
#   DOCTOR_SECRETS_FILE      secrets file to stat (default: ~/.config/opencode/.secrets-home.env)
#   DOCTOR_PROBE             identity probe path   (default: <repo>/harness/probes/verify-github-identities.py)
#   DOCTOR_POSTURE_CHECKER   gate-20 checker path   (default: <repo>/harness/config-validation/check_installed_posture_freshness.py)
#
# Exit: 0 = all fresh; 1 = findings (summary table with a remediation hint
# each); 2 = usage/invocation error. A SKIP row (no HOME-profile install)
# counts as neither fresh nor a finding.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_FILE="${DOCTOR_SECRETS_FILE:-${HOME:?}/.config/opencode/.secrets-home.env}"
PROBE="${DOCTOR_PROBE:-${REPO_ROOT}/harness/probes/verify-github-identities.py}"
POSTURE_CHECKER="${DOCTOR_POSTURE_CHECKER:-${REPO_ROOT}/harness/config-validation/check_installed_posture_freshness.py}"

FINDINGS=0
ROWS=()

record() { # record STATUS CHECK DETAIL
  ROWS+=("${1}|${2}|${3}")
}

fail() { # fail CHECK DETAIL — a finding
  FINDINGS=$((FINDINGS + 1))
  record "FAIL" "$1" "$2"
}

# (a) Token freshness — stat only: existence + mtime age. NEVER contents.
check_token_freshness() {
  if [ ! -e "${SECRETS_FILE}" ]; then
    fail "token-freshness" \
      "secrets file not found at ${SECRETS_FILE} — populate it and restart the service daemon with secrets sourced (oc-home wrapper pattern, #423)"
    return 0
  fi
  local mtime age_days
  mtime="$(stat -c '%Y' "${SECRETS_FILE}")"
  age_days=$(( ($(date +%s) - mtime) / 86400 ))
  record "OK" "token-freshness" \
    "token file present, last rotated ${age_days} day(s) ago (${SECRETS_FILE})"
}

# (b) GitHub identity — delegate verbatim to the gate-16 probe. Its output
# is token-material-free by construction; a non-zero exit (drift or missing
# ambient token) is a finding, and its FAIL lines are surfaced as-is.
check_github_identity() {
  if [ ! -f "${PROBE}" ]; then
    fail "github-identity" "identity probe not found at ${PROBE} — run from a repository checkout"
    return 0
  fi
  local probe_out probe_status
  if probe_out="$(python3 "${PROBE}" 2>&1)"; then
    probe_status=0
  else
    probe_status=$?
  fi
  local fail_lines
  fail_lines="$(printf '%s\n' "${probe_out}" | grep -E 'FAIL|missing token|refus' || true)"
  if [ "${probe_status}" -eq 0 ]; then
    record "OK" "github-identity" "$(printf '%s\n' "${probe_out}" | tail -n 1)"
  elif [ -n "${fail_lines}" ]; then
    fail "github-identity" "probe reported drift or refusal (exit ${probe_status}): $(printf '%s\n' "${fail_lines}" | head -n 3 | tr '\n' ' ')"
  else
    fail "github-identity" "probe exited ${probe_status} with no actionable output — run 'python3 ${PROBE}' directly for the full read-only report"
  fi
}

# (c) Installed posture — delegate verbatim to the gate-20 checker; surface
# its verdict (PASS fresh / SKIP uninstalled / FAIL with its findings text).
check_installed_posture() {
  if [ ! -f "${POSTURE_CHECKER}" ]; then
    fail "installed-posture" "gate-20 checker not found at ${POSTURE_CHECKER} — run from a repository checkout"
    return 0
  fi
  local checker_out checker_status
  if checker_out="$(python3 "${POSTURE_CHECKER}" "${REPO_ROOT}" "${HOME:-}" 2>&1)"; then
    checker_status=0
  else
    checker_status=$?
  fi
  local first_line
  first_line="$(printf '%s\n' "${checker_out}" | head -n 1)"
  case "${first_line}" in
    PASS*)
      record "OK" "installed-posture" "${first_line}"
      ;;
    SKIP*)
      record "SKIP" "installed-posture" "${first_line}"
      ;;
    *)
      local detail
      detail="$(printf '%s\n' "${checker_out}" | grep -m1 '^  ' | sed 's/^  //')"
      fail "installed-posture" "${detail:-${first_line}} (checker exit ${checker_status}; re-run install.sh to re-provision)"
      ;;
  esac
}

main() {
  check_token_freshness
  check_github_identity
  check_installed_posture

  echo "=== operator doctor — report-only posture check (#462) ==="
  printf '%s\n' "${ROWS[@]}" | awk -F'\\|' '{ printf "%-6s %-18s %s\n", $1, $2, substr($0, index($0, $3)) }'
  echo
  if [ "${FINDINGS}" -gt 0 ]; then
    echo "findings: ${FINDINGS} — each row above carries its remediation hint; nothing was changed (report-only)."
    exit 1
  fi
  if printf '%s\n' "${ROWS[@]}" | grep -q '^SKIP|'; then
    echo "no findings (one or more checks skipped — see the SKIP row above; report-only)."
    exit 0
  fi
  echo "all checks fresh — nothing to do (report-only)."
  exit 0
}

main "$@"
