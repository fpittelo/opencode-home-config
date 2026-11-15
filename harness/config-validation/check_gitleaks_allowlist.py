#!/usr/bin/env python3
"""Fail-closed gitleaks-allowlist + tracked-runtime-artifact gate (#448, gate 18).

Incident #448: a wide ``git add -A`` swept ``service.json`` — an untracked
opencode runtime artifact holding a local daemon credential — into commit
``fd15509…``, where it stayed publicly readable for 22 days until Deep
Validation's full-history gitleaks scan caught it. The credential is dead
(rotated; HTTP 401 as of 2026-11-15) and disposition (B) "rotate + document"
was accepted, so the historical finding is allowlisted — narrowly.

Two fail-closed assertions:

  1. **Tracked artifacts** — no opencode runtime artifact (``service.json``,
     ``cli.json``) is ever tracked (``git ls-files``). This closes the #405
     defect class: the file may exist untracked (the daemon writes it), but it
     must never enter the index. Fail-closed when git cannot answer.
  2. **Allowlist shape** — ``.gitleaks.toml`` carries **exactly one** allowlist
     entry, attached to a *rule* (the global ``[allowlist]`` table in
     gitleaks v8.24.3 has no ``condition`` field and matches with OR
     semantics, which would turn a path entry into a blanket waiver), scoped by
     ``condition = "AND"`` to the public incident commit AND the artifact path,
     with the path regex fully anchored — and the file carries no secret
     material (no value-shaped literal, no sha256 digest, no password
     assignment).

Usage: check_gitleaks_allowlist.py [REPO_ROOT]
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

# Public incident facts — the ONLY secret-adjacent material allowed in the repo
# (the commit sha and the path). The credential value is never referenced.
PUBLIC_COMMIT = "fd15509fa6cebebbb8bd02bd7a50caa639a7588a"
ALLOWLISTED_PATH = "service.json"
RUNTIME_ARTIFACTS = ("service.json", "cli.json")

# Detection thresholds for "value-shaped token": the leaked credential was a
# 43-character mixed-charset token (entropy 4.868) with no whitespace. Prose,
# paths and URLs in this file stay below the cut, and hex digests are handled
# by their own rule.
MIN_SECRET_LENGTH = 40
MIN_SECRET_ENTROPY = 4.0
MIN_CHARSET_CLASSES = 3
SHA256_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
PASSWORD_ASSIGNMENT_RE = re.compile(r"(?i)\bpassword\b\s*[:=]\s*[\"']?[^\s\"']{6,}")
HEX_RE = re.compile(r"[0-9a-fA-F]+")
TOKEN_STRIP = "\"'`.,;:()[]{}<>=|"
# Paths the allowlist regex must NOT match: a pattern that also matches these
# is a blanket waiver rather than an exact-path scope (#448 C3).
PATH_DECOYS = ("prefix/service.json", "service.json.bak", "cli.json")


def shannon_entropy(value: str) -> float:
    """Shannon entropy (bits per character) of a string."""
    if not value:
        return 0.0
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in Counter(value).values()
    )


def charset_classes(value: str) -> int:
    """Number of distinct character classes present (upper/lower/digit/symbol)."""
    classes = 0
    for predicate in (str.islower, str.isupper, str.isdigit):
        if any(predicate(char) for char in value):
            classes += 1
    if any(not char.isalnum() for char in value):
        classes += 1
    return classes


def is_value_shaped(token: str) -> bool:
    """True when a token looks like a credential value (never prose or a sha)."""
    if len(token) < MIN_SECRET_LENGTH or not token.isprintable():
        return False
    if HEX_RE.fullmatch(token) is not None:
        return False
    if charset_classes(token) < MIN_CHARSET_CLASSES:
        return False
    return shannon_entropy(token) >= MIN_SECRET_ENTROPY


def tracked_files(root: Path) -> list[str]:
    """Tracked paths from ``git ls-files``; raises RuntimeError when git fails."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git unavailable ({exc})") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        raise RuntimeError(
            f"git ls-files failed: {detail[0] if detail else 'unknown error'}"
        )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def allowlist_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """All allowlist entries declared by a parsed gitleaks config.

    The global table (``[allowlist]``) and every rule-level
    ``[[rules.allowlists]]`` entry count — "exactly one" means one in total.
    """
    entries: list[dict[str, Any]] = []
    global_allowlist = config.get("allowlist")
    if isinstance(global_allowlist, dict) and global_allowlist:
        entries.append(global_allowlist)
    rules = config.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            allowlists = rule.get("allowlists")
            if isinstance(allowlists, list):
                entries.extend(item for item in allowlists if isinstance(item, dict))
    return entries


