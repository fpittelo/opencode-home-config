# MADR-0018: Demote Projects v2 planning board to optional roadmap view

- **Status:** accepted (optional-roadmap-view posture superseded by MADR-0022 — the Projects v2 board retires entirely)
- **Date:** 2026-10-17
- **Deciders:** @fpittelo (PO directive "go" on the #339 audit recommendations, 2026-10-17), @architect (author)

## Context

MADR-0014 established the GitHub Projects v2 board `HOME Squad Planning` (project #36, `Sprint` iteration + `Priority` fields) as the **planning SSOT**, with mandatory field writes at grooming (`Priority` by @architect) and dispatch (`Sprint` by @scrum-master), each verified by a fresh read. In parallel, MADR-0013 made the five `status::*` issue labels the execution SSOT and sprint-marker issues the sprint-scope record.

The architecture audit (2026-10-17, PO-requested) found this creates **three parallel representations of sprint work** (labels + sprint markers + Projects fields). Every dispatch requires dual writes (`GITHUB_issue_write` + `GITHUB_PROJECTS_projects_write`) with verify-or-escalate read loops; a Projects write timeout or field-strip desynchronizes the board and stalls the autonomous loop into `blocker::active`. For a single-PO, WIP=1, demand-driven portfolio, the Projects layer adds ceremony without adding a decision — the exact failure mode KIS & YAGNI (`home-governance` §9) warns against.

## Decision Drivers

- **KIS & YAGNI:** the smallest mechanism satisfying the delivery fabric wins; a third state store is speculative machinery.
- **Autonomous loop reliability:** board transitions must never block on a non-essential write path.
- **Single-PO reality:** the Projects board serves PO roadmap visibility, not agent coordination — labels already do the latter.
- **Traceability:** the demotion partially supersedes MADR-0014's planning-SSOT claim and must be recorded (madr-adr supersession trigger).

## Considered Options

### Option 1: Demote Projects v2 to an optional roadmap view (chosen)

- Pros: execution SSOT collapses to labels + sprint markers (one write per transition); the loop can never stall on Projects tooling; the board remains available for PO roadmap visibility; zero permission changes required.
- Cons: MADR-0014's planning-SSOT wording becomes historical; roadmap data may drift from execution state if agents stop writing it.

### Option 2: Status quo — mandatory dual writes at grooming/dispatch

- Pros: roadmap stays in lockstep with execution.
- Cons: permanent dual-write + verify-or-escalate tax on every transition; known desync/stall failure mode; contradicts the audit's KIS findings.

### Option 3: Retire the Projects server entirely

- Pros: maximal simplification.
- Cons: removes the PO's roadmap view the PO has not asked to remove (YAGNI in the other direction — do not delete what is still used for visibility).

## Decision Outcome

Chosen option: **"Option 1 — Demote Projects v2 to an optional roadmap view"**, because the execution SSOT (labels + sprint markers) is fully sufficient for the autonomous loop, and the Projects layer's only unique value (PO roadmap visibility) does not require mandatory writes.

**Normative statement (SSOT: `skills/github-scrum-board/SKILL.md` §1):** the five `status::*` issue labels + sprint-marker sub-issues are the sole execution SSOT. Projects v2 `Sprint`/`Priority` writes are permitted, never mandatory, and never block the loop — no dual-write at grooming or dispatch, no verify-or-escalate dependency on Projects state for any board transition. This supersedes MADR-0014's planning-SSOT claim and its write-ownership convention (`Priority` at grooming / `Sprint` at dispatch); the `GITHUB_PROJECTS` server, its scoped PAT, and the per-agent permission scoping remain unchanged.

## Consequences

- **Positive:** one write per board transition; the loop is immune to Projects tooling failures; ceremony reduced per the audit; permissions and credentials untouched (no security-surface change).
- **Negative:** roadmap fields may lag execution state when agents skip optional writes; MADR-0014 is partially superseded (its server/credential decisions remain fully in force).
- **Mitigations:** the sprint-marker issue remains the authoritative execution/DoD/closeout record; any roadmap write that IS made still follows fresh-read verification; the PO can request a roadmap sync at any sprint boundary.
