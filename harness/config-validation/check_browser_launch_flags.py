#!/usr/bin/env python3
"""Enforce the mandated BROWSER MCP launch flags (#219 AC3, MADR-0009).

The Playwright browser MCP server (``mcp.BROWSER`` in opencode.jsonc) must be
launched with the hardening flags mandated by MADR-0009 (Decision Outcome §2,
as corrected by the #219 post-implementation security re-review):

  ===============================  =========================================
  Flag                             Why it is mandated
  ===============================  =========================================
  ``--isolated``                   Ephemeral in-memory profile — no
                                   cookie/session persistence (#207).
  ``--no-webmcp``                  Pages must not register tools exposed to
                                   the agent (WebMCP tool-poisoning /
                                   indirect prompt injection vector, #219).
  ``--allowed-origins <origins>``  Loopback-origin request allowlist covering
                                   both ``localhost`` and ``127.0.0.1``
                                   (coach-web dev/qa lanes publish
                                   loopback-only; wildcard lane ports).
                                   NOTE: upstream documents this flag as NOT
                                   a security boundary (does not affect
                                   redirects) — the gate pins its presence,
                                   not its enforcement strength (#219).
  ``--output-dir <path>``          Automatically-named output files
                                   (screenshots, session artifacts) are
                                   scoped to a ``/tmp/`` path instead of the
                                   workspace/cwd (#219).
  ===============================  =========================================

Usage: check_browser_launch_flags.py [REPO_ROOT]
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

# Flags that take a value (the element immediately after them in the command
# array). Presence without a value is a misconfiguration and fails the gate.
VALUE_FLAGS = ("--allowed-origins", "--output-dir")

OUTPUT_DIR_PREFIX = "/tmp/"


def strip_jsonc(text: str) -> str:
    """Strip // comments (mirrors the run-config-gate/ci.yml JSONC validator)."""
    out: list[str] = []
    i, in_str, esc = 0, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and text[i + 1 : i + 2] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def browser_command(root: Path) -> tuple[list[str] | None, str | None]:
    """Return the BROWSER command array, or ``(None, error description)``."""
    config = root / "opencode.jsonc"
    rel = config.relative_to(root)
    try:
        data = json.loads(strip_jsonc(config.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"unreadable or invalid JSONC ({exc})"
    mcp = data.get("mcp")
    if not isinstance(mcp, dict) or "BROWSER" not in mcp:
        return None, "missing mcp.BROWSER server entry"
    browser = mcp["BROWSER"]
    if not isinstance(browser, dict):
        return None, "mcp.BROWSER is not an object"
    command = browser.get("command")
    if not isinstance(command, list) or not all(
        isinstance(element, str) for element in command
    ):
        return None, "mcp.BROWSER.command is not an array of strings"
    return command, None


def flag_index(command: list[str], flag: str) -> int:
    """Index of ``flag`` in the command array, or -1 when absent."""
    try:
        return command.index(flag)
    except ValueError:
        return -1


def flag_value(command: list[str], flag: str) -> str | None:
    """Value of a value-taking flag (``None`` when absent or valueless).

    A following element that itself looks like a flag (``--…``) is not a
    value: the flag is then treated as valueless (a misconfiguration).
    """
    index = flag_index(command, flag)
    if index < 0 or index + 1 >= len(command):
        return None
    value = command[index + 1]
    if value.startswith("--"):
        return None
    return value


def loopback_hosts(origins_value: str) -> set[str]:
    """Hosts of a semicolon-separated origin list (lower-cased)."""
    hosts: set[str] = set()
    for origin in origins_value.split(";"):
        origin = origin.strip()
        if not origin:
            continue
        hosts.add((urllib.parse.urlsplit(origin).hostname or "").lower())
    return hosts


def check_browser_flags(root: Path, failures: list[str]) -> None:
    """Assert the mandated launch flags on the mcp.BROWSER command array."""
    config = root / "opencode.jsonc"
    rel = config.relative_to(root)
    command, error = browser_command(root)
    if error is not None or command is None:
        failures.append(f"{rel}: {error}")
        return
    if "--isolated" not in command:
        failures.append(
            f"{rel}: BROWSER command must contain '--isolated' (ephemeral "
            f"in-memory profile, #207/MADR-0009)"
        )
    if "--no-webmcp" not in command:
        failures.append(
            f"{rel}: BROWSER command must contain '--no-webmcp' (pages must "
            f"not register agent-visible tools — WebMCP tool-poisoning "
            f"vector, #219/MADR-0009)"
        )
    origins = flag_value(command, "--allowed-origins")
    if origins is None:
        failures.append(
            f"{rel}: BROWSER command must contain '--allowed-origins' with an "
            f"origin value (loopback request allowlist, #207/MADR-0009)"
        )
    else:
        hosts = loopback_hosts(origins)
        missing = [
            host
            for host in ("localhost", "127.0.0.1")
            if host not in hosts
        ]
        if missing:
            failures.append(
                f"{rel}: '--allowed-origins' value {origins!r} must cover "
                f"loopback hosts localhost and 127.0.0.1 (coach-web dev/qa "
                f"lanes publish loopback-only); missing: {', '.join(missing)}"
            )
    output_dir = flag_value(command, "--output-dir")
    if output_dir is None:
        failures.append(
            f"{rel}: BROWSER command must contain '--output-dir' with a path "
            f"value (scoped output directory, #219/MADR-0009)"
        )
    elif not output_dir.startswith(OUTPUT_DIR_PREFIX):
        failures.append(
            f"{rel}: '--output-dir' value {output_dir!r} must be a scoped "
            f"{OUTPUT_DIR_PREFIX}** path (automatically-named output files "
            f"must land outside the workspace and HOME, #219/MADR-0009)"
        )


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    failures: list[str] = []
    check_browser_flags(root, failures)
    if failures:
        print(
            "FAIL check_browser_launch_flags: mandated BROWSER launch flags "
            "violated:"
        )
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(
        "PASS check_browser_launch_flags: BROWSER command carries the "
        "mandated hardening flags (--isolated, --no-webmcp, loopback "
        "--allowed-origins, scoped --output-dir) — #219/MADR-0009"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
