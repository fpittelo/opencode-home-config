# TDD regression suite for the github-mcp-server supply-chain pin (#310).
#
# Guards the three drift surfaces between the install.sh pin, the installed
# binary, and the opencode.jsonc documentation comments:
#   (a) install.sh declares exactly one GITHUB_MCP_VERSION assignment — the
#       pin must stay single-sourced;
#   (b) the binary installed at $HOME/.local/bin/github-mcp-server, when
#       present, reports the pinned version (body skipped on hosts without
#       the installed binary, e.g. CI runners);
#   (c) every X.Y.Z-shaped version literal in opencode.jsonc MCP comment
#       lines containing "pinned" or "v<digit>" matches the install.sh pin,
#       so the documented toolset claims cannot drift from the pin again.
#
# stdlib unittest only, < 1 s, no network.

from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
OPENCODE_JSONC = REPO_ROOT / "opencode.jsonc"

PIN_ASSIGNMENT_RE = re.compile(r'^GITHUB_MCP_VERSION="(\d+\.\d+\.\d+)"', re.MULTILINE)
VERSION_LITERAL_RE = re.compile(r"\d+\.\d+\.\d+")


def pinned_version() -> str:
    """Return the single GITHUB_MCP_VERSION pin declared by install.sh."""
    matches = PIN_ASSIGNMENT_RE.findall(INSTALL_SH.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise AssertionError(
            "install.sh must declare exactly one GITHUB_MCP_VERSION "
            f"assignment, found {len(matches)}: {matches}"
        )
    return matches[0]


def mcp_block_comment_lines() -> list[str]:
    """Return the // comment lines inside the opencode.jsonc "mcp" block.

    The block spans from the '"mcp": {' line to its closing '  },' at
    two-space indent (nested object closes are indented deeper).
    """
    lines = OPENCODE_JSONC.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith('"mcp"')),
        None,
    )
    assert start is not None, 'opencode.jsonc must contain an "mcp" block'
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^  },\s*$", lines[i])),
        None,
    )
    assert end is not None, 'the "mcp" block closing brace must be present'
    return [
        lines[i] for i in range(start, end) if lines[i].lstrip().startswith("//")
    ]


class TestInstallPin(unittest.TestCase):
    def test_exactly_one_github_mcp_version_assignment(self) -> None:
        """install.sh must single-source the pin in one GITHUB_MCP_VERSION line."""
        matches = PIN_ASSIGNMENT_RE.findall(INSTALL_SH.read_text(encoding="utf-8"))
        self.assertEqual(
            len(matches),
            1,
            "install.sh must declare exactly one GITHUB_MCP_VERSION assignment "
            f"(single-sourced pin, #310); found {len(matches)}: {matches}",
        )


class TestInstalledBinary(unittest.TestCase):
    def test_installed_binary_reports_pinned_version(self) -> None:
        """The installed binary, when present, must report the pinned version."""
        pin = pinned_version()
        binary = Path(os.environ.get("HOME", "")) / ".local" / "bin" / "github-mcp-server"
        if not binary.is_file():
            self.skipTest(
                "github-mcp-server not installed at $HOME/.local/bin "
                "(e.g. CI runner) — nothing to verify"
            )
        result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertIn(
            f"Version: {pin}",
            result.stdout,
            f"installed {binary} reports {result.stdout.strip()!r} but install.sh "
            f"pins {pin} — re-run install.sh to update the binary (#310)",
        )


class TestCommentDrift(unittest.TestCase):
    def test_mcp_comment_version_literals_match_pin(self) -> None:
        """Version literals in pinned/v-citing MCP comments must equal the pin."""
        pin = pinned_version()
        offenders: list[str] = []
        for line in mcp_block_comment_lines():
            if "pinned" in line or re.search(r"v\d", line):
                for literal in VERSION_LITERAL_RE.findall(line):
                    if literal != pin:
                        offenders.append(f"{literal} in: {line.strip()}")
        self.assertEqual(
            offenders,
            [],
            "opencode.jsonc MCP comments cite versions that differ from the "
            f"install.sh pin {pin} — update the comments with the pin (#310):\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
