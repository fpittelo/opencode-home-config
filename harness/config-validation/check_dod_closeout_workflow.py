#!/usr/bin/env python3
"""Machine gate for the DoD closeout signal workflow (#481, AC11/R5-C12).

The closeout signal's blast radius must be machine-checkable so the
report-only contract (AC10) cannot regress silently on the next workflow
edit. This gate asserts, on THREE files:

``.github/workflows/dod-closeout.yml``:
  1. **AC2 (MADR-0026 pattern)** — a job-level ``permissions:`` mapping that
     is EXACTLY ``{contents: read, checks: read, statuses: read,
     pull-requests: read, issues: write}`` (``statuses: read`` is mandatory:
     the DV verdict is a legacy commit status, R5-C1, not a check run), NO
     top-level ``permissions:`` block, exactly one job, every
     ``actions/checkout`` step with ``persist-credentials: false``.
  2. **AC2 (credential hygiene)** — the built-in ``${{ github.token }}`` is
     the only token surface: zero ``secrets.*`` references, no PAT.
  3. **AC1/AC9** — the trigger is exactly ``push`` to ``branches: [main]``,
     and the ``concurrency`` group exists (duplicate-comment prevention).
  4. **AC12 integrity** — the run step invokes
     ``harness/dod_closeout_verify.py``, the module the Tier A verifier
     suite (gate 18) pins: the unittest-covered logic is the executed logic.
  5. **AC10** — zero non-zero exits and zero issue-close/label/status-write
     call shapes anywhere in the workflow text.

``harness/dod_closeout_verify.py`` (the actual API/write surface — the
workflow itself performs no GitHub calls):
  6. **AC10 (write surface)** — every ``-X POST``/``-X PATCH`` line targets
     issue comments (create ``issues/<n>/comments`` or update
     ``issues/comments/<id>``); zero ``-X DELETE``/``-X PUT``, zero
     ``gh issue``/``gh pr``/``gh label`` subcommands, zero ``secrets.*``,
     zero ``status::`` label strings, and the always-exit-0 contract (no
     non-zero exit shape).
  7. **AC6/AC4 parity** — the reviewer identity literals (login
     ``devfpittelo`` AND id ``327061373``, parity with
     ``harness/probes/verify-github-identities.py``), the
     ``deep-validation`` status context and the hidden comment marker are
     pinned; the comment template states the report-only contract.

``.github/workflows/ci.yml`` (AC4 preconditions):
  8. The CI verdict inside the verifier is name-scoped (the ``actions: read``
     scope is deliberately excluded by AC2, so the workflow-runs API cannot
     link check suites to workflows). The scoping is exact only while
     ``ci.yml`` stays the single-job ``CI Pipeline`` workflow whose job name
     matches the verifier constant — a rename or a second job is a finding,
     forcing the scoping to be consciously re-validated.

YAML structure is parsed with ``yaml`` (the house dependency of
``check_agent_frontmatter.py``); write-surface and exit semantics are
asserted at grep level on the raw text, by design (the invariants must be
checkable without executing anything — the check_pin_freshness_workflow.py
precedent).

Usage: check_dod_closeout_workflow.py [REPO_ROOT]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

WORKFLOW_REL = Path(".github/workflows/dod-closeout.yml")
VERIFIER_REL = Path("harness/dod_closeout_verify.py")
CI_WORKFLOW_REL = Path(".github/workflows/ci.yml")

ALLOWED_PERMISSIONS = {
    "contents": "read",
    "checks": "read",
    "statuses": "read",
    "pull-requests": "read",
    "issues": "write",
}
CI_WORKFLOW_NAME = "CI Pipeline"
CI_CHECK_RUN_NAME = "Quality Gate (native, zero Docker)"
VERIFIER_INVOCATION = "python3 harness/dod_closeout_verify.py"
COMMENT_MARKER = "<!-- dod-closeout-signal -->"
REVIEWER_LOGIN = "devfpittelo"
REVIEWER_ID = "327061373"
DV_CONTEXT = "deep-validation"
REPORT_ONLY_PHRASE = "does not close the DoD gate"

# Raw-text forbiddens with their invariant tags. The workflow is shell text
# (forbidden shapes are shell forms); the verifier is Python source, where
# gh CLI subcommands and HTTP verbs appear as argv lists — both spellings
# are pinned so neither can regress. label/close/status writes are R5-C10.
WORKFLOW_FORBIDDEN = (
    ("secrets.", "AC2"),
    ("gh issue ", "AC10"),
    ("gh pr ", "AC10"),
    ("--label", "AC10"),
    ("add-label", "AC10"),
    ("-X DELETE", "AC10"),
    ("-X PUT", "AC10"),
)
VERIFIER_FORBIDDEN = (
    ("secrets.", "AC2"),
    ('"gh", "issue"', "AC10"),
    ('"gh", "pr"', "AC10"),
    ('"gh", "label"', "AC10"),
    ("gh issue ", "AC10"),
    ("gh pr ", "AC10"),
    ("--label", "AC10"),
    ("add-label", "AC10"),
    ('"-X", "DELETE"', "AC10"),
    ('"-X", "PUT"', "AC10"),
    ('"-X DELETE"', "AC10"),
    ('"-X PUT"', "AC10"),
    ("status::", "AC10"),
)
NONZERO_EXIT_RE = re.compile(r"\bexit [1-9]\b")
VERIFIER_EXIT_RE = re.compile(
    r"\bsys\.exit\b|\bSystemExit\b|\bexit\([1-9]|\breturn [1-9]\b"
)
WRITE_LINE_RE = re.compile(r"\"-X\",\s*\"(POST|PATCH)\"")


def _workflow_findings(workflow: dict[str, Any]) -> list[str]:
    """Structural (parsed-YAML) assertions for dod-closeout.yml."""
    findings: list[str] = []
    if "permissions" in workflow:
        findings.append(
            "top-level permissions block present — permissions must be "
            f"declared at job level only, exactly {ALLOWED_PERMISSIONS} (AC2)"
        )
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        findings.append("no jobs defined in dod-closeout.yml (AC2)")
        return findings
    if len(jobs) != 1:
        findings.append(
            f"exactly one job is pinned (the single-job report-only design, "
            f"KIS), found {len(jobs)}"
        )
    for name, job in jobs.items():
        if not isinstance(job, dict):
            findings.append(f"job {name!r}: not a mapping (AC2)")
            continue
        permissions = job.get("permissions")
        if permissions is None:
            findings.append(
                f"job {name!r}: permissions missing — job-level permissions "
                f"must be exactly {ALLOWED_PERMISSIONS} (AC2)"
            )
        elif permissions != ALLOWED_PERMISSIONS:
            findings.append(
                f"job {name!r}: permissions must be exactly "
                f"{ALLOWED_PERMISSIONS} (AC2; statuses: read is mandatory — "
                f"the DV verdict is a legacy commit status, R5-C1), "
                f"found {permissions!r}"
            )
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses", ""))
            if "actions/checkout" in uses:
                with_block = step.get("with") or {}
                if with_block.get("persist-credentials") is not False:
                    findings.append(
                        f"checkout step in job {name!r} must set "
                        "persist-credentials: false (AC2), found "
                        f"{with_block.get('persist-credentials')!r}"
                    )
            run_block = step.get("run") or ""
            if isinstance(run_block, str) and VERIFIER_INVOCATION in run_block:
                break
        else:
            findings.append(
                f"job {name!r}: no step invokes '{VERIFIER_INVOCATION}' — the "
                "unittest-covered verifier module must be the executed logic "
                "(AC12 integrity)"
            )
    # AC1: the trigger is exactly push to main. NOTE: yaml.safe_load parses
    # the `on:` key as boolean True (YAML 1.1 truthiness) — accept both.
    on_block = workflow.get("on", workflow.get(True))
    if not isinstance(on_block, dict) or set(on_block) != {"push"}:
        findings.append(
            "the trigger must be exactly on.push (branches: [main]) — no "
            "schedule/pull_request/workflow_dispatch trigger is pinned (AC1)"
        )
    else:
        push = on_block.get("push")
        if not isinstance(push, dict) or push.get("branches") != ["main"]:
            findings.append(
                "on.push.branches must be exactly [main] (AC1), found "
                f"{push!r}"
            )
    concurrency = workflow.get("concurrency")
    if not isinstance(concurrency, dict) or not concurrency.get("group"):
        findings.append(
            "concurrency group missing — concurrent pushes must serialize to "
            "prevent duplicate signal comments (AC9)"
        )
    return findings


def strip_comment_lines(text: str) -> str:
    """Drop full-line YAML comments before grep-level matching — the gate
    must judge CODE, never the prose that documents it (a workflow comment
    legitimately cites the invariants it implements)."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _workflow_text_findings(text: str) -> list[str]:
    """Grep-level assertions on the workflow's code text (by design)."""
    findings: list[str] = []
    code = strip_comment_lines(text)
    for needle, invariant in WORKFLOW_FORBIDDEN:
        if needle in code:
            findings.append(
                f"{needle!r} present in dod-closeout.yml — forbidden ({invariant})"
            )
    exit_hit = NONZERO_EXIT_RE.search(code)
    if exit_hit is not None:
        findings.append(
            f"non-failing design violated: `{exit_hit.group(0)}` present in "
            "dod-closeout.yml — the workflow always exits 0 (AC10)"
        )
    if "${{ github.token }}" not in code:
        findings.append(
            "built-in token ${{ github.token }} absent — it is the only "
            "permitted credential surface (AC2)"
        )
    return findings


