# MADR-0014: Agent-managed planning model — GitHub Projects v2 iteration and priority fields, dedicated GITHUB_PROJECTS server

- **Status:** accepted
- **Date:** 2026-10-17
- **Deciders:** @fpittelo (PO decisions recorded on issue #308, 2026-10-17 — Projects v2 model choice, minimal no-status-mirror scope, dedicated classic `project`-scope PAT), @architect (author)

## Context

MADR-0013 retired milestones as board primitives and explicitly parked Projects v2 as
Option 2 "revisit if the portfolio grows a genuine need for board views/automation".
That trigger fired on 2026-10-17: PO directive #308 states milestones are **not wanted
at all** unless fully agent-supported, and requests a fully agent-manageable
replacement for planning (prioritized backlog, iterations, board views).

Verified facts underlying this decision (2026-10-17, issue #308 — do not re-research):

1. **Milestone CRUD is not coming from upstream.** The pinned server (v1.12.2, probed
   live) exposes 45 default-toolset tools with zero milestone tools; code search of
   `github/github-mcp-server` post-v2.0.2 finds no `create_milestone` tool anywhere.
2. **The projects toolset is already compiled into the pinned binary** — a live schema
   probe of `projects_write` confirmed: `create_project`, `create_iteration_field`
   (`iteration_duration`, `start_date`, custom `iterations`), `add_project_item`
   (issues and PRs by number), `update_project_item(s)` (field settable by
   `{"name": ..., "value": ...}`, bulk updates), `delete_project_item`, saved views
   (`table`/`board`/`roadmap`), and project status updates. Full label CRUD
   (`list_label`/`label_write`) also exists at binary level.
3. **Fine-grained PATs cannot access user-owned Projects** (GitHub docs limitation,
   verified live 2026-10-17; the only fine-grained Projects permission is
   `organization_projects`, which requires an organization resource owner).
4. The PO has already created a **classic PAT scoped to `project` only** and installed
   it as `GITHUB_TOKEN_PROJECTS` in `~/.config/opencode/.secrets-home.env` (mode 600).

## Decision Drivers

- **Agent autonomy (MADR-0008):** planning must run with zero PO clicks after the
  one-time credential creation (already performed); a planning primitive only the PO
  can touch is disqualified.
- **PO friction (MADR-0013 unchanged):** backlog visibility and prioritization should
  not consume the bottleneck resource.
- **KIS & YAGNI (home-governance §9):** reuse the tooled upstream Projects support
  rather than building a milestone bridge/proxy; keep the minimal field set; forbid
  status-field duplication of the label SSOT.
- **Credential minimalism:** the main fine-grained credential must gain **zero** new
  scope; the new capability rides a dedicated single-scope token.
- **Write integrity (MADR-0013):** every board write follows verify-or-escalate; the
  same discipline must now cover project-field writes.
- **Swiss nLPD:** the new token is scope-minimal (no repo access), stored mode 600,
  never in the repo (gitleaks-covered).

## Considered Options

### Option 1: Milestone bridge/proxy (gh CLI fallback wrapping milestone CRUD)

- Pros: keeps the milestone mental model; no new MCP surface.
- Cons: formalizes a half-supported primitive against the PO's explicit "fully
  supported by agents" condition; adds a shell-escape surface for zero upstream
  benefit; contradicts the no-re-litigation stance recorded in MADR-0013.

### Option 2: Priority labels only (no project board)

- Pros: smallest change; `list_label`/`label_write` exist at binary level; no new
  credential needed.
- Cons: no iteration/schedule view, no board for the PO; planning state stays buried
  in issue bodies and label names; the PO explicitly asked for a board-like planning
  surface with iterations and a prioritized backlog.

### Option 3: Organization conversion or a dedicated GitHub App

- Pros: unlocks the fine-grained `organization_projects` permission cleanly.
- Cons: heavyweight ceremony (org setup, app registration, review cycles) to solve a
  one-person repository; a single-scope classic PAT achieves the same with less —
  classic scope-breadth is neutralized by selecting only the `project` scope.

### Option 4: Wait for upstream milestone CRUD

- Pros: none beyond avoiding a decision today.
- Cons: rejected on evidence — no `create_milestone` in post-v2.0.2 code, upstream
  milestone PR #1560 unmerged since 2025-12 (recorded in MADR-0013); infinite horizon.

### Option 5 (chosen): Projects v2 planning model on a dedicated namespaced GITHUB_PROJECTS server

- Pros: every planning operation is agent-manageable with the pinned binary today;
  additive credential (main PAT untouched); dedicated server keeps permission scoping
  and SoD intact via existing MADR-0011 patterns; views give the PO visibility without
  agent dependency.
- Cons: a second write surface next to labels (per-transition dual-write risk); a
  classic PAT is scope-broad by design; the JSONC permission surface grows.

## Decision Outcome

Chosen option: **"Option 5 — a user-owned Projects v2 board (`HOME Squad Planning`)
with Sprint (iteration) + Priority fields, managed end-to-end by agents through a
dedicated `GITHUB_PROJECTS` MCP server instance,"** because it is the only fully
agent-manageable planning model available from the pinned toolchain, it rides the
proven namespaced-server pattern, and it preserves both SSOT boundaries (execution
labels, planning fields) without duplication.

Operative parts:

1. **Planning model:** `HOME Squad Planning` (Projects v2, owner `@fpittelo`) with
   - **`Sprint` iteration field**, 14-day duration — iteration assignment is a
     planning label, NOT a schedule commitment (demand-driven cadence, PO decision A
     2026-10-04 / #216 remains normative);
   - **`Priority` single-select field** (P0 highest … P3 lowest) driving the
     prioritized backlog ordering;
   - saved views *Prioritized Backlog* (table, sorted by Priority) and *Sprint Board*
     (roadmap/board grouped by Sprint);
   - **no status column**: `status::*` issue labels remain the sole execution-state
     SSOT (PO decision 2, 2026-10-17 — minimal no-duplication model; the mirrored
     status option is closed unless a future PO directive reopens it).
2. **SSOT split:** `status::*` labels = execution SSOT (MADR-0013 unchanged);
   project `Sprint` + `Priority` fields = planning SSOT. Write ownership:
   `Priority` is set by `@architect` at grooming; `Sprint` is set by `@scrum-master`
   at dispatch. Every write follows verify-or-escalate (separated calls, fresh read,
   single retry, then `blocker::active` + fallback).
3. **Sprint-marker issues remain the execution/DoD/retro record** (MADR-0013
   operative part 2 is unchanged by this decision); the project is a planning
   visibility layer on top, not a replacement — sprint membership, WIP=1, and board
   hygiene semantics stay exactly as recorded in MADR-0013.
4. **Server wiring:** fifth namespaced instance `GITHUB_PROJECTS` in
   `opencode.jsonc` — same pinned binary, `--toolsets=projects`, authenticated via
   `{env:GITHUB_TOKEN_PROJECTS}`. The shared `GITHUB` server keeps its default
   toolsets and its fine-grained token, unchanged.
5. **Credential:** classic PAT, `project` scope only (the minimal scope that reaches
   user-owned Projects API surface), file mode 600, PO-owned, referenced only by
   `{env:}` interpolation — never committed, never logged. Residual risk: classic
   tokens validate broad by design — mitigated here by single-scope selection (no
   `repo`, no organization scopes); recorded for STRIDE review.
6. **Permission baseline:** global default-deny `GITHUB_PROJECTS_*` in the root
   permission object; allowlist — `@scrum-master` holds write (steady-state planning
   field mutations), `@architect` holds read AND write (`projects_get`,
   `projects_list`, `projects_write`) because the PO's settled grooming convention
   assigns `Priority` to `@architect` ("read + field groom", issue #308 rev 3);
   every other SCRUM agent and the built-in subagents (explore, general, task) deny
   the namespace (defense in depth, #150 pattern). Least-privilege note: the
   upstream `projects_write` is a consolidated tool (method enum selects the
   operation), so pattern-based scoping cannot restrict @architect/@scrum-master to
   individual methods — the residual method-level breadth is accepted for these two
   roles and mitigated by the write-ownership convention above plus the
   verify-or-escalate audit trail. The namespace-exclusivity checker and its
   regression suite are extended accordingly.
7. **Routing note (label CRUD):** if the delivery loop trips on missing label
   toolset exposure (`list_label`/`label_write`), the fix rides this same permission
   design via the `GITHUB` server — never a parallel exception.

## Consequences

- **Positive:** the full planning lifecycle — project creation, fields, views, item
  attachment, bulk grooming, priority and sprint assignment — is executed by agents
  with a single one-time PO token action (already completed); the PO gains board
  visibility (prioritized backlog, sprint board) with zero maintenance clicks; the
  audit story extends to planning state (project fields are readable by MCP).
- **Negative:** every sprint transition now has two write surfaces (labels +
  project fields) if both are touched in one step — more per-write verification
  overhead; classic PAT scope-breadth is a residual security debt; the fifth server
  adds schema surface to the config.
- **Mitigations:** write discipline (verify-or-escalate) is extended to project
  writes and codified in the `github-scrum-board` skill; the token is single-scope,
  mode-600, host-only, and visible to gitleaks deny-rules (`*.env*`); board hygiene
  audits both label and project-field state each release; the namespace-exclusivity
  gate + regression suite enforce the `GITHUB_PROJECTS_*` baseline mechanically.
