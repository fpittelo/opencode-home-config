#!/usr/bin/env python3
"""Enforce YAML front-matter validity for agents/*.md (#338 AC1-AC2).

Closes the defect class from #325: corrupted front-matter passed CI because
the namespace-exclusivity checker is indentation-insensitive. This gate
structurally parses the front-matter block of every agents/*.md:

  1. Delimiter structure: the file must start with a ``---`` line and contain
     a closing ``---`` line (missing/malformed delimiters fail).
  2. YAML validity: the block must parse as YAML (PyYAML safe_load); parse
     errors fail with the offending line number.
  3. Duplicate keys: rejected (PyYAML silently overwrites duplicates by
     default, so a duplicate-key-rejecting loader is used).
  4. Mandatory fields (#338 AC2):
       - ``description``: non-empty string
       - ``mode``: string
       - ``model``: string matching ``openrouter/<slug>``
       - ``temperature``: number with 0 <= t <= 2
       - ``permission``: mapping with at least one key
     Unknown keys are allowed (forward compatibility) — only structure and
     the listed fields are enforced.

Scope note: PyYAML is used (available in the local gate environment and
preinstalled on GitHub ubuntu-latest runners). No general YAML engine is
re-implemented; the checker is scoped to the flat front-matter shape the
agent files actually use.

Usage: check_agent_frontmatter.py [REPO_ROOT]
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

MODEL_PREFIX = "openrouter/"
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0
MANDATORY_FIELDS = ("description", "mode", "model", "temperature", "permission")


class _DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys with their line number."""

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.YAMLError(
                    f"duplicate key {key!r} at line {key_node.start_mark.line + 1}"
                )
            seen.add(key)
        mapping: dict[object, object] = super().construct_mapping(node, deep=deep)
        return mapping


def extract_frontmatter(text: str) -> tuple[str | None, int | None, str | None]:
    """Extract the front-matter block.

    Returns ``(block_text, block_start_line, error)`` — exactly one of
    ``block_text``/``error`` is set. ``block_start_line`` is the 1-based line
    number of the first content line (for error reporting).
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip("\r") != "---":
        return None, None, "missing leading '---' delimiter on line 1"
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r") == "---":
            block = "\n".join(lines[1:index])
            return block, 2, None
    return None, None, "missing closing '---' delimiter"


def check_field(name: str, value: object, failures: list[str]) -> None:
    """Validate one mandatory field against the #338 AC2 schema."""
    if name == "description":
        if not isinstance(value, str) or not value.strip():
            failures.append(
                f"  'description' must be a non-empty string (got {value!r})"
            )
    elif name == "mode":
        if not isinstance(value, str):
            failures.append(f"  'mode' must be a string (got {value!r})")
    elif name == "model":
        if not isinstance(value, str) or not value.startswith(MODEL_PREFIX):
            failures.append(
                f"  'model' must be a string with the '{MODEL_PREFIX}<slug>' "
                f"shape (got {value!r})"
            )
    elif name == "temperature":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            failures.append(f"  'temperature' must be a number (got {value!r})")
        elif not TEMPERATURE_MIN <= value <= TEMPERATURE_MAX:
            failures.append(
                f"  'temperature' must be within "
                f"[{TEMPERATURE_MIN}, {TEMPERATURE_MAX}] (got {value!r})"
            )
    elif name == "permission":
        if not isinstance(value, dict) or not value:
            failures.append(
                "  'permission' must be a mapping with at least one key "
                f"(got {value!r})"
            )


def check_agent_file(path: Path, failures: list[str]) -> None:
    """Validate one agent markdown file, appending actionable failures."""
    rel = path.relative_to(path.parents[2])
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{rel}: unreadable ({exc})")
        return
    block, start_line, error = extract_frontmatter(text)
    if error is not None or block is None or start_line is None:
        failures.append(f"{rel}: {error}")
        return
    try:
        data = yaml.load(block, Loader=_DuplicateKeyLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            line_no = mark.line + 1 + (start_line - 1)
        else:
            line_no = start_line
        failures.append(f"{rel}: invalid YAML near line {line_no}: {exc}")
        return
    if not isinstance(data, dict):
        failures.append(f"{rel}: front matter must be a YAML mapping")
        return
    for field in MANDATORY_FIELDS:
        if field not in data:
            failures.append(f"{rel}: missing mandatory field '{field}'")
            continue
        field_failures: list[str] = []
        check_field(field, data[field], field_failures)
        failures.extend(f"{rel}:{failure}" for failure in field_failures)


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    agent_files = sorted((root / "agents").glob("*.md"))
    if not agent_files:
        print("FAIL check_agent_frontmatter: no agents/*.md files found")
        return 1
    failures: list[str] = []
    for path in agent_files:
        check_agent_file(path, failures)
    if failures:
        print(
            "FAIL check_agent_frontmatter: agents/*.md front-matter validity "
            "violated:"
        )
        for failure in failures:
            print(failure)
        return 1
    names = ", ".join(str(p.relative_to(root)) for p in agent_files)
    print(
        "PASS check_agent_frontmatter: all "
        f"{len(agent_files)} agents/*.md front-matter blocks are valid YAML "
        "with the mandatory schema (description, mode, openrouter/<slug> "
        "model, temperature in [0, 2], non-empty permission mapping) — #338 "
        f"[{names}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
