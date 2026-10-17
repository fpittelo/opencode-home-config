"""Error sanitization for the GITHUB_RELEASES server (MADR-0016 condition 7).

Tool errors surface to agents as a sanitized ``{status, github_message}``
payload — never the raw HTTP response body, and never any registered secret
value (the release token). Secret values are registered once at server
startup and redacted from every sanitized message thereafter.
"""
from __future__ import annotations

REDACTED_MARKER = "[REDACTED]"

# Process-global registry of secret values that must never appear in any
# sanitized payload. Populated once at server startup (lifespan) via
# :func:`register_secret`.
_registered_secrets: set[str] = set()


def register_secret(value: str) -> None:
    """Register a secret value for mandatory redaction (never logged/echoed)."""
    if value:
        _registered_secrets.add(value)


def clear_registered_secrets() -> None:
    """Empty the secret registry (test hygiene; not used at runtime)."""
    _registered_secrets.clear()


def _redact_secrets(message: str) -> str:
    """Replace every registered secret occurrence with the redaction marker."""
    for secret in _registered_secrets:
        if secret:
            message = message.replace(secret, REDACTED_MARKER)
    return message


def sanitize_error(status: int, github_message: str) -> dict[str, str | int]:
    """Return the sanitized error payload allowed out of the server.

    Only the HTTP status and GitHub's own ``message`` field survive: callers
    must pass the extracted message (NOT the raw response body), and every
    registered secret value is redacted before the payload leaves.
    """
    message = _redact_secrets(github_message)
    return {"status": status, "github_message": message}
