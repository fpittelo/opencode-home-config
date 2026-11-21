#!/usr/bin/env python3
"""DoD closeout signal verifier (#481) — report-only post-merge verification.

Executed by ``.github/workflows/dod-closeout.yml`` on every push to ``main``.
For the pushed squash-merge commit (``github.sha``, AC3) it verifies the five
machine-derivable DoD facts and posts/updates ONE line on the linked issue:

  1. squash merge into ``main`` (merged PR, base ``main``,
     ``merge_commit_sha == sha``, 1-parent commit, exactly 1 pushed commit);
  2. CI green on the exact sha — computed ONLY over the ``CI Pipeline``
     workflow's check runs, name-scoped to its single job (AC4; the
     ``actions: read`` scope is deliberately excluded by the AC2 permission
     set, so the workflow-runs API cannot be used);
  3. DV green on the exact sha — the durable deletion-evident
     ``deep-validation`` LEGACY COMMIT STATUS (#449 AC2b), re-evaluated over
     a bounded window; a not-yet-published status renders ``pending`` and is
     never a failure (AC5, MADR-0028);
  4. formal APPROVE by login ``devfpittelo`` AND id ``327061373`` (identity
     parity with ``harness/probes/verify-github-identities.py``, #423) and
     distinct from the PR author (AC6);
  5. issue<->PR traceability — the linked issue derived from GitHub's native
     closing-issue linkage only; zero or >1 candidates are unknown (AC7).

Contract (AC8-AC10): the comment body carries machine-derived values only
(sha, PR number, issue number, per-fact verdicts); at most one signal comment
per issue (hidden marker, updated in place); the workflow NEVER closes an
issue, never writes labels/statuses/check runs, and ALWAYS exits 0 — it is a
signal that does not close the DoD gate: ``@scrum-master`` remains the DoD
authority (home-governance §7; SoD: bot verifies, scrum-master acts).

The tri-state fact logic (this module's pure functions) is pinned by
``harness/config-validation/test_dod_closeout_verifier.py`` (Tier A gate 18,
#481 AC12/R5-C13); the workflow's blast radius is pinned by
``harness/config-validation/check_dod_closeout_workflow.py`` (gate 17).

Usage (workflow): python3 harness/dod_closeout_verify.py
Env: GITHUB_REPOSITORY, SHA, COMMITS_JSON, GH_TOKEN.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field

REVIEWER_LOGIN = "devfpittelo"
REVIEWER_ID = 327061373
DV_CONTEXT = "deep-validation"
# The single job of .github/workflows/ci.yml — the CI Pipeline workflow's
# check runs on the sha are identified by this name (AC4). The config gate
# (check_dod_closeout_workflow.py) pins this literal to ci.yml so a rename
# or a second ci.yml job can never silently narrow the CI verdict.
CI_CHECK_RUN_NAME = "Quality Gate (native, zero Docker)"
COMMENT_MARKER = "<!-- dod-closeout-signal -->"
# Bounded re-evaluation window (AC5): DV posts its status ~2.5 min after
# push (MADR-0028); the window covers CI + DV completion with margin and is
# finite by design. Poll cadence is coarse — every read is a cheap GET.
WINDOW_SECONDS = 420
POLL_SECONDS = 15
FAILURE_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}
)
FACT_ORDER: tuple[str, ...] = (
    "squash",
    "ci",
    "dv",
    "review",
    "traceability",
)
GREEN = "green"
RED = "red"
UNKNOWN = "unknown"
PENDING = "pending"
UNMET = "unmet"

GITHUB_API_TIMEOUT_SECONDS = 60


@dataclass
class Evaluation:
    """One evaluation pass over the pushed sha."""

    facts: dict[str, tuple[str, str]] = field(default_factory=dict)
    pr_number: int | None = None
    issue_number: int | None = None

    def final(self) -> bool:
        """Stop polling when the verdict can no longer change: all green
        (the signal condition) or any red fact (a failure is final)."""
        if not self.facts:
            return False
        if all(fact == GREEN for fact, _ in self.facts.values()):
            return True
        return any(fact == RED for fact, _ in self.facts.values())


def derive_issue_number(graphql_payload: object) -> int | None:
    """AC7: the linked issue from GitHub-native closing-issue linkage.

    Exactly one candidate yields its number; zero, more than one, or any
    unexpected payload shape renders unknown (None). No regex over the PR
    body or commit message ever selects the target issue.
    """
    if not isinstance(graphql_payload, dict):
        return None
    try:
        references = graphql_payload["data"]["repository"]["pullRequest"][
            "closingIssuesReferences"
        ]
        nodes = references["nodes"]
        total = references["totalCount"]
    except (KeyError, TypeError):
        return None
    if total != 1 or not isinstance(nodes, list) or len(nodes) != 1:
        return None
    number = nodes[0].get("number") if isinstance(nodes[0], dict) else None
    return number if isinstance(number, int) else None


def filter_merged_prs(candidates: list, sha: str) -> list[dict]:
    """Full-PR dicts that are merged with merge_commit_sha == sha (AC3)."""
    return [
        pr
        for pr in candidates
        if isinstance(pr, dict)
        and pr.get("merged") is True
        and pr.get("merge_commit_sha") == sha
    ]


def evaluate_squash_fact(
    pr: dict | None, sha: str, pushed_count: int | None, parent_count: int | None
) -> tuple[str, str]:
    """Fact 1: squash merge into main, evaluated on the pushed sha (AC3).

    A 2-parent commit is a merge-commit merge; a multi-commit push matching
    a merged PR is the rebase/direct-push shape — both violate the squash
    protocol and are determinably red. Missing inputs render unknown, never
    green (AC4).
    """
    if pr is None or pushed_count is None or parent_count is None:
        return (UNKNOWN, UNKNOWN)
    if pr.get("merged") is not True:
        return (RED, RED)
    if (pr.get("base") or {}).get("ref") != "main":
        return (RED, RED)
    if pr.get("merge_commit_sha") != sha:
        return (RED, RED)
    if parent_count != 1:
        return (RED, RED)
    if pushed_count != 1:
        return (RED, RED)
    return (GREEN, GREEN)


def evaluate_ci_fact(check_runs: object) -> tuple[str, str]:
    """Fact 2: CI green on the exact sha, scoped to the CI Pipeline
    workflow's check runs only (AC4) — every other check run on the sha
    (the DV workflow's own still-pending jobs included) is ignored.

    A missing or not-yet-published (queued/in_progress) run renders
    unknown and never green (AC4).
    """
    if not isinstance(check_runs, list):
        return (UNKNOWN, UNKNOWN)
    mine = [
        run
        for run in check_runs
        if isinstance(run, dict) and run.get("name") == CI_CHECK_RUN_NAME
    ]
    if not mine:
        return (UNKNOWN, UNKNOWN)
    if any((run.get("conclusion") or "") in FAILURE_CONCLUSIONS for run in mine):
        return (RED, RED)
    if all(run.get("conclusion") == "success" for run in mine):
        return (GREEN, GREEN)
    return (UNKNOWN, UNKNOWN)


def evaluate_dv_fact(status_payload: object) -> tuple[str, str]:
    """Fact 3: the DV verdict — the ``deep-validation`` legacy commit status
    on the exact sha (#449 AC2b), re-evaluated over the bounded window.

    A clean read with no DV status yet — or a status still in ``pending`` —
    renders ``pending`` and is never a failure (AC5): the workflow never
    posts a failure comment for a status that does not exist yet. An
    unreadable status (API failure) renders unknown.
    """
    if not isinstance(status_payload, dict):
        return (UNKNOWN, UNKNOWN)
    entries = [
        entry
        for entry in status_payload.get("statuses") or []
        if isinstance(entry, dict) and entry.get("context") == DV_CONTEXT
    ]
    if not entries:
        return (UNKNOWN, PENDING)
    latest = max(entries, key=lambda entry: entry.get("id") or 0)
    state = latest.get("state")
    if state == "success":
        return (GREEN, GREEN)
    if state in {"failure", "error"}:
        return (RED, RED)
    return (UNKNOWN, PENDING)


def evaluate_review_fact(
    reviews: object, pr_author_id: int | None
) -> tuple[str, str]:
    """Fact 4: formal APPROVE by login AND id parity (AC6, #423 precedent —
    no login-only checks) with a reviewer distinct from the PR author.

    Any other shape (self-approval, drifted identity, no approval) is
    determinably ``unmet``; an unreadable review list or a missing PR author
    renders unknown, never green (AC4).
    """
    if not isinstance(reviews, list) or pr_author_id is None:
        return (UNKNOWN, UNKNOWN)
    for review in reviews:
        if not isinstance(review, dict) or review.get("state") != "APPROVED":
            continue
        user = review.get("user") or {}
        if (
            user.get("login") == REVIEWER_LOGIN
            and user.get("id") == REVIEWER_ID
            and user.get("id") != pr_author_id
        ):
            return (GREEN, GREEN)
    return (RED, UNMET)


def evaluate_traceability_fact(
    issue_number: int | None, pr: dict | None
) -> tuple[str, str]:
    """Fact 5: issue<->PR traceability — a uniquely derived linked issue
    (native closing linkage, AC7) for the associated PR."""
    if issue_number is None or pr is None:
        return (UNKNOWN, UNKNOWN)
    return (GREEN, GREEN)


def overall_signal(facts: dict[str, tuple[str, str]]) -> bool:
    """The closeout-signal condition: ALL five facts green (AC1)."""
    return bool(facts) and all(fact == GREEN for fact, _ in facts.values())


def render_comment(
    sha: str, pr_number: int, issue_number: int, facts: dict[str, tuple[str, str]]
) -> str:
    """AC8/AC9/AC10: ONE line — hidden marker + machine-derived values only.

    Only the sha, the PR number, the issue number and the per-fact verdicts
    are interpolated; no free text from the PR body, commit message, branch
    name or issue body can reach this body (the indirect prompt-injection
    surface, since agents read issue threads over MCP). The line states the
    report-only contract: a signal that does not close the DoD gate.
    """
    verdicts = " · ".join(
        f"{name}: {facts.get(name, (UNKNOWN, UNKNOWN))[1]}" for name in FACT_ORDER
    )
    prefix = "✅" if overall_signal(facts) else "⚠️"
    signal_phrase = "does not close the DoD gate"
    return (
        f"{COMMENT_MARKER}{prefix} DoD closeout signal (report-only — {signal_phrase}; "
        f"@scrum-master remains the DoD authority): "
        f"sha `{sha}` · PR #{pr_number} · issue #{issue_number} · {verdicts}"
    )


def gh_api(args: list[str]) -> object:
    """One ``gh api`` call with the built-in token; ANY failure -> None.

    Every caller treats None as the unknown/pending tri-state (fail-safe):
    an API failure never produces a green or red verdict by itself.
    """
    cmd = ["gh", "api", *args]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GITHUB_API_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def evaluate_once(repo: str, sha: str, pushed_count: int | None) -> Evaluation:
    """Fetch every fact input for the pushed sha and evaluate all five facts.

    Every fact evaluates on github.sha (AC3) — never on the pre-squash PR
    head sha.
    """
    evaluation = Evaluation()
    commit = gh_api([f"repos/{repo}/commits/{sha}"])
    parent_count = (
        len(commit.get("parents") or [])
        if isinstance(commit, dict)
        else None
    )
    associated = gh_api([f"repos/{repo}/commits/{sha}/pulls"])
    full_prs = []
    if isinstance(associated, list):
        for candidate in associated:
            number = candidate.get("number") if isinstance(candidate, dict) else None
            if isinstance(number, int):
                pr = gh_api([f"repos/{repo}/pulls/{number}"])
                if isinstance(pr, dict):
                    full_prs.append(pr)
    merged_prs = filter_merged_prs(full_prs, sha)
    pr = merged_prs[0] if len(merged_prs) == 1 else None

    evaluation.pr_number = pr.get("number") if pr else None
    issue_number = None
    if pr is not None:
        owner, _, name = repo.partition("/")
        issue_number = derive_issue_number(
            gh_api(
                [
                    "graphql",
                    "-F", f"owner={owner}",
                    "-F", f"name={name}",
                    "-F", f"number={pr['number']}",
                    "-f", "query=query($owner: String!, $name: String!, "
                    "$number: Int!) { repository(owner: $owner, name: $name) "
                    "{ pullRequest(number: $number) { closingIssuesReferences"
                    "(first: 10) { totalCount nodes { number } } } } }",
                ]
            )
        )
    evaluation.issue_number = issue_number

    check_runs = gh_api([f"repos/{repo}/commits/{sha}/check-runs?per_page=100"])
    status = gh_api([f"repos/{repo}/commits/{sha}/status"])
    reviews = (
        gh_api([f"repos/{repo}/pulls/{pr['number']}/reviews?per_page=100"])
        if pr is not None
        else None
    )

    evaluation.facts = {
        "squash": evaluate_squash_fact(pr, sha, pushed_count, parent_count),
        "ci": evaluate_ci_fact(
            check_runs.get("check_runs") if isinstance(check_runs, dict) else None
        ),
        "dv": evaluate_dv_fact(status),
        "review": evaluate_review_fact(
            reviews, (pr.get("user") or {}).get("id") if pr else None
        ),
        "traceability": evaluate_traceability_fact(issue_number, pr),
    }
    return evaluation


def post_or_update_comment(repo: str, issue_number: int, body: str) -> bool:
    """AC9: at most one signal comment per issue — hidden marker lookup,
    update in place; created only when absent. Returns True on success."""
    comments = gh_api([f"repos/{repo}/issues/{issue_number}/comments?per_page=100"])
    existing_id = None
    if isinstance(comments, list):
        for comment in comments:
            if (
                isinstance(comment, dict)
                and str(comment.get("body") or "").startswith(COMMENT_MARKER)
            ):
                existing_id = comment.get("id")
                break
    if existing_id is not None:
        # Single-line calls by design: the config gate (AC11) pins the write
        # surface line-wise — every POST/PATCH must target issue comments.
        updated = gh_api(["-X", "PATCH", f"repos/{repo}/issues/comments/{existing_id}", "-f", f"body={body}"])
        if updated is not None:
            return True
        print(
            f"::warning::dod-closeout: comment update failed on issue "
            f"#{issue_number} — the signal is inconclusive, never a failure "
            f"(AC10); next push re-verifies"
        )
        return False
    created = gh_api(["-X", "POST", f"repos/{repo}/issues/{issue_number}/comments", "-f", f"body={body}"])
    if created is not None:
        return True
    print(
        f"::warning::dod-closeout: comment create failed on issue "
        f"#{issue_number} — the signal is inconclusive, never a failure "
        f"(AC10); next push re-verifies"
    )
    return False


def run() -> None:
    """The bounded-window verification loop (AC5); always report-only."""
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    sha = os.environ.get("SHA", "").strip()
    if not repo or not sha:
        print(
            "::warning::dod-closeout: GITHUB_REPOSITORY/SHA missing — signal "
            "skipped (report-only, exit 0)"
        )
        return
    commits = os.environ.get("COMMITS_JSON", "")
    try:
        # COMMITS_JSON is the pushed-commit array; count it without
        # trusting its contents (only the count is used, AC3).
        parsed = json.loads(commits or "[]")
    except ValueError:
        parsed = None
    pushed_count = len(parsed) if isinstance(parsed, list) else None
    deadline = time.monotonic() + WINDOW_SECONDS
    while True:
        evaluation = evaluate_once(repo, sha, pushed_count)
        if evaluation.final() or time.monotonic() >= deadline:
            break
        time.sleep(POLL_SECONDS)

    if evaluation.issue_number is None:
        # AC7: zero or >1 linked-issue candidates -> unknown; there is no
        # comment target, so no signal can be posted for this push.
        print(
            "::warning::dod-closeout: linked issue could not be derived "
            f"uniquely from the native closing linkage for sha {sha[:12]} "
            "(zero or >1 candidates) — no signal comment; @scrum-master "
            "handles this as an exception"
        )
        return
    if evaluation.pr_number is None:
        # Unreachable in practice (linkage requires an associated PR) — a
        # missing PR number must never render as a fabricated value (AC8).
        print(
            "::warning::dod-closeout: linked issue resolved without an "
            "associated PR — no signal comment (report-only, exit 0)"
        )
        return
    body = render_comment(
        sha, evaluation.pr_number, evaluation.issue_number, evaluation.facts
    )
    post_or_update_comment(repo, evaluation.issue_number, body)
    verdicts = ", ".join(
        f"{name}={fact}" for name, (fact, _) in evaluation.facts.items()
    )
    print(f"dod-closeout: verification complete on {sha[:12]} ({verdicts})")


def main() -> int:
    """Report-only contract (AC10): the verifier ALWAYS exits 0 — an
    internal error renders the signal inconclusive via a warning, never a
    failed job (the workflow is never a required check)."""
    try:
        run()
    except Exception as exc:  # noqa: BLE001 — the report-only exit-0 contract
        print(
            f"::warning::dod-closeout verifier aborted ({type(exc).__name__}) "
            "— signal inconclusive, never a failure (AC10)"
        )
    return 0


if __name__ == "__main__":
    main()
