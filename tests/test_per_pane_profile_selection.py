# TDD validation suite for dual-profile coexistence and per-pane secrets
# isolation (issue #244).
#
# Covers the acceptance criteria AC1-AC8 and the mandatory controls MC1-MC10
# from the STRIDE threat model (#253):
#   - AC1/MC1: install.sh provisions profiles.sh defining oc-home (subshell +
#     set -a/set +a + exec, prefix-assignment, no export); re-running does not
#     duplicate the rc-file source line.
#   - MC3/F9: convergence invariant — updating oc-home must never clobber the
#     oc-work() function installed by the WORK profile installer.
#   - AC3/MC2/MC9: secrets split — .secrets-home.env (mode 600, umask 077),
#     shared .secrets.env retired (migrated then removed), .bashrc AND
#     .profile cleanup, systemd secret-var import retired (unset + verify).
#   - AC4/MC6: legacy /AI_OS_ROOT switcher dead code removed idempotently.
#   - MC9: ~/.config/opencode hardened to 700; fail-closed permission
#     assertion on .secrets-*.env files.
#   - AC7/MC5: MADR-0010 decision record (per-pane env-based selection vs
#     symlink flipping) with explicit PO risk-acceptance for shared provider
#     OAuth tokens; indexed in docs/adr/README.md and arc42 §9.
#   - MC7: arc42 §11 documents the same-UID /proc/<pid>/environ residual.
#   - AC6/MC8: README dual-profile sections (oc-home/oc-work, wrapper
#     semantics, merge caveat, bare-opencode-unsupported notice, Herdr usage).
#   - MC10: .gitignore covers .secrets-home.env.
#
# LIVE-HOST SAFETY: every behavioral test runs install.sh against a
# SANDBOXED fake $HOME with stubbed systemctl (no systemd user session),
# docker, curl, openssl, and pinned-binary version spies — never the real
# home directory, never the real systemd user environment, never the
# network. No real secrets are used anywhere in this suite.

from __future__ import annotations

import os
import re
import stat
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"
ADR_DIR = REPO_ROOT / "docs" / "adr"
ARC42_DIR = REPO_ROOT / "docs" / "architecture" / "arc42"
README_PATH = REPO_ROOT / "README.md"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

HOME_REPO_DIRNAME = "opencode-home-config"
HOME_SECRETS_NAME = ".secrets-home.env"

# Pinned-artifact values from install.sh the stubs must satisfy so the
# sandboxed runs take the "already installed / verified" skip paths instead
# of touching the network.
GITHUB_MCP_VERSION = "1.12.2"
PLAYWRIGHT_MCP_DIGEST = "oNcl+Ae2/IAjhfPeP46BfIkSakfmprY+aOtkv5MjrQ4lPav4/yNtPhL0iq8SlIM90oApWgBDUxaNKvktazUKOg=="

# The live legacy switcher block (uncommented variant, references
# /AI_OS_ROOT) — mirrors the real VIDAR .bashrc layout.
LEGACY_SWITCHER_BLOCK = """\
# ==========================================
# OPENCODE UNIFIED STORAGE & PROFILE MANAGER
# ==========================================

function opencode-switch-context() {
    local CONFIG_ROOT="/AI_OS_ROOT/CONFIGS/OPENCODE"
    local DEST="$HOME/.config/opencode"

    # Clean the old connections
    mkdir -p "$DEST"
    rm -rf "$DEST/opencode.jsonc" "$DEST/agents" "$DEST/skills"

    if [ "$1" == "home" ]; then
        ln -sf $CONFIG_ROOT/profiles/profile.vidar-home.jsonc $DEST/opencode.jsonc
        echo "🟢 Switched to HOME context"

    elif [ "$1" == "work" ]; then
        ln -sf $CONFIG_ROOT/profiles/profile.vidar-work.jsonc $DEST/opencode.jsonc
        echo "🏢 Switched to WORK context"
    fi
}

# Quick Status Checker
function opencode-status() {
    local target=$(readlink $HOME/.config/opencode/opencode.jsonc)

    if [[ "$target" == *"pro-work"* ]]; then
        echo "🏢 ACTIVE PROFILE: OFFICE WORK ($target)"
    else
        echo "⚠️  NO PROFILE LINKED"
    fi
}
"""