def secret_material_findings(text: str) -> list[str]:
    """Findings for secret-shaped material in the allowlist file."""
    findings: list[str] = []
    if SHA256_RE.search(text):
        findings.append(
            ".gitleaks.toml: sha256-shaped digest present — the allowlist is "
            "commit+path scoped and must never carry a value hash (#448 C2)"
        )
    if PASSWORD_ASSIGNMENT_RE.search(text):
        findings.append(
            ".gitleaks.toml: password assignment present — secret material "
            "must never be written to the allowlist file (#448 C2)"
        )
    for raw in text.split():
        token = raw.strip(TOKEN_STRIP)
        if is_value_shaped(token):
            findings.append(
                ".gitleaks.toml: value-shaped token present (>= "
                f"{MIN_SECRET_LENGTH} chars, mixed charset, entropy >= "
                f"{MIN_SECRET_ENTROPY}) — secret material must never be "
                "written to the allowlist file (#448 C2)"
            )
            break
    return findings


def check_repo(root: Path) -> list[str]:
    """Return every finding for a repository tree (empty list = clean)."""
    findings: list[str] = []

    # Assertion 1 — no runtime artifact is tracked (the #405 class).
    try:
        tracked = tracked_files(root)
    except RuntimeError as exc:
        findings.append(
            f"tracked-artifact check: {exc} — cannot verify that no opencode "
            f"runtime artifact is tracked (fail-closed, #448 C5b/C6)"
        )
    else:
        for path in tracked:
            if Path(path).name in RUNTIME_ARTIFACTS:
                findings.append(
                    f"{path}: opencode runtime artifact is TRACKED — it must "
                    f"stay untracked/ignored (the #405 `git add -A` class; "
                    f"incident #448 C5b/C6)"
                )

    # Assertion 2 — the incident allowlist is exact and clean.
    config_path = root / ".gitleaks.toml"
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            f".gitleaks.toml: unreadable ({exc}) — the #448 allowlist is required"
        )
        return findings
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        findings.append(f".gitleaks.toml: unparsable TOML ({exc})")
        return findings

    findings.extend(secret_material_findings(text))

    entries = allowlist_entries(config)
    if len(entries) != 1:
        findings.append(
            ".gitleaks.toml: expected exactly one allowlist entry (the #448 "
            f"incident), found {len(entries)} — extra entries are unreviewed "
            "waivers (#448 C3)"
        )
        return findings

    entry = entries[0]
    commits = entry.get("commits")
    if not isinstance(commits, list) or commits != [PUBLIC_COMMIT]:
        findings.append(
            ".gitleaks.toml: allowlist entry must be scoped to exactly the "
            f"public incident commit {PUBLIC_COMMIT} (found commits={commits!r}) "
            "— a path-only waiver would mask future commits at that path "
            "(#448 C2/C3)"
        )

    condition = str(entry.get("condition", "")).upper()
    if condition != "AND":
        findings.append(
            ".gitleaks.toml: allowlist entry must declare condition = \"AND\" "
            f"(found {condition or 'none'!r}) — OR semantics make the path "
            "component a blanket waiver (#448 C3)"
        )

    paths = entry.get("paths")
    if not isinstance(paths, list) or len(paths) != 1:
        findings.append(
            ".gitleaks.toml: allowlist entry must carry exactly one path regex "
            f"for {ALLOWLISTED_PATH} (found {paths!r}) (#448 C2)"
        )
    else:
        pattern = str(paths[0])
        try:
            matcher = re.compile(pattern)
        except re.error as exc:
            findings.append(f".gitleaks.toml: allowlist path regex invalid ({exc})")
        else:
            if matcher.fullmatch(ALLOWLISTED_PATH) is None:
                findings.append(
                    ".gitleaks.toml: allowlist path regex must match "
                    f"{ALLOWLISTED_PATH!r} exactly and fully anchored (found "
                    f"{pattern!r}) — a broad regex would waive other paths "
                    "(#448 C3)"
                )
            decoy = next(
                (
                    candidate
                    for candidate in PATH_DECOYS
                    if matcher.search(candidate) is not None
                ),
                None,
            )
            if decoy is not None:
                findings.append(
                    ".gitleaks.toml: allowlist path regex "
                    f"{pattern!r} also matches {decoy!r} — it must match only "
                    f"{ALLOWLISTED_PATH!r} exactly (broad patterns are blanket "
                    "waivers, #448 C3)"
                )

    extra = sorted(set(entry) - {"description", "condition", "commits", "paths"})
    if extra:
        findings.append(
            ".gitleaks.toml: allowlist entry carries unexpected keys "
            f"{extra} — only description/condition/commits/paths are permitted "
            "(value-bearing keys are forbidden, #448 C2)"
        )

    description = str(entry.get("description", ""))
    lowered = description.lower()
    missing: list[str] = []
    if "448" not in description:
        missing.append("incident reference (#448)")
    if "dead" not in lowered and "rotated" not in lowered:
        missing.append("rotation/dead status")
    if "2027" not in description:
        missing.append("review-by date")
    if missing:
        findings.append(
            ".gitleaks.toml: allowlist description must record "
            f"{', '.join(missing)} (#448 C4)"
        )
    return findings


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    findings = check_repo(root)
    if findings:
        print("FAIL check_gitleaks_allowlist: allowlist gate violated:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(
        "PASS check_gitleaks_allowlist: no opencode runtime artifact tracked; "
        "exactly one commit+path AND-scoped gitleaks allowlist entry, free of "
        "secret material — #448"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
