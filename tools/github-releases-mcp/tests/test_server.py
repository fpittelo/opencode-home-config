"""Tests for the GITHUB_RELEASES FastMCP server (MADR-0016 conditions 1, 7, 8).

Condition 8: the tool inventory is EXACTLY {create_release, update_release}
and no tool schema exposes URL/header/token/owner/method parameters.
Condition 7: structured logs contain {tool, repo, tag_name, release_id,
outcome} but never the token and never release body text; sanitized error
payloads never leak the token.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from github_releases_mcp import utils
from github_releases_mcp.client import build_client
from github_releases_mcp.models import CreateReleaseInput, UpdateReleaseInput
from github_releases_mcp.server import (
    app_lifespan,
    mcp,
    run_create_release,
    run_update_release,
)

SECRET = "ghs_server_test_secret_CANARY"
BODY_CANARY = "BODY-TEXT-MUST-NOT-BE-LOGGED-42"

_FORBIDDEN_PARAMETER_NAMES = frozenset(
    {"owner", "token", "url", "header", "authorization", "base_url", "method"}
)


def setup_function() -> None:
    utils.clear_registered_secrets()


def teardown_function() -> None:
    utils.clear_registered_secrets()


def _responding_client(status: int, body: dict[str, Any]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return build_client(SecretStr(SECRET), transport=httpx.MockTransport(handler))


def _iter_property_names(node: Any) -> Iterator[str]:
    """Collect every JSON-schema property name reachable from a schema."""
    if isinstance(node, dict):
        for name, value in node.items():
            if name == "properties" and isinstance(value, dict):
                yield from value
            yield from _iter_property_names(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_property_names(item)


async def test_tool_inventory_is_exactly_two_release_tools() -> None:
    tools = await mcp.list_tools()
    assert {tool.name for tool in tools} == {"create_release", "update_release"}
    assert len(tools) == 2


async def test_tools_are_write_only() -> None:
    tools = await mcp.list_tools()
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False


async def test_no_forbidden_parameters_in_any_tool_schema() -> None:
    tools = await mcp.list_tools()
    names: set[str] = set()
    for tool in tools:
        schema = tool.inputSchema
        names.update(_iter_property_names(schema))
        dumped = json.dumps(schema)
        assert "owner" not in dumped
        assert "token" not in dumped
        assert "Authorization" not in dumped
    assert names == {
        "params",
        "repo",
        "tag_name",
        "name",
        "body",
        "draft",
        "prerelease",
        "make_latest",
        "generate_release_notes",
        "target_commitish",
        "release_id",
    }
    forbidden = _FORBIDDEN_PARAMETER_NAMES.intersection(names)
    assert not forbidden, forbidden


async def test_run_create_release_logs_and_returns_release(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="github_releases_mcp.server"):
        client = _responding_client(201, {"id": 9, "tag_name": "v1"})
        try:
            params = CreateReleaseInput(repo="coach", tag_name="v1", body=BODY_CANARY)
            output = await run_create_release(client, params)
        finally:
            await client.aclose()
    assert json.loads(output)["id"] == 9
    record = caplog.records[-1]
    assert record.message  # structured line exists
    log_text = caplog.text
    assert SECRET not in log_text
    assert BODY_CANARY not in log_text
    assert '"tool": "create_release"' in log_text
    assert '"repo": "coach"' in log_text
    assert '"tag_name": "v1"' in log_text
    assert '"outcome": "201"' in log_text


async def test_run_update_release_overloaded_returns_sanitized_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="github_releases_mcp.server"):
        client = _responding_client(403, {"message": "Forbidden"})
        try:
            params = UpdateReleaseInput(repo="coach", release_id=11, name=BODY_CANARY)
            output = await run_update_release(client, params)
        finally:
            await client.aclose()
    payload = json.loads(output)
    assert payload == {"status": 403, "github_message": "Forbidden"}
    log_text = caplog.text
    assert SECRET not in log_text
    assert BODY_CANARY not in log_text
    assert '"tool": "update_release"' in log_text
    assert '"release_id": 11' in log_text
    assert '"outcome": "error:403"' in log_text


async def test_sanitized_payload_never_contains_registered_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    utils.register_secret(SECRET)
    with caplog.at_level(logging.INFO, logger="github_releases_mcp.server"):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": f"Bad credentials {SECRET}"})

        client = build_client(SecretStr(SECRET), transport=httpx.MockTransport(handler))
        try:
            output = await run_update_release(
                client, UpdateReleaseInput(repo="coach", release_id=3)
            )
        finally:
            await client.aclose()
    payload = json.loads(output)
    assert SECRET not in json.dumps(payload)
    assert payload["github_message"].endswith("[REDACTED]")
    assert SECRET not in caplog.text


async def test_run_update_release_success_logs_and_returns_release(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="github_releases_mcp.server"):
        client = _responding_client(200, {"id": 12, "tag_name": "v2"})
        try:
            params = UpdateReleaseInput(repo="coach", release_id=12)
            output = await run_update_release(client, params)
        finally:
            await client.aclose()
    assert json.loads(output)["id"] == 12
    log_text = caplog.text
    assert '"tool": "update_release"' in log_text
    assert '"release_id": 12' in log_text
    assert '"outcome": "200"' in log_text


@pytest.mark.parametrize(
    ("runner", "factory"),
    [
        (run_create_release, lambda: CreateReleaseInput(repo="coach", tag_name="v1")),
        (run_update_release, lambda: UpdateReleaseInput(repo="coach", release_id=3)),
    ],
)
async def test_transport_failures_return_sanitized_payload(
    runner: Any,
    factory: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client = build_client(SecretStr(SECRET), transport=httpx.MockTransport(handler))
    try:
        output = await runner(client, factory())
    finally:
        await client.aclose()
    assert json.loads(output) == {"status": 0, "github_message": "ConnectError"}
    assert SECRET not in caplog.text


def test_client_from_context_rejects_bad_lifespan_state() -> None:
    from types import SimpleNamespace

    from github_releases_mcp.server import _client_from_context

    fake_ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context={"client": None})
    )
    with pytest.raises(RuntimeError, match="misconfigured"):
        _client_from_context(fake_ctx)  # type: ignore[arg-type]


async def test_lifespan_loads_token_once_and_builds_client(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN_RELEASES", SECRET)
    with caplog.at_level(logging.INFO):
        try:
            async with app_lifespan(mcp) as state:
                client = state["client"]
                assert str(client.base_url).startswith("https://api.github.com")
                assert "Bearer" in client.headers["Authorization"]
        finally:
            pass
    assert SECRET not in caplog.text


async def test_lifespan_fails_closed_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN_RELEASES", raising=False)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN_RELEASES"):
        async with app_lifespan(mcp) as state:  # noqa: F841 — contextmanager must raise on enter
            _ = state
