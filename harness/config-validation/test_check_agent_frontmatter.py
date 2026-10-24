#!/usr/bin/env python3
"""Regression tests for check_agent_frontmatter.py (#338 AC3).

stdlib unittest only: no pytest, no third-party imports. Each case runs the
checker as a subprocess against a throwaway repository tree (tempfile), so
exit codes and failure context are covered end to end.

The checker validates the YAML front-matter block of every agents/*.md:
delimiter structure, YAML parseability (duplicate keys rejected), and the
mandatory-field schema of #338 AC2 (description, mode, model, temperature,
permission). Negative cases cover each defect class from #325/#338; the
real-repo positive control pins all 7 current agent files.

Run:
    python3 harness/config-validation/test_check_agent_frontmatter.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_agent_frontmatter.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

# Minimal valid front-matter exercising every mandatory field (#338 AC2).
VALID_FRONTMATTER = (
    "---\n"
    'description: "Test agent"\n'
    "mode: subagent\n"
    'model: "openrouter/z-ai/glm-5.3-flash"\n'
    "temperature: 0.2\n"
    "permission:\n"
    '  "bash":\n'
    '    "*": allow\n'
    "---\n"
    "Body text after the front matter.\n"
)


def build_repo(files: dict[str, str]) -> Path:
    """Materialize a throwaway repo with the given relative files."""
    root = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker CLI against a repo root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


class AgentFrontmatterTests(unittest.TestCase):
    """Negative/positive cases for the front-matter validity invariant."""

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
        proc = run_checker(build_repo({"agents/test.md": VALID_FRONTMATTER}))
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_unknown_keys_allowed(self) -> None:
        """Forward compatibility: unknown top-level keys must not fail (#338 AC2)."""
        content = VALID_FRONTMATTER.replace("---\n", "---\nfuture_field: whatever\n", 1)
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )

    def test_missing_leading_delimiter_fails(self) -> None:
        content = VALID_FRONTMATTER.lstrip("-\n")
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "delimiter")

    def test_missing_closing_delimiter_fails(self) -> None:
        content = VALID_FRONTMATTER.rsplit("---\n", 1)[0]
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "delimiter")

    def test_invalid_yaml_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            "temperature: 0.2\n", "temperature: [unclosed\n"
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "YAML")

    def test_duplicate_key_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            "temperature: 0.2\n", "temperature: 0.2\ntemperature: 0.5\n"
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "duplicate")

    def test_missing_mandatory_field_fails(self) -> None:
        for field in (
            "description",
            "mode",
            "model",
            "temperature",
            "permission",
        ):
            with self.subTest(field=field):
                lines = [
                    line
                    for line in VALID_FRONTMATTER.splitlines(keepends=True)
                    if not line.startswith(field + ":")
                ]
                # For permission, also drop its nested block lines.
                if field == "permission":
                    lines = [line for line in lines if line.startswith("  ") is False]
                proc = run_checker(build_repo({"agents/test.md": "".join(lines)}))
                self.assert_gate_fails(proc, "agents/test.md", field)

    def test_empty_description_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            'description: "Test agent"\n', 'description: ""\n'
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "description")

    def test_description_not_a_string_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            'description: "Test agent"\n', "description: [not, a, string]\n"
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "description")

    def test_temperature_not_a_number_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            "temperature: 0.2\n", 'temperature: "0.2"\n'
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "temperature")

    def test_temperature_above_range_fails(self) -> None:
        content = VALID_FRONTMATTER.replace("temperature: 0.2\n", "temperature: 2.1\n")
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "temperature")

    def test_temperature_below_range_fails(self) -> None:
        content = VALID_FRONTMATTER.replace("temperature: 0.2\n", "temperature: -0.1\n")
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "temperature")

    def test_model_wrong_shape_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            'model: "openrouter/z-ai/glm-5.3-flash"\n', 'model: "anthropic/claude"\n'
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "openrouter/")

    def test_model_not_a_string_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            'model: "openrouter/z-ai/glm-5.3-flash"\n', "model: 42\n"
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "model")

    def test_permission_not_a_mapping_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            'permission:\n  "bash":\n    "*": allow\n', "permission: allow-all\n"
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "permission")

    def test_permission_empty_mapping_fails(self) -> None:
        content = VALID_FRONTMATTER.replace(
            'permission:\n  "bash":\n    "*": allow\n', "permission: {}\n"
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        self.assert_gate_fails(proc, "agents/test.md", "permission")

    def test_error_names_file_and_line(self) -> None:
        """Actionable errors: file name plus a line reference (#338 AC1)."""
        content = VALID_FRONTMATTER.replace(
            "temperature: 0.2\n", "temperature: [unclosed\n"
        )
        proc = run_checker(build_repo({"agents/test.md": content}))
        output = proc.stdout + proc.stderr
        self.assertIn("agents/test.md", output)
        self.assertRegex(output, r"line \d+")


class RealRepositoryTests(unittest.TestCase):
    """Positive control: all 7 real agent files satisfy the invariant (#338 AC3)."""

    def test_real_repo_agents_pass(self) -> None:
        proc = run_checker(REPO_ROOT)
        self.assertEqual(
            proc.returncode,
            0,
            f"expected exit 0, got {proc.returncode}:\n{proc.stdout}{proc.stderr}",
        )
        for agent in (
            "architect",
            "coach",
            "code-reviewer",
            "cyber-security",
            "developer",
            "devops",
            "scrum-master",
        ):
            self.assertIn(f"agents/{agent}.md", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
