#!/usr/bin/env python3
"""Validate relative markdown links and <img src> paths in the HOME doc set (AC2 of #61).

Doc set: docs/**/*.md, README.md, agents/**/*.md, skills/**/*.md.
Checks [text](target) links and <img src="..."> tags whose target is relative;
verifies target files exist and resolves #anchors against the target file's
headings (GitHub slug rules). External URLs (any scheme://), mailto: and
anchor-only links are out of scope by design (ADR-0001: no network egress).

Usage: check_links.py [REPO_ROOT]
"""
from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

DOC_GLOBS = ("docs/**/*.md", "agents/**/*.md", "skills/**/*.md")
FENCE_RE = re.compile(r"^ {0,3}(`{3,})(.*)$")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
IMG_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def doc_files(root: Path) -> list[Path]:
    """Deterministically ordered markdown files of the doc set."""
    files = {p for pattern in DOC_GLOBS for p in root.glob(pattern) if p.is_file()}
    readme = root / "README.md"
    if readme.is_file():
        files.add(readme)
    return sorted(files)


def github_slug(heading_text: str) -> str:
    """GitHub-style anchor slug: lowercase, strip punctuation, spaces to hyphens."""
    text = heading_text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def collect_headings(text: str) -> set[str]:
    """Anchor slugs of all headings, ignoring anything inside fenced blocks."""
    slugs: set[str] = set()
    fence_len: int | None = None
    for line in text.splitlines():
        m = FENCE_RE.match(line)
        if fence_len is None:
            if m:
                fence_len = len(m.group(1))
                continue
            hm = HEADING_RE.match(line)
            if hm:
                slugs.add(github_slug(hm.group(2)))
        elif m and len(m.group(1)) >= fence_len and not m.group(2).strip():
            fence_len = None
    return slugs


def scan_line(line: str) -> list[str]:
    """Markdown link and <img src> targets on one line, ignoring inline code spans."""
    targets: list[str] = []
    for segment in INLINE_CODE_RE.split(line):
        targets.extend(m.group(1) for m in MARKDOWN_LINK_RE.finditer(segment))
        targets.extend(m.group(1) for m in IMG_SRC_RE.finditer(segment))
    return targets


def classify(target: str) -> tuple[str, str] | None:
    """Return (path_part, anchor_part) for in-scope relative targets, else None."""
    if not target or target.startswith("#") or SCHEME_RE.match(target):
        return None
    path, sep, anchor = target.partition("#")
    return path, anchor if sep else ""


def parse_dest(raw: str) -> str:
    """Extract the link destination: first token, or the <angle-bracketed> form."""
    dest = raw.strip()
    if dest.startswith("<") and ">" in dest:
        return dest[1:dest.index(">")]
    tokens = dest.split()
    return tokens[0] if tokens else ""


def verify(path: Path, parsed: tuple[str, str],
           heading_cache: dict[Path, set[str]]) -> str | None:
    """Return an error reason if the relative target is broken, else None."""
    raw_path, anchor = parsed
    dest = parse_dest(raw_path)
    if not dest:
        return None
    resolved = (path.parent / urllib.parse.unquote(dest)).resolve()
    if not resolved.exists():
        return "target does not exist"
    if anchor and resolved.suffix == ".md":
        slugs = heading_cache.setdefault(
            resolved, collect_headings(resolved.read_text(encoding="utf-8")))
        if anchor not in slugs:
            return f"anchor '#{anchor}' not found in {dest}"
    return None


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    failures: list[str] = []
    checked = 0
    files = doc_files(root)
    heading_cache: dict[Path, set[str]] = {}
    for path in files:
        fence_len: int | None = None
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = FENCE_RE.match(line)
            if fence_len is None:
                if m:
                    fence_len = len(m.group(1))
                    continue
                for target in scan_line(line):
                    parsed = classify(target)
                    if parsed is None:
                        continue
                    checked += 1
                    reason = verify(path, parsed, heading_cache)
                    if reason:
                        failures.append(f"{path.relative_to(root)}:{lineno}: "
                                        f"broken relative link '{target}' ({reason})")
            elif m and len(m.group(1)) >= fence_len and not m.group(2).strip():
                fence_len = None
    if failures:
        print("FAIL check_links: broken relative link(s):")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"PASS check_links: {checked} relative link(s)/img src verified "
          f"in {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