# Commented-out variant (defensive: also removed if encountered).
LEGACY_SWITCHER_BLOCK_COMMENTED = "\n".join(
    f"# {line}" if line.strip() else line for line in LEGACY_SWITCHER_BLOCK.splitlines()
)

OLD_SECRETS_SOURCE_LINE = (
    "[ -f $HOME/.config/opencode/.secrets.env ] "
    "&& source $HOME/.config/opencode/.secrets.env"
)

OC_WORK_BLOCK = """\
# profiles.sh — per-pane profile selection for the WORK profile (issue #177).
# Sourced from .bashrc/.profile. Shell functions only; secrets are never
# exported into the pane shell.
oc-work() {
    (
        set -a
        if [ -f "$HOME/.config/opencode/.secrets-work.env" ]; then
            # shellcheck disable=SC1090
            source "$HOME/.config/opencode/.secrets-work.env"
        fi
        set +a
        OPENCODE_CONFIG="$HOME/projects/opencode-work-config/opencode.jsonc" \\
        OPENCODE_CONFIG_DIR="$HOME/projects/opencode-work-config" \\
            exec opencode "$@"
    )
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_home(tmp_path: Path) -> Path:
    """Create a sandboxed fake $HOME directory."""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    return fake_home


def _install_stubs(fake_home: Path) -> Path:
    """Install stub executables so install.sh never touches the network,
    the real systemd user session, or the real docker daemon.

    - systemctl: exits 1 → install.sh takes its guarded no-systemd path.
    - docker: exits 0 → the coach image pre-pull is a no-op.
    - curl: creates the requested output file (empty) instead of downloading.
    - openssl: prints the pinned @playwright/mcp digest (base64 subcommand
      passes stdin through, mirroring the dgst | base64 pipe).
    - github-mcp-server / herdr: version spies matching the pinned versions
      so the binary-install blocks take their idempotent skip paths.
    """
    stub_bin = fake_home / ".stub-bin"
    stub_bin.mkdir(exist_ok=True)

    def stub(name: str, body: str) -> None:
        path = stub_bin / name
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o755)

    stub("systemctl", "#!/bin/sh\nexit 1\n")
    stub("docker", "#!/bin/sh\nexit 0\n")
    stub(
        "curl",
        '#!/bin/sh\nout=""\nwhile [ $# -gt 0 ]; do\n'
        '  case "$1" in -o) out="$2"; shift 2;; *) shift;; esac\ndone\n'
        ': > "$out"\n',
    )
    stub(
        "openssl",
        '#!/bin/sh\ncase "$*" in\n'
        f"  *base64*) cat ;;\n  *) echo '{PLAYWRIGHT_MCP_DIGEST}' ;;\nesac\n",
    )
    # Version spies live in $HOME/.local/bin (where install.sh checks for the
    # pinned binaries), so both install blocks take their idempotent skip
    # paths and never download anything.
    local_bin = fake_home / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    spy_github = local_bin / "github-mcp-server"
    spy_github.write_text(
        f"#!/bin/sh\necho 'Version: {GITHUB_MCP_VERSION}'\n", encoding="utf-8"
    )
    os.chmod(spy_github, 0o755)
    spy_herdr = local_bin / "herdr"
    spy_herdr.write_text("#!/bin/sh\necho 'herdr 0.9.3'\n", encoding="utf-8")
    os.chmod(spy_herdr, 0o755)
    return stub_bin


def run_install(fake_home: Path) -> subprocess.CompletedProcess[str]:
    """Run install.sh against a sandboxed fake $HOME (never the real one)."""
    stub_bin = _install_stubs(fake_home)
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = f"{stub_bin}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        [str(INSTALL_SH)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def install_text() -> str:
    """Return the install.sh source text."""
    return INSTALL_SH.read_text(encoding="utf-8")


def profiles_heredoc() -> str:
    """Extract the profiles.sh append-heredoc body from install.sh."""
    match = re.search(
        r"cat >> \"\$PROFILES_SH\" << 'EOF'\n(.*?)\nEOF\n",
        install_text(),
        re.DOTALL,
    )
    assert (
        match is not None
    ), "install.sh must provision ~/.config/opencode/profiles.sh (#244 AC1)"
    return match.group(1)


def oc_home_function() -> str:
    """Extract the oc-home() function body from the profiles.sh heredoc."""
    heredoc = profiles_heredoc()
    match = re.search(
        r"^oc-home\(\) \{(.*?)^\}",
        heredoc,
        re.DOTALL | re.MULTILINE,
    )
    assert match is not None, "profiles.sh must define the oc-home() wrapper (#244 AC1)"
    return match.group(1)


def readme_section(header: str) -> str:
    """Return the body of a level-2 README section (excluding the header)."""
    lines = README_PATH.read_text(encoding="utf-8").splitlines()
    start: int | None = None
    for idx, line in enumerate(lines):
        if line.startswith(header):
            start = idx
            break
    assert start is not None, f"README.md is missing the '{header}' section"
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


# ---------------------------------------------------------------------------
# AC1 / MC1 — profiles.sh provisioning + oc-home wrapper semantics
# ---------------------------------------------------------------------------


class TestProfilesSnippet(unittest.TestCase):
    def test_install_sh_provisions_profiles_snippet_defining_oc_home(self) -> None:
        """install.sh must write profiles.sh defining the oc-home wrapper."""
        heredoc = profiles_heredoc()
        self.assertIn(
            "oc-home()", heredoc, "profiles.sh must define oc-home (#244 AC1)"
        )

    def test_oc_home_wrapper_sources_secrets_in_subshell_with_exec(self) -> None:
        """The wrapper sources .secrets-home.env inside a subshell ending in exec.

        MC1 (F1): set -a / set +a around the source (so {env:} interpolation
        and MCP servers see the values), then exec opencode "$@" — secrets
        never persist in the pane shell and no subshell lingers.
        """
        body = oc_home_function()
        self.assertIn("(", body, "wrapper must run inside a subshell (#244 AC1/MC1)")
        self.assertIn(
            'exec opencode "$@"',
            body,
            'wrapper must end in exec opencode "$@" (#244 AC1/MC1)',
        )
        set_a_pos = body.find("set -a")
        set_plus_a_pos = body.find("set +a")
        source_pos = body.find("source")
        self.assertNotEqual(
            set_a_pos, -1, "wrapper must set -a before sourcing secrets (MC1)"
        )
        self.assertNotEqual(
            source_pos, -1, "wrapper must source the home secrets file (MC1)"
        )
        self.assertNotEqual(
            set_plus_a_pos, -1, "wrapper must set +a after sourcing secrets (MC1)"
        )
        self.assertLess(
            set_a_pos,
            source_pos,
            "set -a must precede the secrets source (#244 AC1/MC1)",
        )
        self.assertLess(
            source_pos,
            set_plus_a_pos,
            "set +a must follow the secrets source (#244 AC1/MC1)",
        )
        self.assertIn(
            HOME_SECRETS_NAME,
            body,
            "wrapper must source .secrets-home.env, not a shared file (#244 AC3)",
        )

    def test_oc_home_wrapper_uses_prefix_assignment_without_export(self) -> None:
        """OPENCODE_CONFIG/OPENCODE_CONFIG_DIR are prefix-assigned, never exported."""
        body = oc_home_function()
        self.assertIn(
            'OPENCODE_CONFIG="$HOME/projects/opencode-home-config/opencode.jsonc"',
            body,
            "wrapper must prefix-assign OPENCODE_CONFIG to the home config (#244 AC1)",
        )
        self.assertIn(
            'OPENCODE_CONFIG_DIR="$HOME/projects/opencode-home-config"',
            body,
            "wrapper must prefix-assign OPENCODE_CONFIG_DIR to the home repo (#244 AC1)",
        )
        self.assertNotIn(
            "export OPENCODE_CONFIG",
            body,
            "wrapper must not export OPENCODE_CONFIG (prefix-assignment only)",
        )
        self.assertNotIn(
            "export OPENCODE_CONFIG_DIR",
            body,
            "wrapper must not export OPENCODE_CONFIG_DIR (prefix-assignment only)",
        )

    def test_profiles_snippet_update_preserves_oc_work(self) -> None:
        """MC3/F9 convergence invariant: updating oc-home never clobbers oc-work.

        The WORK installer (#177) already ships profiles.sh with oc-work().
        The HOME installer must append/update oc-home idempotently while
        leaving oc-work() byte-identical.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            dest = fake_home / ".config" / "opencode"
            dest.mkdir(parents=True)
            profiles = dest / "profiles.sh"
            profiles.write_text(OC_WORK_BLOCK, encoding="utf-8")

            first = run_install(fake_home)
            self.assertEqual(first.returncode, 0, f"install.sh failed: {first.stderr}")
            content = profiles.read_text(encoding="utf-8")
            self.assertIn(
                "oc-work()", content, "oc-work must survive the HOME install (MC3/F9)"
            )
            self.assertIn("oc-home()", content, "oc-home must be appended (MC3/F9)")
            self.assertIn(
                "opencode-work-config",
                content,
                "oc-work body must be untouched (MC3/F9)",
            )

            second = run_install(fake_home)
            self.assertEqual(
                second.returncode, 0, f"install.sh re-run failed: {second.stderr}"
            )
            content2 = profiles.read_text(encoding="utf-8")
            self.assertEqual(
                content2.count("oc-home()"),
                1,
                "oc-home must appear exactly once after two installs (idempotent, MC3)",
            )
            self.assertEqual(
                content2.count("oc-work()"), 1, "oc-work must never be duplicated"
            )

    def test_installed_wrapper_is_scoped_and_does_not_persist_secrets(
        self,
    ) -> None:
        """Behavioral (MC1): the installed wrapper reaches opencode with home env only.

        The fake opencode spy dumps its environment; the assertion checks that
        OPENCODE_CONFIG/OPENCODE_CONFIG_DIR and the home secrets are visible to
        the exec'd process, and that the sourced secret does NOT persist in the
        calling pane shell after the wrapper returns.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            home_dir = fake_home / "projects" / HOME_REPO_DIRNAME
            home_dir.mkdir(parents=True)
            (home_dir / "opencode.jsonc").write_text(
                '{"model": "sandbox"}\n', encoding="utf-8"
            )

            fake_bin = fake_home / ".stub-bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            spy = fake_bin / "opencode"
            spy.write_text("#!/bin/sh\nenv | sort\n", encoding="utf-8")
            os.chmod(spy, 0o755)

            result = run_install(fake_home)
            self.assertEqual(
                result.returncode, 0, f"install.sh failed: {result.stderr}"
            )

            profiles = fake_home / ".config" / "opencode" / "profiles.sh"
            self.assertTrue(
                profiles.is_file(), "profiles.sh must exist after install (#244 AC1)"
            )

            secrets = fake_home / ".config" / "opencode" / HOME_SECRETS_NAME
            secrets.write_text(
                'export OPENCODE_SANDBOX_SECRET="fake-secret-value-123"\n',
                encoding="utf-8",
            )
            os.chmod(secrets, 0o600)

            spy_out = Path(tmp) / "spy.out"
            script = (
                "set -u\n"
                f'export PATH="{fake_bin}:$PATH"\n'
                f'. "{profiles}"\n'
                f'oc-home --sandbox > "{spy_out}"\n'
                'if [ -n "${OPENCODE_SANDBOX_SECRET:-}" ]; then\n'
                "  echo leaked\n"
                "else\n"
                "  echo clean\n"
                "fi\n"
            )
            run = subprocess.run(
                ["bash", "-c", script],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
                env={**os.environ, "HOME": str(fake_home)},
            )
            self.assertEqual(
                run.returncode, 0, f"wrapper run failed: {run.stdout}\n{run.stderr}"
            )

            dumped = spy_out.read_text(encoding="utf-8")
            self.assertIn(
                f"OPENCODE_CONFIG={home_dir}/opencode.jsonc",
                dumped,
                "opencode must receive OPENCODE_CONFIG pointing at the home config (#244 AC2)",
            )
            self.assertIn(
                f"OPENCODE_CONFIG_DIR={home_dir}",
                dumped,
                "opencode must receive OPENCODE_CONFIG_DIR pointing at the home repo (#244 AC2)",
            )
            self.assertIn(
                "OPENCODE_SANDBOX_SECRET=fake-secret-value-123",
                dumped,
                "the exec'd opencode must see the profile-scoped secrets (#244 AC3/MC1)",
            )
            self.assertTrue(
                run.stdout.strip().endswith("clean"),
                "sourced secrets must NOT persist in the pane shell after oc-home returns "
                "(#244 AC3/MC1)",
            )

    def test_install_sh_sources_snippet_from_bashrc_and_profile(self) -> None:
        """install.sh must add the profiles.sh source line to .bashrc AND .profile."""
        text = install_text()
        self.assertIn('$PROFILES_SH"', text, "install.sh must reference $PROFILES_SH")
        self.assertGreaterEqual(
            text.count("source $PROFILES_SH"),
            2,
            "profiles.sh source line must be wired into both .bashrc and .profile (#244 AC1)",
        )

    def test_install_snippet_addition_is_idempotent(self) -> None:
        """Re-running install.sh must not duplicate the rc-file snippet entries."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            self.assertEqual(run_install(fake_home).returncode, 0)
            self.assertEqual(run_install(fake_home).returncode, 0)
            bashrc = (fake_home / ".bashrc").read_text(encoding="utf-8")
            profile = (fake_home / ".profile").read_text(encoding="utf-8")
            profiles_source = f"source {fake_home}/.config/opencode/profiles.sh"
            for name, content in (("bashrc", bashrc), ("profile", profile)):
                occurrences = content.count(profiles_source)
                self.assertEqual(
                    occurrences,
                    1,
                    f".{name} contains {occurrences} profiles.sh source lines after two "
                    "installs; must be exactly 1 (#244 AC1)",
                )


# ---------------------------------------------------------------------------
# AC3 / MC2 / MC9 — secrets split, shared .secrets.env retirement, migration
# ---------------------------------------------------------------------------


class TestSecretsIsolation(unittest.TestCase):
    def test_install_sh_no_longer_manages_shared_secrets_env(self) -> None:
        """install.sh must stop creating/managing the shared .secrets.env (MC2)."""
        text = install_text()
        self.assertIn(
            f'SECRETS_FILE="$DEST/{HOME_SECRETS_NAME}"',
            text,
            "install.sh must provision the profile-scoped .secrets-home.env (#244 AC3)",
        )
        template_shared = re.compile(
            r'^SECRETS_FILE="\$DEST/\.secrets\.env"', re.MULTILINE
        )
        self.assertIsNone(
            template_shared.search(text),
            "install.sh must stop managing the shared .secrets.env (#244 AC3/MC2)",
        )
        for line in text.splitlines():
            if ".secrets.env" in line and HOME_SECRETS_NAME not in line:
                self.assertIsNone(
                    re.search(r"\b(cat|echo)\b.*\.secrets\.env", line),
                    f"install.sh still creates/sources the shared secrets file: {line!r}",
                )
                self.assertNotIn(
                    ">>",
                    line,
                    f"install.sh still appends to the shared secrets file: {line!r}",
                )

    def test_install_sh_provisions_home_secrets_under_umask_077(self) -> None:
        """The home secrets template must be created with umask 077 (MC9)."""
        text = install_text()
        self.assertIn(
            "umask 077", text, "install.sh must provision secrets under umask 077 (MC9)"
        )
        self.assertIn(
            HOME_SECRETS_NAME,
            text,
            "install.sh must provision the .secrets-home.env template (#244 AC3)",
        )

    def test_install_sh_migrates_populated_shared_secrets_file(self) -> None:
        """A populated shared .secrets.env migrates to .secrets-home.env (mode 600).

        MC2: migrate the populated shared file preserving mode 600, then
        remove the old file. The marker value is a fake, non-secret
        placeholder — never a real credential.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            dest = fake_home / ".config" / "opencode"
            dest.mkdir(parents=True)
            old = dest / ".secrets.env"
            old.write_text(
                'export OPENROUTER_HOME_API_KEY="fake-migration-marker"\n',
                encoding="utf-8",
            )
            os.chmod(old, 0o600)

            result = run_install(fake_home)
            self.assertEqual(
                result.returncode, 0, f"install.sh failed: {result.stderr}"
            )

            new = dest / HOME_SECRETS_NAME
            self.assertTrue(
                new.is_file(),
                "populated shared secrets must be migrated to .secrets-home.env",
            )
            mode = stat.S_IMODE(new.stat().st_mode)
            self.assertEqual(
                mode,
                0o600,
                f".secrets-home.env must be mode 600, got {oct(mode)} (MC9)",
            )
            self.assertIn(
                "fake-migration-marker",
                new.read_text(encoding="utf-8"),
                "migration must preserve the populated values",
            )
            self.assertFalse(
                old.exists(),
                "the shared .secrets.env must be emptied/removed after migration (#244 AC3/MC2)",
            )

    def test_install_sh_removes_unpopulated_shared_secrets_template(self) -> None:
        """A bare (unpopulated) shared .secrets.env is removed as a dead artifact."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            dest = fake_home / ".config" / "opencode"
            dest.mkdir(parents=True)
            old = dest / ".secrets.env"
            old.write_text('export OPENROUTER_HOME_API_KEY=""\n', encoding="utf-8")
            os.chmod(old, 0o600)

            result = run_install(fake_home)
            self.assertEqual(
                result.returncode, 0, f"install.sh failed: {result.stderr}"
            )
            self.assertFalse(
                old.exists(), "an unpopulated shared .secrets.env must be removed"
            )
            self.assertTrue(
                (dest / HOME_SECRETS_NAME).is_file(),
                "the home secrets template must still be provisioned",
            )

    def test_install_sh_removes_legacy_source_lines_from_both_rc_files(self) -> None:
        """Old shared-secrets source lines are removed from .bashrc AND .profile.

        MC2/F2: cleanup covers both rc files with idempotent removal of
        existing shared-secrets source lines; unrelated lines are preserved.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            (fake_home / ".config" / "opencode").mkdir(parents=True)
            for rc_name in (".bashrc", ".profile"):
                rc = fake_home / rc_name
                rc.write_text(
                    f"export EDITOR=vim\n{OLD_SECRETS_SOURCE_LINE}\n", encoding="utf-8"
                )

            result = run_install(fake_home)
            self.assertEqual(
                result.returncode, 0, f"install.sh failed: {result.stderr}"
            )

            for rc_name in (".bashrc", ".profile"):
                content = (fake_home / rc_name).read_text(encoding="utf-8")
                self.assertNotIn(
                    ".secrets.env",
                    content,
                    f"{rc_name} still sources the shared .secrets.env (#244 AC3/MC2)",
                )
                self.assertIn(
                    "export EDITOR=vim",
                    content,
                    f"{rc_name}: unrelated lines must be preserved",
                )

    def test_install_sh_retires_secret_var_import_environment(self) -> None:
        """install.sh must not import secret vars into the systemd user env (MC2).

        The GUI-launcher import path is retired: install.sh instead unsets
        the previously imported secret variables and verifies via
        systemctl --user show-environment that no secret vars remain.
        """
        text = install_text()
        self.assertNotIn(
            "import-environment",
            text,
            "install.sh must retire the systemctl --user import-environment path (MC2)",
        )
        self.assertIn(
            "unset-environment",
            text,
            "install.sh must unset previously imported secret vars from the systemd "
            "user environment (MC2)",
        )
        self.assertIn(
            "show-environment",
            text,
            "install.sh must verify via show-environment that no secret vars remain "
            "(post-migration verification)",
        )
        for var in (
            "OPENROUTER_HOME_API_KEY",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "GITHUB_TOKEN_CODE_REVIEWER",
            "INTERVALS_API_KEY",
            "INTERVALS_ATHLETE_ID",
        ):
            self.assertIn(
                var,
                text,
                f"install.sh must unset the previously imported secret var {var} (MC2)",
            )


# ---------------------------------------------------------------------------
# AC4 / MC6 — legacy /AI_OS_ROOT switcher dead code removed
# ---------------------------------------------------------------------------


class TestLegacySwitcherCleanup(unittest.TestCase):
    def test_install_sh_removes_legacy_switcher_dead_code(self) -> None:
        """The /AI_OS_ROOT switcher functions are removed from .bashrc.

        AC4/MC6: dead-code deletion performed idempotently by install.sh;
        unrelated .bashrc lines must be preserved.
        """
        import tempfile

        for block in (LEGACY_SWITCHER_BLOCK, LEGACY_SWITCHER_BLOCK_COMMENTED):
            with tempfile.TemporaryDirectory() as tmp:
                fake_home = _make_fake_home(Path(tmp))
                (fake_home / ".config" / "opencode").mkdir(parents=True)
                bashrc = fake_home / ".bashrc"
                bashrc.write_text(
                    f"export EDITOR=vim\n\n{block}\nexport PATH=/usr/bin:$PATH\n",
                    encoding="utf-8",
                )

                first = run_install(fake_home)
                self.assertEqual(
                    first.returncode, 0, f"install.sh failed: {first.stderr}"
                )

                content = bashrc.read_text(encoding="utf-8")
                self.assertNotIn(
                    "opencode-switch-context",
                    content,
                    ".bashrc still contains the legacy opencode-switch-context dead code (#244 AC4)",
                )
                self.assertNotIn(
                    "opencode-status",
                    content,
                    ".bashrc still contains the legacy opencode-status dead code (#244 AC4)",
                )
                self.assertNotIn(
                    "AI_OS_ROOT",
                    content,
                    ".bashrc still references /AI_OS_ROOT (#244 AC4)",
                )
                self.assertIn(
                    "export EDITOR=vim",
                    content,
                    "unrelated .bashrc lines must be preserved",
                )
                self.assertIn(
                    "export PATH=/usr/bin:$PATH",
                    content,
                    "unrelated .bashrc lines must be preserved",
                )

                second = run_install(fake_home)
                self.assertEqual(
                    second.returncode, 0, f"install.sh re-run failed: {second.stderr}"
                )
                content2 = bashrc.read_text(encoding="utf-8")
                self.assertNotIn(
                    "AI_OS_ROOT", content2, "switcher removal must be idempotent (AC4)"
                )


# ---------------------------------------------------------------------------
# MC9 — config-dir hardening + fail-closed permission assertion
# ---------------------------------------------------------------------------


class TestPermissionHardening(unittest.TestCase):
    def test_install_sh_hardens_config_dir_to_700(self) -> None:
        """~/.config/opencode is hardened to 700 (MC9)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            result = run_install(fake_home)
            self.assertEqual(
                result.returncode, 0, f"install.sh failed: {result.stderr}"
            )
            dest = fake_home / ".config" / "opencode"
            mode = stat.S_IMODE(dest.stat().st_mode)
            self.assertEqual(
                mode,
                0o700,
                f"~/.config/opencode must be mode 700, got {oct(mode)} (MC9)",
            )

    def test_install_sh_has_fail_closed_permission_assertion(self) -> None:
        """install.sh must fail if any secrets env file is group/world-readable (MC9)."""
        text = install_text()
        self.assertIn(
            "-perm /044",
            text,
            "install.sh must assert permissions via find -perm /044 (#244 AC3/MC9)",
        )
        self.assertRegex(
            text,
            r"exit 1",
            "the permission assertion must fail closed with exit 1 (MC9)",
        )

    def test_install_sh_permission_assertion_fails_on_readable_secrets(self) -> None:
        """A group/world-readable secrets file must make install.sh fail closed."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake_home = _make_fake_home(Path(tmp))
            dest = fake_home / ".config" / "opencode"
            dest.mkdir(parents=True)
            leaked = dest / HOME_SECRETS_NAME
            leaked.write_text(
                "OPENROUTER_HOME_API_KEY=fake-not-a-secret\n", encoding="utf-8"
            )
            os.chmod(leaked, 0o644)

            result = run_install(fake_home)
            self.assertNotEqual(
                result.returncode,
                0,
                "install.sh must fail when a secrets env file is group/world-readable (#244 AC3/MC9)",
            )
            self.assertIn(
                "FATAL",
                result.stderr,
                "the permission failure must be reported loudly on stderr (#244 AC3/MC9)",
            )


# ---------------------------------------------------------------------------
# AC7 / MC5 — MADR-0010 decision record + indexes
# ---------------------------------------------------------------------------


class TestDecisionRecord(unittest.TestCase):
    def test_madr_0010_exists_with_mandatory_sections(self) -> None:
        """MADR docs/adr/0010-per-pane-profile-selection-and-secrets-isolation.md exists."""
        path = ADR_DIR / "0010-per-pane-profile-selection-and-secrets-isolation.md"
        self.assertTrue(path.is_file(), "MADR 0010 must exist in docs/adr/ (#244 AC7)")
        text = path.read_text(encoding="utf-8")
        for section in (
            "## Context",
            "## Decision Drivers",
            "## Considered Options",
            "## Decision Outcome",
            "## Consequences",
        ):
            self.assertIn(section, text, f"MADR 0010 missing '{section}' (#244 AC7)")

    def test_madr_0010_documents_options_and_po_risk_acceptance(self) -> None:
        """MADR 0010 weighs the options and records the explicit PO risk acceptance."""
        text = (
            ADR_DIR / "0010-per-pane-profile-selection-and-secrets-isolation.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "symlink flipping", text, "MADR 0010 must consider global symlink flipping"
        )
        self.assertIn(
            "OPENCODE_CONFIG",
            text,
            "MADR 0010 must describe the env-var wrapper mechanism",
        )
        self.assertIn(
            "risk-acceptance",
            text.lower().replace("risk acceptance", "risk-acceptance"),
            "MADR 0010 must record the explicit PO risk-acceptance (MC5)",
        )
        self.assertIn(
            "auth.json",
            text,
            "MADR 0010 must name the shared auth.json token surface (MC5)",
        )
        self.assertIn(
            "mcp-auth.json",
            text,
            "MADR 0010 must name the shared mcp-auth.json surface (MC5)",
        )
        self.assertIn(
            "@fpittelo",
            text,
            "MADR 0010 risk-acceptance must be attributed to the PO (MC5)",
        )

    def test_decision_indexes_list_0010(self) -> None:
        """Both decision indexes carry the 0010 row."""
        adr_index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "0010", adr_index, "docs/adr/README.md index must list 0010 (#244 AC7)"
        )
        self.assertIn(
            "0010-per-pane-profile-selection-and-secrets-isolation.md",
            adr_index,
            "docs/adr/README.md must link the 0010 record file (#244 AC7)",
        )
        arc42_index = (ARC42_DIR / "09-architecture-decisions.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "MADR-0010", arc42_index, "arc42 §9 index must list MADR-0010 (#244 AC7)"
        )

    def test_arc42_risks_document_proc_environ_residual(self) -> None:
        """arc42 §11 documents the same-UID /proc/<pid>/environ residual (MC7)."""
        text = (ARC42_DIR / "11-risks-and-technical-debt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "/proc",
            text,
            "arc42 §11 must document the /proc/<pid>/environ residual (MC7)",
        )
        self.assertIn("#244", text, "arc42 §11 residual row must reference #244 (MC7)")


# ---------------------------------------------------------------------------
# AC6 / MC8 — README dual-profile documentation
# ---------------------------------------------------------------------------


class TestReadmeDocumentation(unittest.TestCase):
    def test_readme_documents_per_pane_profile_selection(self) -> None:
        """README documents oc-home/oc-work, profiles.sh, merge caveat, and the trap."""
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "oc-home", readme, "README must document the oc-home wrapper (AC6)"
        )
        self.assertIn(
            "oc-work", readme, "README must document coexistence with oc-work (AC6)"
        )
        self.assertIn(
            "profiles.sh", readme, "README must document the profiles.sh snippet (AC6)"
        )
        self.assertIn(
            "OPENCODE_CONFIG",
            readme,
            "README must document the env-var mechanism (AC6)",
        )
        self.assertTrue(
            "base layer" in readme or "merged" in readme,
            "README must document the config-merge caveat (global symlink stays the base layer) (AC6)",
        )
        self.assertIn(
            "instances are running",
            readme,
            "README must carry the 'never run the other profile's install.sh while "
            "instances are running' trap (AC6)",
        )

    def test_readme_states_bare_opencode_unsupported_for_secrets(self) -> None:
        """README states bare `opencode` is unsupported for secret-bearing work (MC8)."""
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            readme,
            r"[Bb]are `opencode`[^\n]*unsupported|unsupported[^\n]*[Bb]are `opencode`",
            "README must state that bare `opencode` is unsupported for secret-bearing work (MC8)",
        )

    def test_readme_documents_herdr_dual_pane_usage(self) -> None:
        """README documents running oc-home and oc-work in parallel Herdr panes (AC6)."""
        section = readme_section("## 🧩 Per-pane profile selection")
        self.assertIn(
            "Herdr", section, "README per-pane section must cover Herdr usage (AC6)"
        )
        self.assertIn(
            "herdr agent list", section, "README must reference herdr agent list (AC6)"
        )


# ---------------------------------------------------------------------------
# MC10 — gitignore coverage
# ---------------------------------------------------------------------------


class TestGitignoreCoverage(unittest.TestCase):
    def test_gitignore_covers_home_secrets_file(self) -> None:
        """.gitignore must cover .secrets-home.env (MC10)."""
        patterns = GITIGNORE_PATH.read_text(encoding="utf-8").splitlines()
        covered = any(
            pattern.strip() in (".secrets*.env", ".secrets-home.env", "*.env")
            for pattern in patterns
            if pattern.strip() and not pattern.strip().startswith("#")
        )
        self.assertTrue(
            covered,
            ".gitignore must cover .secrets-home.env via an explicit or glob pattern (MC10)",
        )


if __name__ == "__main__":
    unittest.main()
