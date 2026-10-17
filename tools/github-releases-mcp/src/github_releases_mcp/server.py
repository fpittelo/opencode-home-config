"""FastMCP stdio server exposing the GITHUB_RELEASES tool pair (MADR-0016).

Exactly two tools (condition 8): ``create_release`` (POST on
``/repos/fpittelo/{repo}/releases``) and ``update_release`` (PATCH on
``/repos/fpittelo/{repo}/releases/{release_id}``). The credential is read
once at startup from ``GITHUB_TOKEN_RELEASES`` (condition 7); tool calls are
logged with a structured, secret-free record ({tool, repo, tag_name,
release_id, outcome} — never the token, never release body text) and every
error path returns a sanitized ``{status, github_message}`` payload.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from github_releases_mcp import client as api
from github_releases_mcp import utils
from github_releases_mcp.models import CreateReleaseInput, UpdateReleaseInput

_LOGGER = logging.getLogger(__name__)

CREATE_SUCCESS_STATUS = "201"
UPDATE_SUCCESS_STATUS = "200"


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Load the credential once and hold one pinned API client per session."""
    _ = server
    token = api.load_releases_token()
    utils.register_secret(token.get_secret_value())
    async with api.build_client(token) as client:
        yield {"client": client}


mcp = FastMCP(
    name="github_releases_mcp",
    instructions=(
        "GITHUB_RELEASES — home-grown GitHub release-write server "
        "(MADR-0016). Creates and updates GitHub Release objects under the "
        "pinned @fpittelo account. Errors are returned as sanitized "
        "{status, github_message} payloads."
    ),
    lifespan=app_lifespan,
)


def _log_call(
    tool: str,
    repo: str,
    *,
    tag_name: str | None = None,
    release_id: int | None = None,
    outcome: str,
) -> None:
    """Emit the repudiation-control record; token and body text never enter."""
    entry: dict[str, Any] = {
        "tool": tool,
        "repo": repo,
        "tag_name": tag_name,
        "release_id": release_id,
        "outcome": outcome,
    }
    structured = json.dumps(
        {key: value for key, value in entry.items() if value is not None},
        sort_keys=True,
    )
    _LOGGER.info("%s", structured)


def _client_from_context(ctx: Context) -> httpx.AsyncClient:
    """Retrieve the pinned client from the FastMCP lifespan state."""
    client = ctx.request_context.lifespan_context["client"]
    if not isinstance(client, httpx.AsyncClient):
        raise RuntimeError("GITHUB_RELEASES lifespan state is misconfigured")
    return client


async def run_create_release(
    client: httpx.AsyncClient,
    params: CreateReleaseInput,
) -> str:
    """Execute the create tool body: API call, logging, sanitized errors."""
    tag_name = params.tag_name
    try:
        release = await api.create_release(client, params)
    except api.ReleasesAPIError as error:
        _log_call(
            "create_release",
            params.repo,
            tag_name=tag_name,
            outcome=f"error:{error.payload['status']}",
        )
        return json.dumps(error.payload)
    except httpx.HTTPError as error:
        _log_call("create_release", params.repo, tag_name=tag_name, outcome="error")
        sanitized = await _transport_error_payload(error)
        return json.dumps(sanitized)
    release_id = release.get("id")
    _log_call(
        "create_release",
        params.repo,
        tag_name=tag_name,
        release_id=release_id if isinstance(release_id, int) else None,
        outcome=CREATE_SUCCESS_STATUS,
    )
    return json.dumps(release)


async def run_update_release(
    client: httpx.AsyncClient,
    params: UpdateReleaseInput,
) -> str:
    """Execute the update tool body: API call, logging, sanitized errors."""
    tag_name = params.tag_name
    try:
        release = await api.update_release(client, params)
    except api.ReleasesAPIError as error:
        _log_call(
            "update_release",
            params.repo,
            tag_name=tag_name,
            release_id=params.release_id,
            outcome=f"error:{error.payload['status']}",
        )
        return json.dumps(error.payload)
    except httpx.HTTPError as error:
        _log_call(
            "update_release",
            params.repo,
            tag_name=tag_name,
            release_id=params.release_id,
            outcome="error",
        )
        sanitized = await _transport_error_payload(error)
        return json.dumps(sanitized)
    _log_call(
        "update_release",
        params.repo,
        tag_name=tag_name,
        release_id=params.release_id,
        outcome=UPDATE_SUCCESS_STATUS,
    )
    return json.dumps(release)


async def _transport_error_payload(error: httpx.HTTPError) -> dict[str, str | int]:
    """Sanitized payload for failures before any HTTP response existed."""
    status_zero = 0
    return {
        "status": status_zero,
        "github_message": utils.sanitize_error(status_zero, type(error).__name__)[
            "github_message"
        ],
    }


@mcp.tool(
    name="create_release",
    annotations=ToolAnnotations(
        title="Create a GitHub release",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def create_release(params: CreateReleaseInput, ctx: Context) -> str:
    """Create a GitHub Release object for a repository of the pinned account.

    Args:
        params (CreateReleaseInput): Validated release fields (tag_name
            required; name, body, draft, prerelease, make_latest,
            generate_release_notes, target_commitish optional).
        ctx (Context): Server context providing the pinned API client.

    Returns:
        str: JSON document of the created release, or a sanitized
        {status, github_message} error payload.
    """
    return await run_create_release(_client_from_context(ctx), params)


@mcp.tool(
    name="update_release",
    annotations=ToolAnnotations(
        title="Update a GitHub release",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def update_release(params: UpdateReleaseInput, ctx: Context) -> str:
    """Update an existing GitHub Release object by release id.

    Only explicitly provided fields are sent in the PATCH body; absent
    fields keep their current values on GitHub.

    Args:
        params (UpdateReleaseInput): Validated fields (release_id required;
            every other field optional and sent only when provided).
        ctx (Context): Server context providing the pinned API client.

    Returns:
        str: JSON document of the updated release, or a sanitized
        {status, github_message} error payload.
    """
    return await run_update_release(_client_from_context(ctx), params)


def main() -> None:
    """Run the FastMCP server over stdio (the opencode.jsonc entrypoint)."""
    mcp.run()


if __name__ == "__main__":
    main()
