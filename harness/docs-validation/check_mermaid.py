#!/usr/bin/env python3
"""Validate every fenced mermaid block in the HOME doc set (AC1 of #61).

Doc set: docs/**/*.md, README.md, agents/**/*.md, skills/**/*.md.
Each block is rendered by the pinned mermaid-cli (`mmdc`) located on PATH
(`mmdc -i <block> -o <tmp>/out.svg`, format inferred from the .svg extension);
a render-level failure fails the gate, naming the file, the block index and
the mmdc error excerpt. Runs fully offline per ADR-0001 (no network egress).

Zero mermaid blocks found = pass with a note. Missing mmdc = clear error
(the docs-validator image guarantees its presence).

Usage: check_mermaid.py [REPO_ROOT]
"""
from __future__ import annotations

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


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    mmdc = shutil.which("mmdc")
    if mmdc is None:
        print(
            "error: mmdc not found in PATH - the docs-validator image guarantees it; "
            "install @mermaid-js/mermaid-cli or run inside the image",
            file=sys.stderr,
        )
        return 1
    total = 0
    files = doc_files(root)
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


if __name__ == "__main__":
    sys.exit(main(sys.argv))
