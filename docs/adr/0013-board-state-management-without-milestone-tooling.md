# MADR-0013: Board state management without milestone tooling — status labels as SSOT, sprint marker issues

- **Status:** accepted
- **Date:** 2026-10-13
- **Deciders:** @fpittelo (PO approval 2026-10-13 — implementation go), @architect (author)

## Context

The HOME SCRUM board's workflow state and sprint scoping have been anchored to GitHub
primitives that the agent team **cannot actually manage**. The upstream
`github/github-mcp-server` exposes **no milestone CRUD and no agent-facing milestone
list tools** — the only milestone-related capability available to an agent is setting a
milestone number on an issue. Every other milestone operation (create, close, rename,
list) requires the PO's manual web-UI intervention.

This is not hypothetical: Sprint 18 closeout (epic #293) was blocked because **milestone
#16 could not be closed by any agent session** — `@scrum-master` documented the gap in
the release-confirmation comment, and closing the milestone fell back to the PO. The same
limitation makes the PO a recurring manual bottleneck at every sprint boundary (create
milestone → run sprint → close milestone), for a purely mechanical operation.

Meanwhile the board's actual state lives in **status labels** — which agents CAN create,
set, and verify through the existing MCP tooling (`GITHUB_issue_write` labels field,
fresh-read verification). Labels are already the de-facto SSOT; milestones are the
de-jure SSOT that no agent can touch.

## Decision Drivers

- **Agent autonomy (MADR-0008):** the single-PO AI-agent team must run the full issue
  lifecycle (groom → queue → dispatch → review → close → sprint boundary) without PO
  involvement except the Rule 5 release approval; a board primitive only the PO can
  write contradicts the responsibility harness.
- **PO friction:** sprint-boundary milestone ceremony is mechanical, unskilled work that
  consumes the bottleneck resource (same driver as MADR-0012).
- **KIS & YAGNI (home-governance §9):** reuse the already-working label tooling instead
  of adopting a heavier board system.
- **Write integrity:** label writes have a known silent-failure mode (intermittent MCP
  serialization defects, 3 occurrences: #218, #221, #229); state changes must be
  verifiable, never assumed.
- **No upstream dependency:** waiting on `github/github-mcp-server` milestone CRUD is
  outside the team's control (evidence below).

## Considered Options

### Option 1: Keep milestones as sprint SSOT, PO writes only

- Pros: zero migration; milestones remain the familiar sprint container; GitHub auto
  -links issues to their milestone.
- Cons: **formalizes the bottleneck** — every sprint boundary (create at inception,
  close at hygiene) requires PO manual action; agents still cannot list or verify
  milestone state, so board audits stay partially manual; contradicts the autonomy
  principle the squad operates under.

### Option 2: Adopt GitHub Projects v2 as the board

- Pros: fully tooled upstream (Projects v2 has MCP item/field mutation paths); rich
  views, automation, per-sprint swimlanes.
- Cons: **deferred per YAGNI** — requires an MCP toolset configuration change (new
  server/toolset scoping per MADR-0011 conventions), a board build, and migration of
  all state; the 5-state label taxonomy already satisfies every current need; no
  current requirement for views or automation beyond what labels + sub-issues provide.
  Revisit if the portfolio grows a genuine need for board views/automation.

### Option 3: Wait for upstream milestone CRUD

- Pros: would keep the existing mental model with agent-writable milestones.
- Cons: **rejected on evidence** — upstream PR
  [github/github-mcp-server#1560](https://github.com/github/github-mcp-server/pull/1560)
  (milestone tooling) has been open and unmerged since December 2025, and upstream issue
  [github/github-mcp-server#258](https://github.com/github/github-mcp-server/issues/258)
  was closed as not planned by the stale bot despite live demand. No merge horizon is
  predictable; the bottleneck would persist indefinitely.

### Option 4 (chosen): Labels as workflow SSOT + sprint marker issues; milestones demoted to history

- Pros: every primitive is agent-manageable today with proven tooling; sprint scoping
  reuses the epic/sub-issue pattern already proven by epic #293; migration is a one-time
  label sweep; write integrity is enforceable via the verify-or-escalate pattern.
- Cons: label taxonomy is convention (not schema-enforced) — mitigated by the
  verify-or-escalate write rule and board-hygiene audits; sprint membership via
  sub-issues requires the marker issue to be maintained (a documented `@scrum-master`
  duty, not a tooling gap).

## Decision Outcome

Chosen option: **"Option 4 — status labels as the board SSOT, sprint marker issues for
sprint scope, milestones demoted to historical records."**

**PO decision (@fpittelo, 2026-10-13):** approved for implementation (issue #302 go).

The decision has four operative parts:

1. **Five-state status label taxonomy is the SSOT for workflow state:**
   `status::backlog` (raw, ungroomed) → `status::ready` (groomed: ACs written,
   dependencies closed, pickable) → `status::in-progress` → `status::review` →
   `status::done`. `status::todo` is retired and its label deleted after migration.
2. **Sprint membership is expressed by a sprint marker issue** (epic/sub-issue pattern,
   precedent #293), created and closed autonomously by `@scrum-master`. No milestone is
   required to groom, queue, dispatch, or close work.
3. **Milestones are demoted to historical records** — never SSOT, never a dependency.
   Standing rule: **new issues never receive a milestone**; existing closed issues
   retain their historical milestone as history.
4. **All board writes follow the verify-or-escalate pattern:** separated calls
   (state-only, then labels-only) → fresh read confirming the result → on failure retry
   once → still unconfirmed → flag `blocker::active` (where possible) and fall back to
   `@architect` under the closeout-fallback rule. No board state is reported done
   without a confirming read.

**No upstream engagement (explicit PO decision, recorded to prevent re-litigation):**
the team does not file, chase, or wait on `github/github-mcp-server` milestone tooling
(see Option 3 evidence). If upstream ships milestone CRUD unbidden, adopting it remains
a fresh decision — this ADR is the reference point for that re-evaluation.

## Consequences

- **Positive:** agents run the full issue lifecycle — grooming, queueing, dispatch,
  review, closeout, and sprint boundaries — without PO involvement except the Rule 5
  release approval; the sprint-boundary PO bottleneck is eliminated by construction;
  board state becomes fully auditable by agents (labels are readable and verifiable via
  fresh reads).
- **Negative:** one-time migration cost — open `status::todo` items must be classified
  into `status::backlog`/`status::ready` by grooming state, and the `status::todo` label
  retired; the taxonomy is convention-enforced, so a stray legacy label can reappear and
  must be caught by board hygiene.
- **Mitigations:** the verify-or-escalate write rule (separated calls, fresh read,
  single retry, `blocker::active` + `@architect` fallback) contains the known
  silent-write failure mode; the post-merge board hygiene protocol audits labels each
  release; `skills/github-scrum-board` §1/§2/§5/§6 codify the new mechanics so every
  agent session applies them uniformly.
