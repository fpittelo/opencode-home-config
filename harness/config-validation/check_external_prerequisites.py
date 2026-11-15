#!/usr/bin/env python3
"""Fail-closed external-prerequisite inventory checker (#441, gate 17).

Third "unowned external prerequisite" incident (#416 Podman → #422 git
identity → #435 Node) exposed the systemic gap: a command that ``install.sh`` or
an MCP server depends on could be missing on a host with **nothing** failing at
PR time — the absence only surfaced mid-session. This checker owns the declared
inventory of every external command the config invokes and validates it against
the two files that define the fleet (``install.sh``, ``opencode.jsonc``).

Guard classes (``INVENTORY`` is the single source of truth):

  ``command -v``          Host-provided runtime the script cannot provision
                          (``sudo`` is denied by the bash posture): must have a
                          matching ``command -v <tool>`` guard line. A guard
                          through a runtime token (``command -v
                          "$CONTAINER_RUNTIME"``) is accepted when the token is
                          assigned the same tool name — ``guard_var`` records it,
                          so a switch to another runtime fails the gate (#416).
  ``provisioned``         Owned artifact the script downloads, verifies and
                          installs itself (``github-mcp-server``): the install
                          provenance line (``$BIN_DIR/<tool>``) is the guard —
                          a ``command -v`` guard would be theatre, since the
                          script creates the binary it would look for.
  ``coreutils-allowlist`` OS/coreutils assumed present by every shell contract;
                          classified, never individually guarded (no per-tool
                          waiver to go stale).
  ``unjustified``         Explicitly unguarded — always a finding.

Assertions:
  1. Config coverage — every ``mcp.<ns>.command[0]`` launcher is declared
     (the #435 ``npx`` class: an unguarded launcher fails the gate).
  2. Guard existence — a declared guard must exist in ``install.sh``.
  3. Stale inventory — a guarded tool that is no longer invoked anywhere is a
     finding, so entries cannot become permanent waivers.

Out of scope by design: parsing arbitrary bash beyond the simple
``command -v <tool>`` guard-line match — the checker validates the declared
inventory, it is not a shell parser.

Usage: check_external_prerequisites.py [REPO_ROOT]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence

from jsonc_utils import strip_jsonc

GUARD_COMMAND_V = "command -v"
GUARD_COREUTILS = "coreutils-allowlist"
GUARD_PROVISIONED = "provisioned"
GUARD_UNJUSTIFIED = "unjustified"
GUARD_CLASSES = frozenset(
    {GUARD_COMMAND_V, GUARD_COREUTILS, GUARD_PROVISIONED, GUARD_UNJUSTIFIED}
)

# The inventory of every external command this configuration invokes.
# Classified from install.sh + opencode.jsonc (verified 2026-11-15, #441).
INVENTORY: tuple[Mapping[str, str], ...] = (
    {
        "tool": "github-mcp-server",
        "invoked_where": "opencode.jsonc mcp.GITHUB* command[0] (3 servers)",
        "guard": GUARD_PROVISIONED,
    },
    {
        "tool": "npx",
        "invoked_where": "opencode.jsonc mcp.BROWSER command[0] (Node runtime)",
        "guard": GUARD_COMMAND_V,
    },
    {
        "tool": "node",
        "invoked_where": "install.sh BROWSER runtime guard (npx needs it, #435)",
        "guard": GUARD_COMMAND_V,
    },
    {
        "tool": "openssl",
        "invoked_where": "install.sh @playwright/mcp tarball SHA512 verification",
        "guard": GUARD_COMMAND_V,
    },
    {
        "tool": "git",
        "invoked_where": "install.sh git identity guard (user.name/user.email, #422)",
        "guard": GUARD_COMMAND_V,
    },
    {
        "tool": "podman",
        "invoked_where": "opencode.jsonc mcp.COACH_* command[0]; install.sh pre-pull",
        "guard": GUARD_COMMAND_V,
        "guard_var": "CONTAINER_RUNTIME",
    },
    {
        "tool": "awk",
        "invoked_where": "install.sh checksums parsing + legacy rc-block removal",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "cat",
        "invoked_where": "install.sh secrets template + scratch-file writes",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "chmod",
        "invoked_where": "install.sh secrets-file modes + config-dir hardening",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "curl",
        "invoked_where": "install.sh pinned binary/registry downloads (3 call sites)",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "find",
        "invoked_where": "install.sh fail-closed world-readable-secrets assertion",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "grep",
        "invoked_where": "install.sh installed-version, rc-file and secrets checks",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "install",
        "invoked_where": "install.sh binary placement + secrets-file modes",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "ln",
        "invoked_where": "install.sh config/agents/skills symlinks",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "mkdir",
        "invoked_where": "install.sh config/bin directory creation",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "mktemp",
        "invoked_where": "install.sh temp workspace + scratch files",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "rm",
        "invoked_where": "install.sh temp cleanup + retired-file removal",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "sed",
        "invoked_where": "install.sh herdr version regex + legacy rc-file edits",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "sha256sum",
        "invoked_where": "install.sh artifact SHA256 verification (2 call sites)",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "systemctl",
        "invoked_where": "install.sh legacy systemd user-env scrub + verification",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "tar",
        "invoked_where": "install.sh github-mcp-server archive extraction",
        "guard": GUARD_COREUTILS,
    },
    {
        "tool": "uname",
        "invoked_where": "install.sh Linux/x86_64 platform guard",
        "guard": GUARD_COREUTILS,
    },
)


def mcp_launchers(root: Path) -> list[str]:
    """Basenames of every local ``mcp.*.command[0]`` launcher (#435 class).

    Remote servers (``url``-only) spawn no process and are skipped. Absolute or
    ``{env:HOME}``-interpolated paths (``.../.local/bin/github-mcp-server``) are
    reduced to the binary name, which is what the inventory keys on.
    """
    config = root / "opencode.jsonc"
    data = json.loads(strip_jsonc(config.read_text(encoding="utf-8")))
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        raise ValueError("missing mcp block")
    launchers: list[str] = []
    for server in mcp.values():
        if not isinstance(server, dict):
            continue
        command = server.get("command")
        if not isinstance(command, list) or not command:
            continue
        first = command[0]
        if isinstance(first, str) and first:
            launchers.append(Path(first).name)
    return launchers


def _code_lines(text: str) -> list[str]:
    """install.sh lines excluding whole-line comments (not a shell parser)."""
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def _has_command_v_guard(
    lines: Sequence[str], tool: str, guard_var: str | None
) -> bool:
    """True when a ``command -v`` guard for ``tool`` exists in install.sh."""
    direct = re.compile(rf"command\s+-v\s+{re.escape(tool)}(?![-\w])")
    if any(direct.search(line) for line in lines):
        return True
    if guard_var is None:
        return False
    indirect = re.compile(
        rf'command\s+-v\s+"\$(?:\{{{re.escape(guard_var)}\}}|{re.escape(guard_var)})"'
    )
    assignment = re.compile(rf'^\s*{re.escape(guard_var)}="?{re.escape(tool)}"?\s*$')
    return any(indirect.search(line) for line in lines) and any(
        assignment.match(line) for line in lines
    )


def _has_provision_step(lines: Sequence[str], tool: str) -> bool:
    """True when install.sh installs ``tool`` into ``$BIN_DIR`` itself."""
    marker = f'"$BIN_DIR/{tool}"'
    return any(marker in line for line in lines)


def _invoked(lines: Sequence[str], tool: str) -> bool:
    """True when a non-comment install.sh line uses ``tool`` beyond its guard."""
    guard = re.compile(
        rf"command\s+-v\s+(?:\"?\$(?:\{{?\w+\}}?)?)?{re.escape(tool)}(?![-\w])"
    )
    usage = re.compile(rf"(?<![-\w]){re.escape(tool)}(?![-\w])")
    return any(
        not guard.search(line) and usage.search(line) is not None for line in lines
    )


def check_inventory(root: Path, inventory: Sequence[Mapping[str, str]]) -> list[str]:
    """Validate the declared inventory against a repository tree."""
    findings: list[str] = []
    config = root / "opencode.jsonc"
    install = root / "install.sh"
    try:
        launchers = mcp_launchers(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        findings.append(f"{config.name}: unreadable or invalid ({exc})")
        launchers = []
    try:
        lines = _code_lines(install.read_text(encoding="utf-8"))
    except OSError as exc:
        findings.append(f"{install.name}: unreadable ({exc})")
        return findings

    declared = {item.get("tool"): item for item in inventory}

    # Assertion 1 — every config launcher is declared (guard-class validity and
    # the unjustified case are reported once, by the inventory loop below).
    for launcher in launchers:
        if launcher not in declared:
            findings.append(
                f"{config.name}: launcher {launcher!r} is not declared in the "
                f"external-prerequisite inventory (#435: an unowned launcher "
                f"fails silently per session)"
            )

    # Assertions 2 and 3 — guard existence and stale entries.
    for item in inventory:
        tool = str(item.get("tool", ""))
        guard = item.get("guard")
        if guard not in GUARD_CLASSES:
            findings.append(
                f"inventory: {tool!r} has unknown guard {guard!r} (expected one "
                f"of {sorted(GUARD_CLASSES)})"
            )
            continue
        if guard == GUARD_UNJUSTIFIED:
            findings.append(
                f"inventory: {tool!r} is declared {GUARD_UNJUSTIFIED!r} — an "
                f"unguarded external prerequisite is a finding, never a waiver"
            )
            continue
        if guard == GUARD_COREUTILS:
            continue
        if guard == GUARD_COMMAND_V and not _has_command_v_guard(
            lines, tool, item.get("guard_var")
        ):
            variable = (
                f'command -v "${item["guard_var"]}" '
                f'({item["guard_var"]}="{tool}")'
                if item.get("guard_var")
                else f"command -v {tool}"
            )
            findings.append(
                f"{install.name}: {tool!r} is declared guarded but no "
                f"{variable} guard line exists (fail-closed prerequisite, #441)"
            )
            continue
        if guard == GUARD_PROVISIONED and not _has_provision_step(lines, tool):
            findings.append(
                f"{install.name}: {tool!r} is declared provisioned but no "
                f'"$BIN_DIR/{tool}" install step exists (#441)'
            )
            continue
        if tool not in launchers and not _invoked(lines, tool):
            findings.append(
                f"inventory: {tool!r} is declared {guard!r} but is no longer "
                f"invoked by install.sh or opencode.jsonc — stale entry "
                f"(delete it or re-classify, #441)"
            )
    return findings


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    findings = check_inventory(root, INVENTORY)
    if findings:
        print("FAIL check_external_prerequisites: inventory violated:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    guarded = sum(
        1 for item in INVENTORY if item["guard"] in {GUARD_COMMAND_V, GUARD_PROVISIONED}
    )
    print(
        f"PASS check_external_prerequisites: {len(INVENTORY)} external commands "
        f"classified ({guarded} guarded, "
        f"{len(INVENTORY) - guarded} OS/coreutils allowlisted), every MCP "
        f"launcher declared, no stale entries — #441"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
