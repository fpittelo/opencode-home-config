"""Tests for the GITHUB_RELEASES httpx client (MADR-0016 conditions 2, 6, 7, 11).

The client pins the GitHub API origin, disables redirects and environment
proxy trust, carries a fixed 30 s timeout, builds the Authorization header at
startup from a SecretStr, retries at most twice with exponential backoff on
5xx/429 only while honoring Retry-After, and never exposes URL/header inputs
to tool arguments.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from github_releases_mcp.client import (
    API_BASE_URL,
    INITIAL_BACKOFF_SECONDS,
    ReleasesAPIError,
    build_client,
    create_release,
    load_releases_token,
    request,
    update_release,
)
from github_releases_mcp.models import CreateReleaseInput, UpdateReleaseInput

SECRET = "ghs_releases_test_secret_CANARY"


def _responding_client(
    responses: list[httpx.Response | BaseException],
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """Build a pinned client answering each call with the next queued response."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item

    client = build_client(SecretStr(SECRET), transport=httpx.MockTransport(handler))
    return client, calls


def _json_response(
    status: int,
    body: dict[str, str | int],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers or {})


async def test_build_client_pins_exact_configuration() -> None:
    client = build_client(SecretStr(SECRET))
    try:
        assert str(client.base_url).rstrip("/") == API_BASE_URL
        assert client.follow_redirects is False
        assert client.timeout == httpx.Timeout(30.0)
        assert client.trust_env is False
        assert client.headers["Authorization"] == f"Bearer {SECRET}"
        assert client.headers["Accept"] == "application/vnd.github+json"
        assert client.headers["X-GitHub-Api-Version"] == "2022-11-28"
    finally:
        await client.aclose()


async def test_request_rejects_methods_other_than_post_patch() -> None:
    client, calls = _responding_client([])
    try:
        for method in ("DELETE", "GET", "PUT"):
            with pytest.raises(ValueError, match="not allowed"):
                await request(client, method, "/repos/fpittelo/x/releases", {})
        assert calls == []
    finally:
        await client.aclose()


async def test_create_release_uses_post_and_pinned_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, calls = _responding_client([_json_response(201, {"id": 1, "tag_name": "v1"})])
    try:
        params = CreateReleaseInput(repo="coach", tag_name="v1", name="R1")
        release = await create_release(client, params)
        assert release["id"] == 1
        request_sent = calls[0]
        assert request_sent.method == "POST"
        assert str(request_sent.url) == f"{API_BASE_URL}/repos/fpittelo/coach/releases"
        assert request_sent.headers["Authorization"] == f"Bearer {SECRET}"
        assert request_sent.read() == b'{"tag_name":"v1","name":"R1"}'
    finally:
        await client.aclose()


async def test_update_release_uses_patch_and_digits_release_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, calls = _responding_client([_json_response(200, {"id": 42})])
    try:
        params = UpdateReleaseInput(repo="coach", release_id=42, draft=True)
        release = await update_release(client, params)
        assert release["id"] == 42
        request_sent = calls[0]
        assert request_sent.method == "PATCH"
        assert str(request_sent.url) == f"{API_BASE_URL}/repos/fpittelo/coach/releases/42"
        assert request_sent.read() == b'{"draft":true}'
    finally:
        await client.aclose()


async def _no_sleep(seconds: float) -> None:
    return None


async def test_retries_at_most_two_on_5xx_with_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    client, calls = _responding_client(
        [
            httpx.Response(500),
            httpx.Response(502),
            _json_response(201, {"id": 3}),
        ]
    )
    try:
        params = CreateReleaseInput(repo="coach", tag_name="v1")
        release = await create_release(client, params)
        assert release["id"] == 3
        assert len(calls) == 3
        base = INITIAL_BACKOFF_SECONDS
        assert sleeps == [base, base * 2]
    finally:
        await client.aclose()


async def test_retry_after_header_is_honored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    client, calls = _responding_client(
        [
            httpx.Response(429, headers={"Retry-After": "3"}),
            _json_response(200, {"id": 4}),
        ]
    )
    try:
        release = await update_release(client, UpdateReleaseInput(repo="coach", release_id=4))
        assert release["id"] == 4
        assert len(calls) == 2
        assert sleeps == [3.0]
    finally:
        await client.aclose()


async def test_429_without_retry_after_uses_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    client, calls = _responding_client(
        [
            httpx.Response(429),
            _json_response(200, {"id": 5}),
        ]
    )
    try:
        release = await update_release(client, UpdateReleaseInput(repo="coach", release_id=5))
        assert release["id"] == 5
        assert sleeps == [INITIAL_BACKOFF_SECONDS]
    finally:
        await client.aclose()


async def test_retries_bounded_at_two_then_error_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, calls = _responding_client([httpx.Response(503)])
    try:
        with pytest.raises(ReleasesAPIError) as excinfo:
            await create_release(client, CreateReleaseInput(repo="coach", tag_name="v1"))
        assert len(calls) == 3  # initial attempt + 2 retries
        assert excinfo.value.payload == {"status": 503, "github_message": ""}
    finally:
        await client.aclose()


async def test_4xx_is_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, calls = _responding_client([_json_response(422, {"message": "Validation Failed"})])
    try:
        with pytest.raises(ReleasesAPIError) as excinfo:
            await create_release(client, CreateReleaseInput(repo="coach", tag_name="v1"))
        assert len(calls) == 1
        assert excinfo.value.payload == {
            "status": 422,
            "github_message": "Validation Failed",
        }
    finally:
        await client.aclose()


async def test_transport_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, calls = _responding_client([httpx.ConnectError("dns down")])
    try:
        with pytest.raises(httpx.ConnectError):
            await create_release(client, CreateReleaseInput(repo="coach", tag_name="v1"))
        assert len(calls) == 1
    finally:
        await client.aclose()


async def test_non_json_error_body_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    client, calls = _responding_client([httpx.Response(500, text="<html>boom</html>")])
    try:
        with pytest.raises(ReleasesAPIError) as excinfo:
            await create_release(client, CreateReleaseInput(repo="coach", tag_name="v1"))
        assert excinfo.value.payload == {"status": 500, "github_message": ""}
        assert "<html>" not in str(excinfo.value.payload["github_message"])
    finally:
        await client.aclose()


def test_load_releases_token_wraps_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN_RELEASES", SECRET)
    token = load_releases_token()
    assert isinstance(token, SecretStr)
    assert SECRET not in repr(token)

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN_RELEASES"):
        monkeypatch.setenv("GITHUB_TOKEN_RELEASES", "")
        load_releases_token()

    monkeypatch.delenv("GITHUB_TOKEN_RELEASES")
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN_RELEASES"):
        load_releases_token()
