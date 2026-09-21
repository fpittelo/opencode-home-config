#!/usr/bin/env python3
"""Validate every fenced mermaid block in the HOME doc set (AC1 of #61).

Doc set: docs/**/*.md, README.md, agents/**/*.md, skills/**/*.md.

Two modes:

- render (default): each block is rendered by the pinned mermaid-cli (`mmdc`)
  located on PATH (`mmdc -i <block> -o <tmp>/out.svg`, format inferred from
  the .svg extension); a render-level failure fails the gate, naming the
  file, the block index and the mmdc error excerpt. Runs fully offline per
  ADR-0001 (no network egress). This mode is owned by the deep-validation
  workflow (MADR-0003 D2, #133) and must not regress.

- syntax (--syntax): native structural validation without mmdc/Chromium
  (MADR-0003 D1, #134 - per-PR gate, zero Docker):
    * optional YAML frontmatter (opening '---' on the block's first line) is
      skipped before the keyword check; an unterminated frontmatter fence is
      a failure;
    * the first non-comment token must be a recognized diagram keyword
      (comment lines start with '%%', which also covers %%{init}%%
      directives); the keyword match is case-sensitive on purpose, mirroring
      mermaid's own grammar;
    * the body must be non-empty;
    * every content line must carry an even number of double quotes outside
      '%%' comments (no unterminated strings);
    * in the bracket-structural dialects (flowchart, graph, classDiagram,
      stateDiagram[-v2]) unquoted parentheses and square brackets must
      balance per line after comment stripping. The asymmetric flag shape
      'id>text]' legally closes with ']' on an empty stack and is allowed
      when a '>' precedes it on the same line. Braces are not checked:
      erDiagram relationships ('||--o{'), multi-line 'class X {' blocks and
      C4 boundaries use them legally. Free-text-heavy dialects
      (sequenceDiagram, erDiagram, journey, gantt, pie, gitGraph, mindmap,
      timeline, C4, architecture-beta, ...) are exempt from the bracket
      check because their arrows ('Client-)Server') and labels legally
      contain unbalanced brackets.

  A syntax failure exits non-zero naming the file and the 1-based block
  index. Zero mermaid blocks found = pass with a note (both modes). Missing
  mmdc = clear error in render mode (the docs-validator image guarantees its
  presence); --syntax never requires mmdc.

Usage: check_mermaid.py [--syntax] [REPO_ROOT]
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DOC_GLOBS = ("docs/**/*.md", "agents/**/*.md", "skills/**/*.md")
FENCE_RE = re.compile(r"^ {0,3}(`{3,})(.*)$")
MMDC_TIMEOUT_S = 120
EXCERPT_LINES = 15

# Diagram keywords recognized by the syntax mode. Case-sensitive on purpose:
# mermaid's own grammar is case-sensitive, so the syntax check must not
# accept what the render check would reject.
DIAGRAM_KEYWORDS = frozenset({
    "flowchart", "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram", "stateDiagram-v2",
    "erDiagram",
    "journey", "gantt", "pie", "gitGraph",
    "quadrantChart", "mindmap", "timeline",
    "sankey-beta", "xychart-beta", "block-beta", "architecture-beta",
    "radar-beta", "kanban-beta",
    "C4Context", "C4Container", "C4Component", "C4Dynamic",
    "requirementDiagram", "requirement",
})

# Dialects whose node shapes make unquoted ()/[] structurally significant;
# only these get the per-line bracket/paren balance check.
BRACKET_STRUCTURAL = frozenset({
    "flowchart", "graph", "classDiagram", "stateDiagram", "stateDiagram-v2",
})


def doc_files(root: Path) -> list[Path]:
    """Deterministically ordered markdown files of the doc set."""
    files = {p for pattern in DOC_GLOBS for p in root.glob(pattern) if p.is_file()}
    readme = root / "README.md"
    if readme.is_file():
        files.add(readme)
    return sorted(files)


def extract_mermaid_blocks(text: str) -> list[tuple[int, int, str]]:
    """Return (block_index_1based, opening_line_1based, code) per ```mermaid fence.

    Tracks all fences (any info string) so that mermaid blocks nested inside
    other fenced blocks are never extracted.
    """
    blocks: list[tuple[int, int, str]] = []
    fence_len: int | None = None
    capturing = False
    start_line = 0
    body: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if fence_len is None:
            if m:
                fence_len = len(m.group(1))
                info = m.group(2).strip().split()
                capturing = bool(info) and info[0] == "mermaid"
                if capturing:
                    start_line, body = lineno, []
        elif m and len(m.group(1)) >= fence_len and not m.group(2).strip():
            if capturing:
                blocks.append((len(blocks) + 1, start_line, "\n".join(body)))
            fence_len, capturing = None, False
        elif capturing:
            body.append(line)
    return blocks


def validate_block(mmdc: str, code: str, workdir: Path, index: int) -> str | None:
    """Render one block with mmdc; return None on success, else a failure excerpt."""
    src = workdir / f"block-{index}.mmd"
    out = workdir / f"out-{index}.svg"
    src.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [mmdc, "-i", str(src), "-o", str(out)],
            capture_output=True,
            text=True,
            timeout=MMDC_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"mmdc timed out after {MMDC_TIMEOUT_S}s"
    if proc.returncode == 0:
        return None
    combined = (proc.stderr + "\n" + proc.stdout).splitlines()
    excerpt = "\n".join(line for line in combined[-EXCERPT_LINES:] if line.strip())
    return f"mmdc exited {proc.returncode}\n{excerpt}".strip()


def strip_comment(line: str) -> str:
    """Truncate the line at the first '%%' outside double-quoted text."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_string = not in_string
        elif ch == "%" and not in_string and line[i:i + 2] == "%%":
            return line[:i]
    return line


def split_frontmatter(lines: list[str]) -> tuple[list[str], str | None]:
    """Strip YAML frontmatter; return (content_lines, error_reason)."""
    if not lines or lines[0].strip() != "---":
        return lines, None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[i + 1:], None
    return [], "unterminated YAML frontmatter (no closing '---')"


def keyword_of(lines: list[str]) -> str | None:
    """First token of the first non-empty, non-comment line, else None."""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        return stripped.split()[0]
    return None


def quote_error(line: str) -> str | None:
    """Reason if the comment-stripped line has an odd number of double quotes."""
    if strip_comment(line).count('"') % 2:
        return "odd number of '\"' (unterminated string?)"
    return None


def bracket_error(line: str) -> str | None:
    """Reason if unquoted ()/[] are unbalanced on the comment-stripped line.

    The asymmetric flag shape 'id>text]' legally closes with ']' on an empty
    stack; accepted when a '>' precedes it outside quotes on the same line.
    """
    code = strip_comment(line)
    openers = {"(": ")", "[": "]"}
    stack: list[str] = []
    in_string = False
    saw_gt = False
    for ch in code:
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == ">":
                saw_gt = True
            elif ch in openers:
                stack.append(openers[ch])
            elif ch in (")", "]"):
                if stack and stack[-1] == ch:
                    stack.pop()
                elif ch == "]" and saw_gt and not stack:
                    continue  # flag shape 'id>text]'
                else:
                    return f"unbalanced '{ch}'"
    if in_string:
        return "unterminated string"
    if stack:
        return f"unclosed '{stack[-1]}'"
    return None


def syntax_errors(code: str) -> list[str]:
    """Structural errors of one mermaid block body (syntax mode)."""
    content, fm_error = split_frontmatter(code.splitlines())
    if fm_error:
        return [fm_error]
    keyword = keyword_of(content)
    if keyword is None:
        return ["empty block (no non-comment content)"]
    if keyword not in DIAGRAM_KEYWORDS:
        return [f"unrecognized diagram keyword '{keyword}'"]
    check_brackets = keyword in BRACKET_STRUCTURAL
    errors: list[str] = []
    for line in content:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        if (reason := quote_error(line)) is not None:
            errors.append(f"line '{stripped[:60]}': {reason}")
            continue  # string state already broken; bracket scan would be noise
        if check_brackets and (reason := bracket_error(line)) is not None:
            errors.append(f"line '{stripped[:60]}': {reason}")
    return errors


def run_render(root: Path, files: list[Path]) -> int:
    """Render-mode gate (unchanged behaviour; owned by deep validation)."""
    mmdc = shutil.which("mmdc")
    if mmdc is None:
        print(
            "error: mmdc not found in PATH - the docs-validator image guarantees it; "
            "install @mermaid-js/mermaid-cli or run inside the image",
            file=sys.stderr,
        )
        return 1
    total = 0
    with tempfile.TemporaryDirectory(prefix="docsval-mmdc-") as td:
        workdir = Path(td)
        for path in files:
            text = path.read_text(encoding="utf-8")
            for index, start_line, code in extract_mermaid_blocks(text):
                total += 1
                failure = validate_block(mmdc, code, workdir, index)
                if failure is not None:
                    print(f"FAIL check_mermaid: {path.relative_to(root)} "
                          f"block #{index} (line {start_line}): {failure}")
                    return 1
    if total == 0:
        print("PASS check_mermaid: no mermaid blocks found in doc set (nothing to validate)")
        return 0
    print(f"PASS check_mermaid: {total} mermaid block(s) validated in {len(files)} file(s)")
    return 0


def run_syntax(root: Path, files: list[Path]) -> int:
    """Syntax-mode gate: native structural validation, no mmdc/Chromium."""
    total = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        for index, start_line, code in extract_mermaid_blocks(text):
            total += 1
            errors = syntax_errors(code)
            if errors:
                print(f"FAIL check_mermaid (syntax): {path.relative_to(root)} "
                      f"block #{index} (line {start_line}): {'; '.join(errors)}")
                return 1
    if total == 0:
        print("PASS check_mermaid (syntax): no mermaid blocks found in doc set "
              "(nothing to validate)")
        return 0
    print(f"PASS check_mermaid (syntax): {total} mermaid block(s) structurally valid "
          f"in {len(files)} file(s)")
    return 0


def main(argv: list[str]) -> int:
    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Validate fenced mermaid blocks. Default mode renders each "
                    "block with mmdc (deep validation); --syntax validates "
                    "structure natively without mmdc/Chromium (per-PR gate).")
    parser.add_argument("root", nargs="?", default=None,
                        help="repository root (default: the script's own repo)")
    parser.add_argument("--syntax", action="store_true",
                        help="native structural validation, no mmdc/Chromium "
                             "(MADR-0003 D1)")
    args = parser.parse_args(argv[1:])
    root = Path(args.root).resolve() if args.root else default_root
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    files = doc_files(root)
    if args.syntax:
        return run_syntax(root, files)
    return run_render(root, files)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