def _verifier_findings(text: str) -> list[str]:
    """Write-surface, exit and identity-parity pins for the verifier module.

    Identity/context/marker/phrase pins match the exact ASSIGNMENT shapes —
    bare literals would be defeated by docstring mentions and could never
    catch a drifted value.
    """
    findings: list[str] = []
    for needle, invariant in VERIFIER_FORBIDDEN:
        if needle in text:
            findings.append(
                f"{needle!r} present in dod_closeout_verify.py — forbidden "
                f"({invariant})"
            )
    exit_hit = VERIFIER_EXIT_RE.search(text)
    if exit_hit is not None:
        findings.append(
            f"non-failing design violated: `{exit_hit.group(0)}` present in "
            "dod_closeout_verify.py — the verifier always exits 0 (AC10)"
        )
    pinned_assignments = (
        (f'REVIEWER_LOGIN = "{REVIEWER_LOGIN}"', "reviewer login parity with the identity probe (AC6)"),
        (f"REVIEWER_ID = {REVIEWER_ID}", "reviewer id parity with the identity probe (AC6, #423)"),
        (f'DV_CONTEXT = "{DV_CONTEXT}"', "the deep-validation legacy status context (AC5)"),
        (f'CI_CHECK_RUN_NAME = "{CI_CHECK_RUN_NAME}"', "the CI Pipeline check-run name scope (AC4)"),
        (f'COMMENT_MARKER = "{COMMENT_MARKER}"', "the hidden one-comment-per-issue marker (AC9)"),
        (f'signal_phrase = "{REPORT_ONLY_PHRASE}"', "the comment must state the signal-not-gate contract (AC10/AC11)"),
    )
    for assignment, why in pinned_assignments:
        if assignment not in text:
            findings.append(
                f"verifier assignment {assignment!r} missing — {why}"
            )
    # Write-surface allowlist: every POST/PATCH line targets issue comments.
    for line in text.splitlines():
        if WRITE_LINE_RE.search(line) is None:
            continue
        if "issues/" not in line or "comments" not in line:
            findings.append(
                f"write surface violated: {line.strip()!r} — the only "
                "permitted writes are issue-comment create/update "
                "(issues/<n>/comments, issues/comments/<id>); zero "
                "issue-close/label/status/check-run writes (AC10/AC11, "
                "issue-comment write surface)"
            )
    return findings


