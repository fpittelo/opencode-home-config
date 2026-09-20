#!/usr/bin/env python3
"""Validate the MADR schema of docs/adr/NNNN-*.md (AC3 of #61).

Implements the machine-checkable schema of skills/madr-adr/SKILL.md §3 exactly:
H1 header (number must equal the filename number), Status, Date and Deciders
fields, the five mandatory H2 sections in order, the file-naming pattern, and
unique gap-free sequence numbers from 0001. docs/adr/README.md is skipped.
Secret scanning is owned by gitleaks in CI, not by this script.

Usage: check_madr.py [REPO_ROOT]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ADR_DIR = "docs/adr"
README = "README.md"
H1_RE = re.compile(r"^# MADR-(\d{4}): .+$")
STATUS_RE = re.compile(
    r"^- \*\*Status:\*\* (proposed|accepted|superseded|deprecated)"
    r"( \(superseded by MADR-\d{4}\))?$"
)
DATE_RE = re.compile(r"^- \*\*Date:\*\* \d{4}-\d{2}-\d{2}$")
DECIDERS_RE = re.compile(r"^- \*\*Deciders:\*\* .+$")
NAME_RE = re.compile(r"^(\d{4})-([a-z0-9-]+)\.md$")
MANDATORY_SECTIONS = (
    "## Context",
    "## Decision Drivers",
    "## Considered Options",
    "## Decision Outcome",
    "## Consequences",
)


def check_adr(path: Path, number: int) -> list[str]:
    """Schema-check one ADR file; return its list of violations."""
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    first_non_blank = next((line for line in lines if line.strip()), "")
    m = H1_RE.match(first_non_blank)
    if not m:
        errors.append("H1 header missing or malformed (expected '# MADR-NNNN: <title>')")
    elif int(m.group(1)) != number:
        errors.append(f"H1 number {m.group(1)} does not match filename number {number:04d}")
    for label, rx in (("Status", STATUS_RE), ("Date", DATE_RE), ("Deciders", DECIDERS_RE)):
        if not any(rx.match(line) for line in lines):
            errors.append(f"missing or malformed {label} field")
    positions = [
        next((i for i, line in enumerate(lines) if line.strip() == section), None)
        for section in MANDATORY_SECTIONS
    ]
    if None in positions:
        for section, pos in zip(MANDATORY_SECTIONS, positions):
            if pos is None:
                errors.append(f"missing mandatory section '{section}'")
    elif positions != sorted(positions):
        errors.append(
            "mandatory sections out of required order: " + ", ".join(MANDATORY_SECTIONS)
        )
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    adr_dir = root / ADR_DIR
    if not adr_dir.is_dir():
        print(f"FAIL check_madr: missing directory {ADR_DIR}")
        return 1
    errors: list[str] = []
    numbers: list[int] = []
    conforming = 0
    for entry in sorted(adr_dir.iterdir()):
        if not entry.is_file() or entry.suffix != ".md" or entry.name == README:
            continue
        m = NAME_RE.match(entry.name)
        if not m:
            errors.append(f"{ADR_DIR}/{entry.name}: "
                          f"file name violates pattern 'NNNN-<lowercase-slug>.md'")
            continue
        number = int(m.group(1))
        numbers.append(number)
        file_errors = check_adr(entry, number)
        errors.extend(f"{ADR_DIR}/{entry.name}: {e}" for e in file_errors)
        if not file_errors:
            conforming += 1
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    for n in duplicates:
        names = ", ".join(p.name for p in sorted(adr_dir.glob(f"{n:04d}-*.md")))
        errors.append(f"{ADR_DIR}: duplicate sequence number {n:04d} (files: {names})")
    unique = sorted(set(numbers))
    if unique:
        missing = sorted(set(range(1, max(unique) + 1)) - set(unique))
        if missing:
            errors.append(f"{ADR_DIR}: sequence gap - missing number(s): "
                          + ", ".join(f"{n:04d}" for n in missing))
    if errors:
        print("FAIL check_madr: non-conforming ADR(s):")
        for error in errors:
            print(f"  {error}")
        return 1
    if conforming == 0:
        print(f"PASS check_madr: no ADRs found in {ADR_DIR} (nothing to validate)")
        return 0
    print(f"PASS check_madr: {conforming} ADR(s) conforming in {ADR_DIR}: "
          + ", ".join(f"{n:04d}" for n in unique))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
