#!/usr/bin/env python3
"""Machine gate for the MADR-0026 pin-freshness workflow (#446, gate 19).

MADR-0026 C6: the O3 workflow's blast radius must be machine-checkable so
C1+C5 cannot regress silently on the next workflow edit. This gate asserts,
on ``.github/workflows/pin-freshness.yml``:

  1. **C1 (least privilege)** — a job-level ``permissions:`` mapping that is
     exactly ``{contents: read, issues: write}`` (no top-level permissions
     block, no extra keys, none of ``contents: write`` /
     ``pull-requests: write`` / ``actions: write`` / ``id-token`` anywhere),
     and every ``actions/checkout`` step runs with
     ``persist-credentials: false``.
  2. **C4/C5 (credential hygiene)** — the built-in ``${{ github.token }}`` is
     the only token surface: zero ``secrets.*`` references, no PAT env vars.
  3. **C11 (tri-state, non-failing)** — all three states appear, explicit
     ``unknown`` failure paths exist (>= 2 assignments), ``fresh`` is assigned
     exactly once (the semver-comparison outcome — never on a failure or
     ``||`` fallback branch), warnings annotate inconclusive runs, a job
     summary is written, and the script never exits non-zero.
  4. **AC1 cadence** — weekly Monday cron staggered off the
     ``deep-validation.yml`` slot (fail-closed when that file is missing) +
     ``workflow_dispatch``.
  5. **C7–C10 (drift-issue mechanics)** — the hidden managed-issue marker,
     the fixed ``agent::devops`` + ``type::task`` labels, the
     ``@devfpittelo`` review statement, the asset/checksums naming, the
     authenticated ``releases/latest`` read — and zero ``status::`` labels,
     zero auto-close, zero ``actions/cache`` state, zero second version
     literals (C2: ``install.sh`` stays the single pin).

YAML structure is parsed with ``yaml`` (already the house dependency of
``check_agent_frontmatter.py``); the failure-path logic inside ``run:``
blocks is asserted at grep level on the raw text, by design (C6: the
invariants must be checkable without executing anything).

Usage: check_pin_freshness_workflow.py [REPO_ROOT]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

WORKFLOW_REL = Path(".github/workflows/pin-freshness.yml")
DEEP_WORKFLOW_REL = Path(".github/workflows/deep-validation.yml")
ALLOWED_PERMISSIONS = {"contents": "read", "issues": "write"}
DRIFT_LABELS = ("agent::devops", "type::task")
MANAGED_MARKER = "<!-- pin-freshness:managed-issue -->"
UPSTREAM_REPO = "github/github-mcp-server"
ASSET_NAME = "github-mcp-server_Linux_x86_64.tar.gz"

# Raw-text forbiddens with their MADR-0026 invariant tags (C1/C2/C5/C10).
FORBIDDEN = (
    ("secrets.", "C5"),
    ("contents: write", "C1"),
    ("pull-requests: write", "C1"),
    ("actions: write", "C1"),
    ("id-token", "C1"),
    ("status::", "C10"),
    ("gh issue close", "C10"),
    ("actions/cache", "C2"),
)
FRESH_FALLBACK_RE = re.compile(r"\|\|[^\n]*\bfresh\b")
EXIT_NONZERO_RE = re.compile(r"\bexit [1-9]\b")
VERSION_LITERAL_RE = re.compile(r"\bv?\d+\.\d+\.\d+")
UNKNOWN_ASSIGN_RE = re.compile(r"RESULT=[\"']?unknown")
FRESH_ASSIGN_RE = re.compile(r"RESULT=[\"']?fresh")
CRON_RE = re.compile(r"cron:\s*(?:[\"']([^\"']+)[\"']|([^\s#]+))")
MONDAY_DOW = {"1", "mon", "monday"}


def crons_of(text: str) -> list[str]:
    """Every cron expression declared in a workflow text (unquoted)."""
    return [
        match.group(1) or match.group(2) or ""
        for match in CRON_RE.finditer(text)
    ]


def is_monday(cron: str) -> bool:
    """True for a 5-field cron whose day-of-week field selects Monday."""
    fields = cron.split()
    return len(fields) == 5 and fields[4].lower() in MONDAY_DOW


def _structure_findings(workflow: dict[str, Any]) -> list[str]:
    """Structural (parsed-YAML) assertions for the pin-freshness workflow."""
    findings: list[str] = []
    if "permissions" in workflow:
        findings.append(
            "top-level permissions block present — permissions must be "
            "declared at job level only, exactly "
            f"{ALLOWED_PERMISSIONS} (MADR-0026 C1)"
        )
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        findings.append("no jobs defined in pin-freshness.yml (C1)")
        return findings
    for name, job in jobs.items():
        if not isinstance(job, dict):
            findings.append(f"job {name!r}: not a mapping (C1)")
            continue
        permissions = job.get("permissions")
        if permissions is None:
            findings.append(
                f"job {name!r}: permissions missing — job-level permissions "
                f"must be exactly {ALLOWED_PERMISSIONS} (MADR-0026 C1)"
            )
        elif permissions != ALLOWED_PERMISSIONS:
            findings.append(
                f"job {name!r}: permissions must be exactly "
                f"{ALLOWED_PERMISSIONS} (MADR-0026 C1), found {permissions!r}"
            )
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses", ""))
            if "actions/checkout" not in uses:
                continue
            with_block = step.get("with") or {}
            if with_block.get("persist-credentials") is not False:
                findings.append(
                    f"checkout step in job {name!r} must set "
                    "persist-credentials: false (MADR-0026 C1), found "
                    f"{with_block.get('persist-credentials')!r}"
                )
    return findings


def _text_findings(text: str) -> list[str]:
    """Grep-level assertions on the raw workflow text (by design, C6)."""
    findings: list[str] = []
    for needle, invariant in FORBIDDEN:
        if needle in text:
            findings.append(
                f"{needle!r} present in pin-freshness.yml — forbidden "
                f"({invariant})"
            )
    if FRESH_FALLBACK_RE.search(text) is not None:
        findings.append(
            "`||` fallback branch producing fresh — a failure path must map "
            "to unknown, never fresh (MADR-0026 C11 failure semantics)"
        )
    exit_hit = EXIT_NONZERO_RE.search(text)
    if exit_hit is not None:
        findings.append(
            f"non-failing design violated: `{exit_hit.group(0)}` present — "
            "drift/unknown must surface via annotation + summary with exit 0 "
            "(MADR-0026 C11)"
        )
    if VERSION_LITERAL_RE.search(text) is not None:
        findings.append(
            "second version literal present — the pin is read from "
            "install.sh at run time; no version literal may exist here "
            "(MADR-0026 C2)"
        )
    if "${{ github.token }}" not in text:
        findings.append(
            "built-in token ${{ github.token }} absent — it is the only "
            "permitted credential surface (MADR-0026 C4)"
        )
    unknown_assignments = len(UNKNOWN_ASSIGN_RE.findall(text))
    if unknown_assignments < 2:
        findings.append(
            "explicit unknown failure paths missing — RESULT=unknown must be "
            "assigned on every API/parse failure branch (MADR-0026 C11), "
            f"found {unknown_assignments}"
        )
    fresh_assignments = len(FRESH_ASSIGN_RE.findall(text))
    if fresh_assignments != 1:
        findings.append(
            "RESULT=fresh must be assigned exactly once (the "
            "semver-comparison outcome) — a fresh-on-failure branch defeats "
            f"C11 (found {fresh_assignments})"
        )
    if "::warning::" not in text:
        findings.append(
            "run annotation missing — inconclusive runs must emit a "
            "::warning:: (MADR-0026 C11)"
        )
    if "GITHUB_STEP_SUMMARY" not in text:
        findings.append(
            "job summary missing — every run must write GITHUB_STEP_SUMMARY "
            "(MADR-0026 C11)"
        )
    if "steps.detect.outputs" not in text:
        findings.append(
            "detection outputs not consumed — the reconcile step must read "
            "steps.detect.outputs.*"
        )
    if MANAGED_MARKER not in text:
        findings.append(
            "hidden managed-issue marker missing — the drift issue is "
            "located deterministically by this body marker (MADR-0026 C8)"
        )
    for label in DRIFT_LABELS:
        if label not in text:
            findings.append(
                f"fixed drift label {label} missing (MADR-0026 C8/C10)"
            )
    if "@devfpittelo" not in text:
        findings.append(
            "the issue body must state that a bump requires a PR reviewed "
            "by @devfpittelo — notification, not authorization (MADR-0026 C9)"
        )
    if ASSET_NAME not in text:
        findings.append(
            f"the exact asset to hash ({ASSET_NAME}) must be named in the "
            "issue body (MADR-0026 C9)"
        )
    if "checksums" not in text.lower():
        findings.append(
            "the checksums file (bump-time source of truth) must be named "
            "in the issue body (MADR-0026 C9)"
        )
    if "releases/latest" not in text:
        findings.append(
            "upstream releases/latest read missing (MADR-0026 C11)"
        )
    if UPSTREAM_REPO not in text:
        findings.append(
            f"upstream repository {UPSTREAM_REPO} missing (MADR-0026 O3)"
        )
    return findings


def _cadence_findings(pin_text: str, deep_text: str | None) -> list[str]:
    """AC1 cadence: Monday crons, staggered off the deep-validation slot."""
    findings: list[str] = []
    pin_crons = crons_of(pin_text)
    if not pin_crons:
        findings.append(
            "no cron under on.schedule — the weekly cadence is required (AC1)"
        )
    deep_crons: list[str] = []
    if deep_text is not None:
        deep_crons = crons_of(deep_text)
    for cron in pin_crons:
        if not is_monday(cron):
            findings.append(
                f"cron {cron!r} is not a Monday schedule (AC1: weekly "
                "Monday, MADR-0026 O3)"
            )
        if cron in deep_crons:
            findings.append(
                f"cron {cron!r} equals the deep-validation slot — the "
                "schedules must be staggered (AC1, correlated API pressure)"
            )
    return findings


def check_repo(root: Path) -> list[str]:
    """Return every finding for a repository tree (empty list = clean)."""
    findings: list[str] = []
    workflow_path = root / WORKFLOW_REL
    deep_path = root / DEEP_WORKFLOW_REL

    try:
        pin_text = workflow_path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            f"{WORKFLOW_REL}: unreadable/missing ({exc}) — gate 19 is "
            "fail-closed (MADR-0026 C6)"
        )
        return findings
    try:
        workflow = yaml.safe_load(pin_text)
    except yaml.YAMLError as exc:
        findings.append(f"{WORKFLOW_REL}: unparsable YAML ({exc})")
        return findings
    if not isinstance(workflow, dict):
        findings.append(f"{WORKFLOW_REL}: YAML root is not a mapping")
        return findings

    findings.extend(_structure_findings(workflow))
    findings.extend(_text_findings(pin_text))

    deep_text: str | None = None
    try:
        deep_text = deep_path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            f"{DEEP_WORKFLOW_REL}: unreadable/missing ({exc}) — the "
            "cron-stagger check fails closed (AC1)"
        )
    findings.extend(_cadence_findings(pin_text, deep_text))
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
        print("FAIL check_pin_freshness_workflow: pin-freshness gate violated:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(
        "PASS check_pin_freshness_workflow: pin-freshness.yml matches "
        "MADR-0026 C1-C12 — exact job permissions, built-in token only, "
        "tri-state failure paths, staggered Monday cron, deterministic "
        "drift issue (#446, gate 19)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