def _ci_findings(ci_workflow: dict[str, Any] | None) -> list[str]:
    """AC4 preconditions: the CI-scoping source of truth stays exact."""
    findings: list[str] = []
    if not isinstance(ci_workflow, dict):
        findings.append(
            f"{CI_WORKFLOW_REL}: unparsable or missing — the AC4 CI-scoping "
            "precondition cannot be verified (fail-closed)"
        )
        return findings
    if ci_workflow.get("name") != CI_WORKFLOW_NAME:
        findings.append(
            f"ci.yml workflow name must be exactly {CI_WORKFLOW_NAME!r} — the "
            "verifier's CI verdict is scoped to that workflow's check runs "
            f"(AC4), found {ci_workflow.get('name')!r}"
        )
    jobs = ci_workflow.get("jobs")
    if not isinstance(jobs, dict) or len(jobs) != 1:
        findings.append(
            f"ci.yml must declare exactly one job (the verifier's CI verdict "
            f"is name-scoped to it, AC4), found "
            f"{len(jobs) if isinstance(jobs, dict) else 'invalid'}"
        )
        return findings
    job = next(iter(jobs.values()))
    job_name = job.get("name") if isinstance(job, dict) else None
    if job_name != CI_CHECK_RUN_NAME:
        findings.append(
            f"the ci.yml job name must stay {CI_CHECK_RUN_NAME!r} — the "
            "verifier scopes the CI verdict to check runs with this exact "
            f"name (AC4; actions: read is excluded by AC2), found {job_name!r}"
        )
    return findings


