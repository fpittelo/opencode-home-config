#!/usr/bin/env python3
"""Read-only GitHub namespace identity probe (#423 AC3).

Separation of duties is a *credential* property, not a config property: the
``GITHUB_CODE_REVIEWER`` MCP server once resolved to ``@fpittelo`` (the PR
author) while every identity read still reported success, silently voiding the
Tier B approval boundary. This probe makes that drift detectable and
fail-closed.

For every GitHub MCP namespace it reads the token from the **environment
variable named in ``ENV_VARS``** (never from argv, never echoed) and asserts
``GET /user`` returns the expected **login AND id** — a login-only check passes
broken states, so the id is the assertion that matters.

Fail-closed behaviour:
  * any missing token, unexpected identity, or request error -> non-zero exit;
  * ``GITHUB_API_BASE_URL`` overrides are accepted for **loopback hosts only**
    (``127.0.0.1``, ``localhost``) so an environment variable can never forge a
    PASS against a remote endpoint;
  * running under an exported ``set -x`` shell (``SHELLOPTS`` contains
    ``xtrace``) is refused, since tracing echoes environment exports into logs.

The probe is read-only (no scope elevation), stdlib-only, and prints only
``<namespace>: <login>/<id> PASS|FAIL`` lines plus a summary. Token values are
never printed and never written to disk.

Usage:
    python3 harness/probes/verify-github-identities.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Single source of the expected identities: each pair is declared exactly once
# here, and the namespaces below alias these two constants only. Parity with
# docs/Admin-and-User-Guide.md §2.3 is asserted by
# harness/config-validation/test_github_identity_probe.py.
OWNER = ("fpittelo", 3135901)
REVIEWER = ("devfpittelo", 327061373)

EXPECTED_IDENTITIES: dict[str, tuple[str, int]] = {
    "GITHUB": OWNER,
    "GITHUB_CODE_REVIEWER": REVIEWER,
    "GITHUB_SECURITY": OWNER,
}

# Namespace -> environment variable holding its token (opencode.jsonc "mcp"
# block: GITHUB_SECURITY reuses the primary GITHUB token).
ENV_VARS: dict[str, str] = {
    "GITHUB": "GITHUB_PERSONAL_ACCESS_TOKEN",
    "GITHUB_CODE_REVIEWER": "GITHUB_TOKEN_CODE_REVIEWER",
    "GITHUB_SECURITY": "GITHUB_PERSONAL_ACCESS_TOKEN",
}

DEFAULT_API_BASE_URL = "https://api.github.com"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
SECRETS_FILE = Path(".config", "opencode", ".secrets-home.env")
REVIEWER_ENV_VAR = "GITHUB_TOKEN_CODE_REVIEWER"
REQUEST_TIMEOUT_SECONDS = 10
SYSTEMCTL_TIMEOUT_SECONDS = 5


class ProbeError(Exception):
    """A fail-closed probe condition carrying an operator-facing message."""


def resolve_api_base_url() -> str:
    """Return the API base URL, permitting overrides for loopback hosts only."""
    override = os.environ.get("GITHUB_API_BASE_URL", "").strip()
    if not override:
        return DEFAULT_API_BASE_URL
    parts = urllib.parse.urlsplit(override)
    if parts.scheme not in {"http", "https"} or parts.hostname not in LOOPBACK_HOSTS:
        raise ProbeError(
            f"refusing GITHUB_API_BASE_URL override {override!r}: "
            f"loopback hosts only ({sorted(LOOPBACK_HOSTS)})"
        )
    return override.rstrip("/")


def fetch_identity(api_base_url: str, token: str) -> tuple[str, int]:
    """Return (login, id) from ``GET /user``; the token stays out of argv."""
    request = urllib.request.Request(
        f"{api_base_url}/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as reply:
            payload = json.loads(reply.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ProbeError(f"request failed ({exc})") from exc
    if not isinstance(payload, dict):
        raise ProbeError("unexpected /user payload (not a JSON object)")
    login = payload.get("login")
    user_id = payload.get("id")
    if not isinstance(login, str) or not isinstance(user_id, int):
        raise ProbeError("unexpected /user payload (no login/id)")
    return login, user_id


def _parse_env_assignment(text: str, env_var: str) -> str | None:
    """Extract ``VAR=value`` / ``export VAR="value"`` from a secrets file body."""
    match = re.search(
        rf"^(?:export\s+)?{re.escape(env_var)}=(.*)$", text, re.MULTILINE
    )
    if match is None:
        return None
    return match.group(1).strip().strip("'\"")


def _secrets_file_token(env_var: str) -> str | None:
    try:
        text = (Path.home() / SECRETS_FILE).read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_env_assignment(text, env_var)


def _service_env_token(env_var: str) -> str | None:
    """Read the variable from ``systemctl --user show-environment`` (no argv token)."""
    try:
        completed = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True,
            text=True,
            timeout=SYSTEMCTL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        name, separator, value = line.partition("=")
        if separator and name == env_var:
            return value
    return None


def daemon_env_freshness(env_var: str) -> str:
    """Report ``yes``/``no``/``unknown``: is the daemon's env the secrets file's?

    Compares SHA-256 digests only — no token value, prefix, or hash is ever
    printed. This catches the documented #423 failure mode: the
    ``opencode serve --service`` daemon captured its environment at spawn, so a
    rotated secret silently leaves a stale credential in the running service.
    Best-effort by design: missing sources yield ``unknown``, never a failure.
    """
    file_token = _secrets_file_token(env_var)
    if not file_token:
        return "unknown"
    service_token = _service_env_token(env_var)
    if not service_token:
        return "unknown"
    file_digest = hashlib.sha256(file_token.encode()).digest()
    service_digest = hashlib.sha256(service_token.encode()).digest()
    return "yes" if file_digest == service_digest else "no"


def main() -> int:
    if "xtrace" in os.environ.get("SHELLOPTS", ""):
        print(
            "FAIL probe: shell xtrace is active (set -x exports secrets into the "
            "log) — re-run with tracing off",
            file=sys.stderr,
        )
        return 2
    try:
        api_base_url = resolve_api_base_url()
    except ProbeError as exc:
        print(f"FAIL probe: {exc}", file=sys.stderr)
        return 2

    failures = 0
    for namespace, (expected_login, expected_id) in EXPECTED_IDENTITIES.items():
        env_var = ENV_VARS[namespace]
        token = os.environ.get(env_var, "").strip()
        if not token:
            print(f"{namespace}: TOKEN MISSING ({env_var}) FAIL")
            failures += 1
            continue
        try:
            login, user_id = fetch_identity(api_base_url, token)
        except ProbeError as exc:
            print(f"{namespace}: REQUEST FAILED {exc} FAIL")
            failures += 1
            continue
        if (login, user_id) == (expected_login, expected_id):
            print(f"{namespace}: {login}/{user_id} PASS")
        else:
            print(
                f"{namespace}: {login}/{user_id} FAIL "
                f"(expected {expected_login}/{expected_id})"
            )
            failures += 1

    print(f"daemon env fresh: {daemon_env_freshness(REVIEWER_ENV_VAR)}")
    total = len(EXPECTED_IDENTITIES)
    print(f"SUMMARY: {total - failures}/{total} namespaces PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
