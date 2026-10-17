"""Pinned GitHub API httpx client for the GITHUB_RELEASES server (MADR-0016).

Security posture (conditions 2, 6, 7, 11 of the MADR-0016 approval):

- The API origin, redirect behaviour, proxy handling and timeout are fixed
  constants — no tool argument can influence the URL, headers or transport.
- The owner is hard-pinned to ``fpittelo``; tools receive only the repo name
  (condition 1 in ``models.py``).
- The credential is read once from ``GITHUB_TOKEN_RELEASES`` (separate env
  var per condition 7) and wrapped in a ``pydantic.SecretStr``; it is written
  into the Authorization header at client construction and never echoed.
- Only POST/PATCH requests are possible (condition 8); retries are bounded
  (≤ 2) with exponential backoff, fired only on 5xx/429, honoring
  ``Retry-After`` (condition 11); failures raise :class:`ReleasesAPIError`
  carrying a sanitized payload.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from typing import Any, Final

import httpx
from pydantic import SecretStr

from github_releases_mcp.models import (
    CreateReleaseInput,
    UpdateReleaseInput,
    create_payload,
    update_payload,
)
from github_releases_mcp.utils import sanitize_error

OWNER: Final = "fpittelo"
API_BASE_URL: Final = "https://api.github.com"
REQUEST_TIMEOUT: Final = httpx.Timeout(30.0)
TOKEN_ENV_VAR: Final = "GITHUB_TOKEN_RELEASES"

ACCEPT_HEADER: Final = "application/vnd.github+json"
GITHUB_API_VERSION: Final = "2022-11-28"

# Condition 8: the transport layer only issues release-write methods.
_ALLOWED_METHODS: Final = frozenset({"POST", "PATCH"})

# Condition 11: <= 2 retries, exponential backoff, 5xx/429 only.
MAX_RETRIES: Final = 2
INITIAL_BACKOFF_SECONDS: Final = 1.0
_RETRYABLE_STATUS_RANGE: Final = range(500, 600)
_RATE_LIMIT_STATUS: Final = 429


class ReleasesAPIError(Exception):
    """GitHub API failure carrying a sanitized, token-free payload."""

    def __init__(self, payload: dict[str, str | int]) -> None:
        """Store the sanitized payload ({status, github_message})."""
        super().__init__(f"GitHub API error {payload['status']}")
        self.payload = payload


def load_releases_token(env: Mapping[str, str] | None = None) -> SecretStr:
    """Read the release credential once at startup (condition 7).

    Fail closed when the variable is missing or empty — the server must not
    start without its credential.
    """
    value = (os.environ if env is None else env).get(TOKEN_ENV_VAR, "")
    if not value.strip():
        raise RuntimeError(
            f"{TOKEN_ENV_VAR} is not set — the GITHUB_RELEASES server requires "
            "it before it is usable (populate ~/.config/opencode/.secrets-home.env)"
        )
    return SecretStr(value)


def build_client(
    token: SecretStr,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build the pinned API client; the Authorization header is fixed here.

    The ``transport`` parameter exists solely for test injection (mock
    transports); nothing derived from tool arguments can ever reach the base
    URL or the headers (condition 6).
    """
    return httpx.AsyncClient(
        base_url=API_BASE_URL,
        headers={
            "Authorization": f"Bearer {token.get_secret_value()}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        follow_redirects=False,
        trust_env=False,
        timeout=REQUEST_TIMEOUT,
        transport=transport,
    )


def _is_retryable(status: int) -> bool:
    """5xx class (500-599) or the rate-limit status only (condition 11)."""
    return status == _RATE_LIMIT_STATUS or status in _RETRYABLE_STATUS_RANGE


def _sleep_duration(response: httpx.Response, backoff_seconds: float) -> float:
    """Prefer the server's Retry-After hint; otherwise exponential backoff."""
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return backoff_seconds
    try:
        return float(retry_after)
    except ValueError:
        return backoff_seconds


def _top_message(response: httpx.Response) -> str:
    """Extract GitHub's ``message`` field; the body is never echoed raw."""
    try:
        document: Any = response.json()
    except ValueError:
        return ""
    message = document.get("message") if isinstance(document, dict) else None
    if isinstance(message, str):
        return message
    return ""


async def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Issue a fixed-method release-write request with bounded retry.

    Retries only 5xx/429 responses, at most ``MAX_RETRIES`` times (condition
    11), sleeping for the server's ``Retry-After`` hint or the exponential
    backoff sequence. Non-retryable failures raise :class:`ReleasesAPIError`
    with a sanitized payload; the token never appears anywhere in it.
    """
    if method not in _ALLOWED_METHODS:
        raise ValueError(f"request method not allowed: {method}")
    backoff_seconds = INITIAL_BACKOFF_SECONDS
    for attempt in range(MAX_RETRIES + 1):
        response = await client.request(method, path, json=payload)
        if response.is_success:
            document: dict[str, Any] = response.json()
            return document
        if _is_retryable(response.status_code) and attempt < MAX_RETRIES:
            await asyncio.sleep(_sleep_duration(response, backoff_seconds))
            backoff_seconds *= 2
            continue
        raise ReleasesAPIError(
            sanitize_error(response.status_code, _top_message(response))
        )
    raise ReleasesAPIError(sanitize_error(500, "unreachable: retry loop exhausted"))


def _releases_path(repo: str) -> str:
    """Releases collection path under the hard-pinned owner (condition 1)."""
    return f"/repos/{OWNER}/{repo}/releases"


async def create_release(
    client: httpx.AsyncClient,
    params: CreateReleaseInput,
) -> dict[str, Any]:
    """POST a new release for the pinned owner (condition 8: fixed method)."""
    return await request(client, "POST", _releases_path(params.repo), create_payload(params))


async def update_release(
    client: httpx.AsyncClient,
    params: UpdateReleaseInput,
) -> dict[str, Any]:
    """PATCH an existing release by id (condition 2: digits-only id in path)."""
    path = f"{_releases_path(params.repo)}/{params.release_id:d}"
    return await request(client, "PATCH", path, update_payload(params))
