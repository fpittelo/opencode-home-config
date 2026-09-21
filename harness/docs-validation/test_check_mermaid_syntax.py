#!/usr/bin/env python3
"""Regression tests for check_mermaid.py --syntax (advisory from #134's review).

stdlib unittest only: no pytest, no third-party imports. Each case runs the
CLI as a subprocess against a throwaway repository tree (tempfile), so the
exit code and the file/block-index failure context are covered end to end.

Defect classes carried forward from #134 (each must FAIL, naming the file and
the 1-based block index): empty block, bad keyword, unterminated frontmatter,
odd quote count, unclosed bracket, unbalanced parenthesis. Positive controls
pin the legitimate constructs the checker must keep accepting (open arrows in
sequenceDiagram, frontmatter + %%{init}%% directives, erDiagram braces,
gitGraph strings, nested-fence extraction, zero-block documents).

Run:
    python3 harness/docs-validation/test_check_mermaid_syntax.py
    python3 -m unittest harness.docs-validation.test_check_mermaid_syntax
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_mermaid.py"

VALID_FLOWCHART = "flowchart TD\n  A[Start] --> B[End]\n"


def run_syntax(files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run check_mermaid.py --syntax over a temp repo containing `files`.

    Files are placed under docs/ because the checker's doc set is
    docs/**, agents/**, skills/** and README.md (by design, shared with
    check_links.py / check_mermaid.py render mode).
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, text in files.items():
            path = root / "docs" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--syntax", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )


def two_block_doc(defect_body: str) -> str:
    """Doc with a valid block #1 and a defective block #2 (context check)."""
    return (
        "# Doc\n\n"
        "```mermaid\n"
        + VALID_FLOWCHART
        + "```\n\n"
        "```mermaid\n"
        + defect_body
        + "```\n"
    )


class DefectClassTests(unittest.TestCase):
    """Each #134 defect class must fail with file + block-index context."""

    def assert_gate_fails(self, doc: str, *expected_fragments: str) -> None:
        proc = run_syntax({"defect.md": doc})
        output = proc.stdout + proc.stderr
        self.assertEqual(
            proc.returncode, 1,
            f"expected exit 1, got {proc.returncode}:\n{output}",
        )
        self.assertIn("defect.md", output)  # file context
        self.assertIn("block #2", output)   # 1-based block-index context
        for fragment in expected_fragments:
            self.assertIn(fragment, output)

    def test_empty_block_fails(self) -> None:
        self.assert_gate_fails(two_block_doc(""), "empty block")

    def test_bad_keyword_fails(self) -> None:
        self.assert_gate_fails(
            two_block_doc("flowchrt TD\n  A --> B\n"),
            "unrecognized diagram keyword 'flowchrt'",
        )

    def test_unterminated_frontmatter_fails(self) -> None:
        self.assert_gate_fails(
            two_block_doc("---\ntitle: x\n  A --> B\n"),
            "unterminated YAML frontmatter",
        )

    def test_odd_quote_count_fails(self) -> None:
        self.assert_gate_fails(
            two_block_doc("flowchart TD\n  A[\"unterminated\n"),
            "odd number of",
        )

    def test_unclosed_bracket_fails(self) -> None:
        # 'A[label' opens a bracket whose closer ']' never arrives; the
        # checker names the pending closer character in the message.
        self.assert_gate_fails(
            two_block_doc("flowchart TD\n  A[label\n"),
            "unclosed ']'",
        )

    def test_unbalanced_parenthesis_fails(self) -> None:
        self.assert_gate_fails(
            two_block_doc("flowchart TD\n  A(label\n"),
            "unclosed ')'",
        )


class PositiveControlTests(unittest.TestCase):
    """Legitimate constructs must keep passing (guards over-strict checks)."""

    def assert_gate_passes(self, files: dict[str, str], *expected: str) -> None:
        proc = run_syntax(files)
        output = proc.stdout + proc.stderr
        self.assertEqual(
            proc.returncode, 0,
            f"expected exit 0, got {proc.returncode}:\n{output}",
        )
        for fragment in expected:
            self.assertIn(fragment, output)

    def test_valid_flowchart_passes(self) -> None:
        self.assert_gate_passes(
            {"ok.md": f"```mermaid\n{VALID_FLOWCHART}```\n"},
            "1 mermaid block(s) structurally valid",
        )

    def test_sequence_diagram_open_arrow_passes(self) -> None:
        body = (
            "sequenceDiagram\n"
            "  Client->Server: request\n"
            "  Client-)Server: fire and forget\n"
        )
        self.assert_gate_passes(
            {"ok.md": f"```mermaid\n{body}```\n"},
            "1 mermaid block(s) structurally valid",
        )

    def test_frontmatter_directive_er_braces_pass(self) -> None:
        body = (
            "---\n"
            "title: schema\n"
            "---\n"
            "%%{init: {\"theme\": \"dark\"}}%%\n"
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places\n"
            "  CUSTOMER {\n"
            "    string name\n"
            "  }\n"
        )
        self.assert_gate_passes(
            {"ok.md": f"```mermaid\n{body}```\n"},
            "1 mermaid block(s) structurally valid",
        )

    def test_gitgraph_quotes_pass(self) -> None:
        body = (
            "gitGraph\n"
            "  commit id: \"one\"\n"
            "  branch dev\n"
            "  commit id: \"three\"\n"
        )
        self.assert_gate_passes(
            {"ok.md": f"```mermaid\n{body}```\n"},
            "1 mermaid block(s) structurally valid",
        )

    def test_zero_blocks_passes(self) -> None:
        self.assert_gate_passes(
            {"plain.md": "# No diagrams here\n"},
            "no mermaid blocks found",
        )

    def test_nested_fence_not_extracted(self) -> None:
        doc = (
            "````text\n"
            "```mermaid\n"
            "flowchrt TD\n"
            "```\n"
            "````\n"
            "\n"
            "```mermaid\n"
            + VALID_FLOWCHART
            + "```\n"
        )
        self.assert_gate_passes({"ok.md": doc}, "1 mermaid block(s) structurally valid")


if __name__ == "__main__":
    unittest.main()
