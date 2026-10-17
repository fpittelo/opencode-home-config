"""Tests for GITHUB_RELEASES error sanitization (MADR-0016 condition 7).

Errors surfaced to agents are a sanitized {status, github_message} payload;
the raw response body never escapes, and any registered secret value (the
release token) must never survive into a returned payload.
"""
from __future__ import annotations

from github_releases_mcp.utils import (
    REDACTED_MARKER,
    clear_registered_secrets,
    register_secret,
    sanitize_error,
)


def setup_function() -> None:
    """Start every test with an empty secret registry (test isolation)."""
    clear_registered_secrets()


def teardown_function() -> None:
    clear_registered_secrets()


def test_sanitize_error_returns_status_and_message_only() -> None:
    payload = sanitize_error(404, "Not Found")
    assert payload == {"status": 404, "github_message": "Not Found"}


def test_raw_body_fields_are_dropped() -> None:
    payload = sanitize_error(403, "Forbidden")
    assert set(payload) == {"status", "github_message"}


def test_registered_token_is_redacted() -> None:
    fake_token = "ghs_FAKE_TOKEN_VALUE_1234567890"
    register_secret(fake_token)
    payload = sanitize_error(401, f"Bad credentials for {fake_token}")
    message = payload["github_message"]
    assert isinstance(message, str)
    assert fake_token not in message
    assert REDACTED_MARKER in message
    assert payload["status"] == 401


def test_unregistered_lookalike_without_registration_survives_sanitizer_contract() -> None:
    """Only explicitly registered secret material is redacted."""
    payload = sanitize_error(401, "Bad credentials")
    assert payload["github_message"] == "Bad credentials"


def test_multiple_registered_secrets_are_redacted() -> None:
    register_secret("secret-one")
    register_secret("secret-two")
    payload = sanitize_error(500, "one=secret-one two=secret-two")
    message = payload["github_message"]
    assert isinstance(message, str)
    assert "secret-one" not in message
    assert "secret-two" not in message
    assert message.count(REDACTED_MARKER) == 2


def test_empty_secrets_register_nothing() -> None:
    register_secret("")
    payload = sanitize_error(500, "boom")
    assert payload["github_message"] == "boom"
