---
name: github-scrum-board
description: "GitHub SCRUM project management, sprint marker orchestration, issue schema templates, Definition of Done enforcement, and post-release board hygiene automation for @fpittelo repositories."
---

# GitHub SCRUM Board & Issue Management

This skill is the operational playbook for **`@scrum-master`** and **`@architect`** to manage sprints, groom backlogs, enforce the Definition of Done (DoD), and automate board hygiene across all GitHub repositories under **Frederic Pitteloud (@fpittelo)**.

---

## 1. GitHub SCRUM Cadence & Structure

- **Sprint Length:** 2-week nominal iterations.
- **Demand-Driven Cadence (PO decision A, 2026-10-04, #216):** Sprints execute on demand (often same-day). The date windows in milestone titles are **labels only, not planning commitments** — early/same-day execution is **conformant, not a deviation** (resolves the cadence-honesty flags carried in #201, #215, #216).
- **Sprint Membership — Sprint Marker Issue (MADR-0013):** Sprint scope is expressed by one **sprint-marker issue** per sprint (epic/sub-issue pattern, precedent #293), created and closed autonomously by `@scrum-master`. Sprint membership is the set of issues sub-scoped to the marker; no milestone is required to groom, queue, dispatch, or close work.
- **Milestones Are Historical Records (MADR-0013):** Milestones are **never SSOT and never a dependency** — agents cannot manage them (upstream `github-mcp-server` exposes no milestone CRUD). Standing rule: **new issues never receive a milestone**; existing closed issues retain their historical milestone as history.
- **Planning Board (retired — MADR-0022, #400):** the **`HOME Squad Planning`** Projects v2 board and its `GITHUB_PROJECTS` MCP server are **RETIRED**. The **execution SSOT is the five `status::*` issue labels + sprint-marker sub-issues** — every board transition (groom, dispatch, review, close) is driven by and verified against issue labels alone. No Projects v2 field writes are possible or expected (no server, no PAT, no namespace); sprint-marker issues remain the execution/DoD/closeout record.
- **Issue Execution:** Sequential issue-by-issue handoff into `main` (the trunk) via squash merge (MADR-0017).

---

## 2. Standard Label Taxonomy

Every repository maintains this standardized label schema:

| Category | Label Name | Color | Purpose |
| :--- | :--- | :--- | :--- |
| **Type** | `type::story` | `#0E8A16` | User story delivering user/athlete value |
| | `type::task` | `#1D76DB` | Technical task or implementation sub-task |
| | `type::bug` | `#D93F0B` | Defect or regression requiring a fix |
| | `type::spike` | `#5319E7` | Architectural research or feasibility study |
| **Status** | `status::backlog` | `#CCCCCC` | Raw, ungroomed item — not yet specified |
| | `status::ready` | `#0E8A16` | Groomed: ACs written, dependencies closed, pickable |
| | `status::in-progress`| `#FBCA04` | Actively being developed on a feature branch |
| | `status::review` | `#006B75` | PR opened targeting `main`, pending review |
| | `status::done` | `#0E8A16` | Merged into `main`, DoD verified, issue closed |
| **Agent** | `agent::architect` | `#BFD4F2` | Solution architecture, ADRs, backlog grooming |
| | `agent::scrum-master`| `#F9D0C4` | Sprint marker management, DoD audit, board hygiene |
| | `agent::developer` | `#C2E0C6` | Python/FastMCP implementation with TDD |
| | `agent::code-reviewer`| `#FEF2C0` | Read-only PR inspection and quality gate |
| | `agent::devops` | `#D4C5F9` | CI/CD workflows, Docker, release tagging & publishing |
| | `agent::cyber-security`| `#FFC0CB`| Threat modeling, vulnerability scanning |
| **Blockers**| `blocker::active` | `#B60205` | Blocked item (e.g. 3-attempt circuit breaker triggered) |
| **Severity**| `severity::critical` | `#B60205` | CVSS 9.0-10.0 blocker |
| | `severity::high` | `#D93F0B` | CVSS 7.0-8.9 |
| | `severity::medium` | `#FBCA04` | CVSS 4.0-6.9 |
| | `severity::low` | `#0E8A16` | CVSS 0.1-3.9 |

**Workflow state SSOT (MADR-0013):** the five `status::*` labels above are the authoritative board state, applied in order `status::backlog` → `status::ready` → `status::in-progress` → `status::review` → `status::done`. `status::todo` is **retired** — do not apply it to new or existing issues; sweep any reappearance during board hygiene.

---

## 3. GitHub Issue Specification Templates

### A. User Story / Feature Template (`type::story`)
```markdown
## 🎯 Goal & Motivation
As a [user/athlete], I want to [action] so that [expected outcome/value].

## 🏗️ Architectural Specification
- **Component:** `src/<service>_mcp/...`
- **ArchiMate Reference:** Application Component -> Capability
- **Design Overview:** [Brief description of interfaces, models, and contracts]

## 📋 Acceptance Criteria
- [ ] AC1: [Explicit functional condition with expected inputs/outputs]
- [ ] AC2: [Schema validation and error handling requirement]
- [ ] AC3: [100% test coverage with zero warnings (`pytest -W error`)]

## 🔒 Security & Privacy (Swiss nLPD)
- [ ] Zero secrets logged or hardcoded.
- [ ] Biometric/personal data stored locally with encryption.
```

### B. Technical Task Template (`type::task`)
```markdown
## 🛠️ Technical Objective
[Precise description of code, refactoring, container, or CI/CD change required]

## 📋 Acceptance Criteria
- [ ] AC1: [Specific implementation requirement]
- [ ] AC2: [Zero-warning pre-flight gate passes locally]
- [ ] AC3: [CI pipeline completes with 0 warnings, 0 failures]
```

---

## 4. Pull Request Protocol & Commit Hygiene

- **Branch Naming:** `feature/<issue-#>-<slug>`, `fix/<issue-#>-<slug>`, `chore/<issue-#>-<slug>` branched from `main` (the trunk — MADR-0017).
- **PR Target:** Must ONLY target `main`.
- **PR Description:** Must reference issue: `Resolves #<issue-#>`.
- **Squash Merge Title:** `feat(<scope>): <description> (#<pr_number>)` or `fix(<scope>): <description> (#<pr_number>)`.
- **Commit Body:**
  ```text
  Resolves #<issue_number>

  Reviewed-by: @code-reviewer
  ```

---

## 5. DoD Closeout Comment Template

When closing an issue upon squash merge into `main`, **`@scrum-master`** posts this closing comment:

```markdown
### 🏁 Definition of Done (DoD) Verification Summary

- [x] **Acceptance Criteria:** All acceptance criteria fulfilled and verified against test suite.
- [x] **Branching & Merge:** Feature branch squash-merged into `main` via PR #<PR_NUMBER>.
- [x] **CI Pipeline:** 100% clean GitHub Actions run (0 warnings, 0 failures).
- [x] **Code Review:** Formal `APPROVE` decision documented by `@code-reviewer`.
- [x] **Traceability:** PR and commits linked to Issue #<ISSUE_NUMBER>.

**Status:** Completed and verified. Issue closed.
```

### Pending-PO Closeout Precedent (#180, #181)

When a story's acceptance criteria are all fulfilled **except** a pending-PO one-click acceptance (e.g. a template flag toggle, a CI glance), **`@scrum-master`** must **close the issue** with an explicit `pending-PO` note referencing the one-click item (precedent: #180, #181), rather than holding the closeout (the #190 deviation).

**Guard:** this allowance must NOT weaken the 5-criteria DoD gate — a closeout genuinely lacking DoD evidence (no merged PR, no formal `@code-reviewer` `APPROVE`, failing CI) is still **rejected**.

### MCP Write-Verification Pattern (verify-or-escalate)

- **Separated calls:** `GITHUB_issue_write` updates MUST use separated calls (state-only first, then labels-only); combined label+state+state_reason update calls are prohibited — known silent-failure mode (3 occurrences: #218, #221, #229).
- **Fresh-read verification:** Every write MUST be verified with a fresh read before reporting success.
- **`parent_issue_number`:** valid on `create` only.
- **Verify-or-escalate (MADR-0013):** separated call → fresh read → on failure **retry once** → still unconfirmed → flag `blocker::active` (where possible) and fall back to `@architect` under the Closeout-Fallback rule. **No board state is reported done without a confirming read.**

### Closeout-Fallback

- **Fallback rule (#344):** If `@scrum-master` write tooling fails during DoD closeout, `@scrum-master` executes the fallback **autonomously** — the `gh` CLI fallback and remote branch deletion below are covered by its scoped bash allowlist (`agents/scrum-master.md`, #344: `gh issue *`, `gh pr *`, `git push origin --delete *`; everything else stays denied). Escalation to `@architect` remains ONLY for MCP-schema failures the fallback cannot solve (precedent 2×: Sprint 13 pre-promotion remediation of #218/#221/#229; Sprint 14 #236 closeout).
- **Correct tool usage notes:**
  - `GITHUB_add_issue_comment` takes `body` only — never combine with `comment_id`.
  - `GITHUB_issue_write` update takes only the changed fields — never `parent_issue_number` (create-only; see `agents/scrum-master.md` MCP Tool-Call Discipline, #304).
  - Remote branch deletion is a bash operation (`git push origin --delete <branch>`), not an MCP tool — **owned autonomously by `@scrum-master` since #344** (allowlist pattern `git push origin --delete *`), for merged feature-branch cleanup only.
  - All writes follow the MCP Write-Verification Pattern (separated calls + fresh-read verification).
- **Privileged fallback path (#304, proven 2026-10-13; owned autonomously by `@scrum-master` since #344):** when MCP write paths fail (schema rejection or silent field stripping), use the `gh` CLI with inline env injection — `GH_TOKEN="${GITHUB_PERSONAL_ACCESS_TOKEN}" gh <command>` (shell assignment, NOT the `env` command, which is permission-denied). Proven sufficient for issue labels (`gh issue edit`) and repo-wide verification (`gh issue list` / `gh pr list`). **Label-definition CRUD (`gh label create/delete`) is NOT covered by the `@scrum-master` bash allowlist** (`gh issue *`, `gh pr *`, `git push origin --delete *` only) — label-definition changes route to `@architect`/`@devops`, unless a future permission decision consciously extends the allowlist.
- **`gh pr edit` is broken for label writes (#304):** it fails with a GraphQL project-cards deprecation error. Use `gh api` REST calls instead: `gh api -X DELETE repos/<owner>/<repo>/issues/<n>/labels/<label>` and `gh api -X POST repos/<owner>/<repo>/issues/<n>/labels -f labels[]=<label>`.

---

## 6. Post-Release Board Hygiene Protocol (Triggered on Release)

When all sprint deliverables are merged into `main` (the trunk) and the release is tagged under the single PO approval (MADR-0017 — no promotion PRs exist):

1. **Board Audit:** Verify all issues in the active sprint (sprint-marker issue) are closed with `status::done`.
2. **Clear Stale Labels:** Remove lingering `blocker::active` or intermediate status labels (including any reappearance of the retired `status::todo`).
3. **Close the Sprint Marker Issue with Lightweight Retro:** `@scrum-master` closes the sprint-marker issue autonomously (MADR-0013) — no milestone close is required or possible (milestones are historical records). The closing comment on the marker carries a **mandatory lightweight 3-bullet retrospective section** (#339):
   ```markdown
   ## 🔁 Sprint XX Retro (3 bullets)

   - **What went well:** <e.g. all issues merged green, zero blockers>
   - **Improvement opportunity:** <single biggest friction observed>
   - **Action for next sprint:** <one concrete process adjustment, or "none">
   ```
   A **standalone retrospective issue** (`type::spike`) is created ONLY when the sprint experienced a major incident or architectural pivot worth a dedicated record — it is no longer a default hygiene step (#339).
4. **Initialize Next Sprint:** Create the next **sprint-marker issue** (`Sprint XX+1`, epic/sub-issue pattern) and groom initial backlog items with `@architect` — new issues enter at `status::backlog` and are promoted to `status::ready` once groomed; **no milestone is created** (MADR-0013).
