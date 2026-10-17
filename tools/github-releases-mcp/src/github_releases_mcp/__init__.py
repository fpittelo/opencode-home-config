"""GITHUB_RELEASES — home-grown FastMCP server for agent-side GitHub release
publishing (MADR-0016, issue #323).

Exposes exactly two tools over stdio (``create_release`` and
``update_release``) against the GitHub REST releases API, with the owner
hard-pinned to ``fpittelo``. Package layout follows the fastmcp-builder house
skill: ``models`` (Pydantic v2 input schemas), ``client`` (pinned httpx
transport), ``server`` (FastMCP app), ``utils`` (error sanitization).
"""
