#!/usr/bin/env python3
"""Regression tests for harness/run.sh native gate toolchain pinning (#256).

stdlib unittest only: no pytest, no third-party imports. Each case runs
``run.sh`` as a subprocess against a throwaway repository tree (tempfile) with
mock tools on a controlled PATH, so exit codes, path selection and the exact
command chain are covered end to end.

The native Python gate must resolve every tool from the project ``.venv``
(``${REPO_ROOT}/.venv/bin``) and never silently fall back to lookalike
host-PATH tools (#256 AC2/AC3); the deps phase must retain dev extras
(``uv sync --all-extras``, #256 AC1); the container fallback must stay
unchanged when the host has neither ``uv`` nor a project ``.venv`` (#256 AC4).

Run:
    python3 harness/config-validation/test_harness_run.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RUN_SH = Path(__file__).resolve().parents[1] / "run.sh"
BASH = shutil.which("bash") or "/bin/bash"

# The full native Python gate toolchain (pytest-cov is probed separately via
# the project interpreter, mirroring run.sh's python_native_tools_ok).
PYTHON_TOOLS = ("ruff", "black", "isort", "mypy", "pytest")


def write_tool(bin_dir: Path, name: str, log: Path, exit_code: int = 0) -> None:
    """Materialize an executable mock tool that logs its name and PATH."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / name
    script.write_text(
        "#!/bin/bash\n"
        f'printf "%s|%s\\n" "{name}" "$PATH" >> "{log}"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def write_arg_logger(bin_dir: Path, name: str, log: Path, exit_code: int = 0) -> None:
    """Materialize an executable mock tool that logs each argv element."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / name
    script.write_text(
        "#!/bin/bash\n"
        f'for arg in "$@"; do printf "%s\\n" "$arg" >> "{log}"; done\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def run_harness(
    stack: str, phase: str, root: Path, path_dirs: list[Path]
) -> subprocess.CompletedProcess[str]:
    """Run run.sh with a controlled PATH (only the given directories)."""
    env = {**os.environ, "PATH": os.pathsep.join(str(path) for path in path_dirs)}
    return subprocess.run(
        [BASH, str(RUN_SH), stack, phase, str(root)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def read_log(log: Path) -> list[str]:
    """Return the mock tool log lines (empty when the tool never ran)."""
    if not log.exists():
        return []
    return log.read_text(encoding="utf-8").splitlines()


class DepsPhaseTests(unittest.TestCase):
    """AC1: the deps phase retains dev extras."""

    def test_native_deps_uses_all_extras(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture'\n", encoding="utf-8"
        )
        bin_dir = root / "mockbin"
        log = root / "uv.log"
        write_arg_logger(bin_dir, "uv", log)

        proc = run_harness("python", "deps", root, [bin_dir])

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        args = read_log(log)
        self.assertIn("sync", args)
        self.assertIn("--all-extras", args)


class NativeGateTests(unittest.TestCase):
    """AC2/AC3: the native gate is pinned to the project .venv."""

    def test_gate_runs_with_venv_bin_first_in_path(self) -> None:
        root = Path(tempfile.mkdtemp())
        venv_bin = root / ".venv" / "bin"
        log = root / "gate.log"
        for tool in (*PYTHON_TOOLS, "python"):
            write_tool(venv_bin, tool, log)

        proc = run_harness("python", "gate", root, [venv_bin])

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        lines = read_log(log)
        invoked = {line.split("|", 1)[0] for line in lines}
        for tool in PYTHON_TOOLS:
            self.assertIn(tool, invoked)
        for line in lines:
            path = line.split("|", 1)[1]
            self.assertEqual(
                path.split(os.pathsep)[0],
                str(venv_bin),
                f"project .venv must be first in PATH, saw: {path}",
            )

    def test_host_toolchain_drift_does_not_affect_gate(self) -> None:
        root = Path(tempfile.mkdtemp())
        venv_bin = root / ".venv" / "bin"
        venv_log = root / "venv.log"
        for tool in (*PYTHON_TOOLS, "python"):
            write_tool(venv_bin, tool, venv_log)
        # A stale host mypy that would fail the gate if it were ever used.
        host_bin = root / "hostbin"
        host_log = root / "host.log"
        write_tool(host_bin, "mypy", host_log, exit_code=1)

        proc = run_harness("python", "gate", root, [host_bin, venv_bin])

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(read_log(host_log), [], "host mypy must never run")
        self.assertIn("mypy", {line.split("|", 1)[0] for line in read_log(venv_log)})

    def test_gate_exits_3_when_venv_missing(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture'\n", encoding="utf-8"
        )
        # Host uv present (native path selected) but no project .venv yet.
        bin_dir = root / "mockbin"
        write_arg_logger(bin_dir, "uv", root / "uv.log")

        proc = run_harness("python", "gate", root, [bin_dir])

        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("project .venv not found", proc.stderr)
        self.assertIn("refusing to use host PATH tools", proc.stderr)

    def test_gate_exits_3_when_tool_missing(self) -> None:
        root = Path(tempfile.mkdtemp())
        venv_bin = root / ".venv" / "bin"
        log = root / "gate.log"
        # Complete toolchain except mypy.
        for tool in ("ruff", "black", "isort", "pytest", "python"):
            write_tool(venv_bin, tool, log)

        proc = run_harness("python", "gate", root, [venv_bin])

        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("toolchain incomplete", proc.stderr)
        self.assertIn("refusing to use host PATH tools", proc.stderr)


class ContainerFallbackTests(unittest.TestCase):
    """AC4: the container fallback is unchanged when no uv and no .venv."""

    def test_gate_falls_back_to_container_with_security_flags(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "pyproject.toml").write_text(
            "[project]\nname = 'fixture'\n", encoding="utf-8"
        )
        bin_dir = root / "mockbin"
        log = root / "docker.log"
        write_arg_logger(bin_dir, "docker", log)

        proc = run_harness("python", "gate", root, [bin_dir])

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        args = read_log(log)
        self.assertIn("--network=none", args)
        self.assertIn("--read-only", args)
        self.assertIn("--cap-drop=ALL", args)
        self.assertIn("--security-opt", args)
        self.assertIn("no-new-privileges", args)
        self.assertIn("1000:1000", args)
        self.assertTrue(
            any("--cov-fail-under=80" in arg for arg in args),
            f"coverage threshold missing from container gate: {args}",
        )


if __name__ == "__main__":
    unittest.main()
