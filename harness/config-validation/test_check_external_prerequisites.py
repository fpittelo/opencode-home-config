#!/usr/bin/env python3
"""Regression tests for check_external_prerequisites.py (#441, gate 17).

stdlib unittest only: no pytest, no third-party imports, no network. Fixture
cases call ``check_inventory()`` directly against throwaway repo trees
(``opencode.jsonc`` + ``install.sh``) with an explicit inventory, so each
assertion is exercised in isolation; the last case runs the CLI against this
real repository as the positive control.

Why this gate exists (#441, third "unowned external prerequisite" incident:
#416 Podman -> #422 git identity -> #435 Node): a command the config invokes
but nothing verifies is a silent per-session failure. The checker owns the
declared inventory of every external command and fails closed when
  * an ``mcp.*.command`` launcher is not declared (the #435 ``npx`` class),
  * a declared guard does not exist in ``install.sh``,
  * an entry is marked ``unjustified``, or
  * a guarded entry is no longer invoked anywhere (permanent-waiver guard).

Run:
    python3 harness/config-validation/test_check_external_prerequisites.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_external_prerequisites as checker  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "check_external_prerequisites.py"
REPO_ROOT = Path(__file__).resolve().parents[2]


def build_repo(config: str, install: str) -> Path:
    """Materialize a throwaway repo (opencode.jsonc + install.sh)."""
    root = Path(tempfile.mkdtemp())
    (root / "opencode.jsonc").write_text(config, encoding="utf-8")
    (root / "install.sh").write_text(install, encoding="utf-8")
    return root


def config_with(command: list[str], namespace: str = "BROWSER") -> str:
    """JSONC config whose single local MCP server launches ``command``."""
    server = json.dumps({"type": "local", "command": command, "enabled": True})
    return (
        "{\n"
        '  "mcp": {\n'
        "    // fixture comment exercising the JSONC stripper\n"
        f'    "{namespace}": {server}\n'
        "  }\n"
        "}\n"
    )


def entry(tool: str, guard: str, **extra: str) -> dict[str, str]:
    """Inventory entry fixture."""
    return {"tool": tool, "invoked_where": "fixture", "guard": guard, **extra}


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker CLI against a repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


class FixtureTestCase(unittest.TestCase):
    def assert_finding(self, findings: list[str], *fragments: str) -> None:
        self.assertTrue(findings, "expected at least one finding, got none")
        joined = "\n".join(findings)
        for fragment in fragments:
            self.assertIn(fragment, joined)

    def assert_clean(self, findings: list[str]) -> None:
        self.assertEqual(findings, [], f"expected no findings, got: {findings}")


class ConfigCoverage(FixtureTestCase):
    """Assertion 1 — every MCP launcher is declared (the #435 defect class)."""

    def test_declared_and_guarded_launcher_passes(self) -> None:
        root = build_repo(
            config_with(["npx", "-y", "@playwright/mcp@0.0.83"]),
            "#!/usr/bin/env bash\ncommand -v npx >/dev/null 2>&1\n",
        )
        findings = checker.check_inventory(
            root, [entry("npx", checker.GUARD_COMMAND_V)]
        )
        self.assert_clean(findings)

    def test_undeclared_launcher_fails(self) -> None:
        root = build_repo(
            config_with(["npx", "-y", "@playwright/mcp@0.0.83"]),
            "#!/usr/bin/env bash\ncommand -v npx >/dev/null 2>&1\n",
        )
        findings = checker.check_inventory(root, [])
        self.assert_finding(findings, "npx", "not declared")

    def test_absolute_path_launcher_is_reduced_to_its_basename(self) -> None:
        root = build_repo(
            config_with(["{env:HOME}/.local/bin/github-mcp-server", "stdio"], "GITHUB"),
            '#!/usr/bin/env bash\nBIN_PATH="$BIN_DIR/github-mcp-server"\n',
        )
        findings = checker.check_inventory(
            root,
            [entry("github-mcp-server", checker.GUARD_PROVISIONED)],
        )
        self.assert_clean(findings)

    def test_remote_server_without_command_is_ignored(self) -> None:
        config = (
            "{\n"
            '  "mcp": {\n'
            '    "openrouter": {"type": "remote", "url": "https://mcp.example/mcp"}\n'
            "  }\n"
            "}\n"
        )
        root = build_repo(config, "#!/usr/bin/env bash\n")
        findings = checker.check_inventory(root, [])
        self.assert_clean(findings)

    def test_unjustified_launcher_fails(self) -> None:
        """An npx-style launcher declared with no guard must fail (#435)."""
        root = build_repo(
            config_with(["npx", "-y", "@playwright/mcp@0.0.83"]),
            "#!/usr/bin/env bash\n",
        )
        findings = checker.check_inventory(
            root, [entry("npx", checker.GUARD_UNJUSTIFIED)]
        )
        self.assert_finding(findings, "npx", "unjustified")


class GuardExistence(FixtureTestCase):
    """Assertion 2 — a declared guard must exist in install.sh."""

    def test_missing_command_v_guard_fails(self) -> None:
        root = build_repo(
            config_with(["npx", "-y", "@playwright/mcp@0.0.83"]),
            "#!/usr/bin/env bash\necho installing\n",
        )
        findings = checker.check_inventory(
            root, [entry("npx", checker.GUARD_COMMAND_V)]
        )
        self.assert_finding(findings, "npx", "command -v")

    def test_guard_via_runtime_variable_passes(self) -> None:
        install = (
            "#!/usr/bin/env bash\n"
            'CONTAINER_RUNTIME="podman"\n'
            'if ! command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1; then exit 1; fi\n'
            '"$CONTAINER_RUNTIME" pull --policy=missing image\n'
        )
        root = build_repo(config_with(["podman", "run", "-i", "image"]), install)
        findings = checker.check_inventory(
            root,
            [entry("podman", checker.GUARD_COMMAND_V, guard_var="CONTAINER_RUNTIME")],
        )
        self.assert_clean(findings)

    def test_runtime_variable_pointing_elsewhere_fails(self) -> None:
        install = (
            "#!/usr/bin/env bash\n"
            'CONTAINER_RUNTIME="docker"\n'
            'command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1\n'
        )
        root = build_repo(config_with(["podman", "run", "-i", "image"]), install)
        findings = checker.check_inventory(
            root,
            [entry("podman", checker.GUARD_COMMAND_V, guard_var="CONTAINER_RUNTIME")],
        )
        self.assert_finding(findings, "podman", "command -v")

    def test_provisioned_tool_without_install_step_fails(self) -> None:
        root = build_repo(
            config_with(["{env:HOME}/.local/bin/github-mcp-server", "stdio"], "GITHUB"),
            "#!/usr/bin/env bash\n",
        )
        findings = checker.check_inventory(
            root, [entry("github-mcp-server", checker.GUARD_PROVISIONED)]
        )
        self.assert_finding(findings, "github-mcp-server", "provisioned")

    def test_coreutils_allowlist_needs_no_guard(self) -> None:
        root = build_repo(
            config_with(["npx", "-y", "pkg"]),
            "#!/usr/bin/env bash\ncurl -fsSL https://example.invalid\n",
        )
        findings = checker.check_inventory(
            root,
            [
                entry("npx", checker.GUARD_COMMAND_V),
                entry("curl", checker.GUARD_COREUTILS),
            ],
        )
        # npx has no guard line here on purpose: only the coreutil is asserted.
        self.assert_finding(findings, "npx")
        self.assertNotIn("curl", "\n".join(findings))


class StaleInventory(FixtureTestCase):
    """Assertion 3 — a guarded entry must still be invoked somewhere."""

    def test_guarded_but_never_invoked_tool_fails(self) -> None:
        root = build_repo(
            config_with(["npx", "-y", "pkg"]),
            "#!/usr/bin/env bash\n"
            "command -v npx >/dev/null 2>&1\n"
            "command -v podman >/dev/null 2>&1\n",
        )
        findings = checker.check_inventory(
            root,
            [
                entry("npx", checker.GUARD_COMMAND_V),
                entry("podman", checker.GUARD_COMMAND_V),
            ],
        )
        self.assert_finding(findings, "podman", "no longer invoked")

    def test_guard_line_alone_does_not_count_as_invocation(self) -> None:
        root = build_repo(
            config_with(["npx", "-y", "pkg"]),
            "#!/usr/bin/env bash\ncommand -v npx >/dev/null 2>&1\n",
        )
        install = (
            "#!/usr/bin/env bash\n"
            "command -v npx >/dev/null 2>&1\n"
            "command -v openssl >/dev/null 2>&1\n"
        )
        (root / "install.sh").write_text(install, encoding="utf-8")
        findings = checker.check_inventory(
            root,
            [
                entry("npx", checker.GUARD_COMMAND_V),
                entry("openssl", checker.GUARD_COMMAND_V),
            ],
        )
        self.assert_finding(findings, "openssl", "no longer invoked")


class FailClosed(FixtureTestCase):
    """Unreadable inputs are findings, never silent passes."""

    def test_missing_config_fails(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        self.assert_finding(checker.check_inventory(root, []), "opencode.jsonc")

    def test_missing_install_sh_fails(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "opencode.jsonc").write_text(config_with(["npx"]), encoding="utf-8")
        self.assert_finding(
            checker.check_inventory(root, [entry("npx", checker.GUARD_COMMAND_V)]),
            "install.sh",
        )

    def test_invalid_guard_class_fails(self) -> None:
        root = build_repo(
            config_with(["npx"]),
            "#!/usr/bin/env bash\ncommand -v npx >/dev/null 2>&1\n",
        )
        findings = checker.check_inventory(root, [entry("npx", "best-effort")])
        self.assert_finding(findings, "npx", "unknown guard")


class RealRepositoryControl(unittest.TestCase):
    """Positive control: today's fleet is fully classified."""

    def test_real_repo_passes(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        self.assertIn("PASS check_external_prerequisites", proc.stdout)

    def test_every_real_mcp_launcher_is_declared(self) -> None:
        declared = {item["tool"] for item in checker.INVENTORY}
        for launcher in checker.mcp_launchers(REPO_ROOT):
            with self.subTest(launcher=launcher):
                self.assertIn(launcher, declared)

    def test_git_identity_guard_is_inventoried(self) -> None:
        """#422: install.sh now invokes git — the inventory must say so."""
        entries = {item["tool"]: item for item in checker.INVENTORY}
        self.assertIn(
            "git",
            entries,
            "install.sh invokes git for the identity guard (#422) — declare it "
            "in the external-prerequisite inventory",
        )
        self.assertEqual(entries["git"]["guard"], checker.GUARD_COMMAND_V)
        self.assertNotIn(
            "guard_var",
            entries["git"],
            "git is guarded by the literal 'command -v git' line, not a token",
        )


if __name__ == "__main__":
    unittest.main()