def check_repo(root: Path) -> list[str]:
    """Return every finding for a repository tree (empty list = clean)."""
    findings: list[str] = []

    workflow_path = root / WORKFLOW_REL
    try:
        workflow_text = workflow_path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            f"{WORKFLOW_REL}: unreadable/missing ({exc}) — the gate is "
            "fail-closed (AC11)"
        )
        workflow_text = None
    if workflow_text is not None:
        try:
            workflow = yaml.safe_load(workflow_text)
        except yaml.YAMLError as exc:
            findings.append(f"{WORKFLOW_REL}: unparsable YAML ({exc})")
            workflow = None
        if isinstance(workflow, dict):
            findings.extend(_workflow_findings(workflow))
            findings.extend(_workflow_text_findings(workflow_text))
        elif workflow is not None:
            findings.append(f"{WORKFLOW_REL}: YAML root is not a mapping")

    verifier_path = root / VERIFIER_REL
    try:
        verifier_text = verifier_path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(
            f"{VERIFIER_REL}: unreadable/missing ({exc}) — the gate is "
            "fail-closed (AC11)"
        )
    else:
        findings.extend(_verifier_findings(verifier_text))

    ci_path = root / CI_WORKFLOW_REL
    try:
        ci_workflow = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        ci_workflow = None
        findings.append(
            f"{CI_WORKFLOW_REL}: unreadable/unparsable ({exc}) — the AC4 "
            "CI-scoping precondition check fails closed"
        )
    findings.extend(_ci_findings(ci_workflow if isinstance(ci_workflow, dict) else None))
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
        print("FAIL check_dod_closeout_workflow: DoD closeout gate violated:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(
        "PASS check_dod_closeout_workflow: dod-closeout.yml matches the "
        "report-only contract — exact job permissions, built-in token only, "
        "comment-only write surface, always exit 0, single-job CI scoping "
        "pinned (#481, AC11/R5-C12)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
