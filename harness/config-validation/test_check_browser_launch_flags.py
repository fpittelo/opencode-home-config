#!/usr/bin/env python3
"""Regression tests for check_browser_launch_flags.py (#219 AC3, MADR-0009).

stdlib unittest only: no pytest, no third-party imports. Each case runs the
checker as a subprocess against a throwaway repository tree (tempfile), so
exit codes and failure context are covered end to end.

The checker enforces the mandated BROWSER MCP launch flags on the
``mcp.BROWSER.command`` array of opencode.jsonc (MADR-0009 Decision Outcome
§2, as corrected by #219): ``--isolated``, ``--no-webmcp``, an
``--allowed-origins`` value covering both loopback hosts (localhost and
127.0.0.1), and an ``--output-dir`` value scoped under /tmp/.

Negative cases cover each mandated flag and each value-shape defect; a
positive control pins the real repository state (the subject of the
run-config-gate.sh launch-flag gate and its ci.yml twin). The real-repo
control is the RED→GREEN vehicle for #219 AC3: before the config fix it
fails because ``--no-webmcp`` is missing.

Run:
    python3 harness/config-validation/test_check_browser_launch_flags.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_browser_launch_flags.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

# The mandated minimum launch configuration (advisory flags such as
# --block-service-workers are deliberately absent: the gate pins the
# mandated set, not the advisory set).
VALID_COMMAND = [
    "npx", "-y", "@playwright/mcp@0.0.83",
    "--isolated",
    "--no-webmcp",
    "--allowed-origins", "http://localhost:*;http://127.0.0.1:*",
    "--output-dir", "/tmp/opencode/playwright-output",
]


def config_text(command: list[str] | None) -> str:
    """Minimal opencode.jsonc carrying the given BROWSER command array."""
    if command is None:
        browser = '{"type": "local", "enabled": true}'
    else:
        browser = json.dumps({"type": "local", "command": command, "enabled": True})
    return (
        "{\n"
        '  "mcp": {\n'
        "    // fixture comment exercising the JSONC stripper\n"
        f'    "BROWSER": {browser}\n'
        "  }\n"
        "}\n"
    )


def build_repo(config: str) -> Path:
    """Materialize a throwaway repo (opencode.jsonc only) and return it."""
    root = Path(tempfile.mkdtemp())
    (root / "opencode.jsonc").write_text(config, encoding="utf-8")
    return root


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker CLI against a repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


class BrowserLaunchFlagTests(unittest.TestCase):
    """Negative/positive cases for the mandated launch-flag invariant."""

    def assert_gate_fails(
        self, proc: subprocess.CompletedProcess[str], *fragments: str
    ) -> None:
        output = proc.stdout + proc.stderr
        self.assertEqual(
            proc.returncode,
            1,
            f"expected exit 1, got {proc.returncode}:\n{output}",
        )
        for fragment in fragments:
            self.assertIn(fragment, output)

    def test_valid_fixture_passes(self) -> None:
        proc = run_checker(build_repo(config_text(VALID_COMMAND)))
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_valid_fixture_origin_order_independent(self) -> None:
        command = list(VALID_COMMAND)
        index = command.index("--allowed-origins")
        command[index + 1] = "http://127.0.0.1:*;http://localhost:*"
        proc = run_checker(build_repo(config_text(command)))
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_missing_mandatory_flag_fails(self) -> None:
        for flag in ("--isolated", "--no-webmcp"):
            with self.subTest(flag=flag):
                command = [element for element in VALID_COMMAND if element != flag]
                proc = run_checker(build_repo(config_text(command)))
                self.assert_gate_fails(proc, flag, "must contain")

    def test_missing_allowed_origins_flag_fails(self) -> None:
        command = [
            element
            for element in VALID_COMMAND
            if element not in ("--allowed-origins", "http://localhost:*;http://127.0.0.1:*")
        ]
        proc = run_checker(build_repo(config_text(command)))
        self.assert_gate_fails(proc, "--allowed-origins", "must contain")

    def test_allowed_origins_without_loopback_ip_fails(self) -> None:
        command = list(VALID_COMMAND)
        index = command.index("--allowed-origins")
        command[index + 1] = "http://localhost:*"
        proc = run_checker(build_repo(config_text(command)))
        self.assert_gate_fails(proc, "127.0.0.1", "must cover")

    def test_allowed_origins_without_localhost_fails(self) -> None:
        command = list(VALID_COMMAND)
        index = command.index("--allowed-origins")
        command[index + 1] = "http://127.0.0.1:*"
        proc = run_checker(build_repo(config_text(command)))
        self.assert_gate_fails(proc, "localhost", "must cover")

    def test_allowed_origins_without_value_fails(self) -> None:
        command = list(VALID_COMMAND)
        index = command.index("--allowed-origins")
        del command[index + 1]
        proc = run_checker(build_repo(config_text(command)))
        self.assert_gate_fails(proc, "--allowed-origins", "must contain")

    def test_missing_output_dir_fails(self) -> None:
        command = [
            element
            for element in VALID_COMMAND
            if element not in ("--output-dir", "/tmp/opencode/playwright-output")
        ]
        proc = run_checker(build_repo(config_text(command)))
        self.assert_gate_fails(proc, "--output-dir", "must contain")

    def test_output_dir_outside_tmp_fails(self) -> None:
        command = list(VALID_COMMAND)
        index = command.index("--output-dir")
        command[index + 1] = "/home/frede/playwright-output"
        proc = run_checker(build_repo(config_text(command)))
        self.assert_gate_fails(proc, "/home/frede/playwright-output", "scoped")

    def test_output_dir_without_value_fails(self) -> None:
        command = list(VALID_COMMAND)
        index = command.index("--output-dir")
        del command[index + 1]
        proc = run_checker(build_repo(config_text(command)))
        self.assert_gate_fails(proc, "--output-dir", "must contain")

    def test_missing_browser_server_fails(self) -> None:
        proc = run_checker(build_repo('{\n  "mcp": {}\n}\n'))
        self.assert_gate_fails(proc, "missing mcp.BROWSER server entry")

    def test_browser_server_without_command_fails(self) -> None:
        proc = run_checker(build_repo(config_text(None)))
        self.assert_gate_fails(proc, "not an array of strings")

    def test_command_not_a_list_fails(self) -> None:
        proc = run_checker(
            build_repo(
                "{\n"
                '  "mcp": {\n'
                '    "BROWSER": {"type": "local", "command": "npx -y"}\n'
                "  }\n"
                "}\n"
            )
        )
        self.assert_gate_fails(proc, "not an array of strings")

    def test_invalid_jsonc_fails(self) -> None:
        proc = run_checker(build_repo("{ not jsonc }"))
        self.assert_gate_fails(proc, "unreadable or invalid JSONC")


class RealRepositoryTests(unittest.TestCase):
    """Positive control: the real repository satisfies the invariant."""

    def test_real_repo_satisfies_launch_flag_invariant(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
