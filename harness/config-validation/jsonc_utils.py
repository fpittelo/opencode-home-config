"""Shared JSONC comment-stripping helper for the config-validation checkers.

Single source of truth for ``strip_jsonc`` (#371, audit finding C3):
``check_coach_exclusivity.py``, ``check_browser_launch_flags.py`` and
``check_bash_permission_tiers.py`` import it instead of carrying private
copies. The shell-embedded copy in ``harness/run-config-gate.sh`` (gate 1)
stays — a bash heredoc cannot import Python.

The stripper removes ``//`` line comments while preserving string literals
(escape-aware), mirroring the JSONC dialect of ``opencode.jsonc``.
"""
from __future__ import annotations


def strip_jsonc(text: str) -> str:
    """Strip // comments (mirrors the run-config-gate JSONC validator)."""
    out: list[str] = []
    i, in_str, esc = 0, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and text[i + 1 : i + 2] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)