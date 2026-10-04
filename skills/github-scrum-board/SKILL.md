---
name: github-scrum-board
description: "GitHub SCRUM project management, sprint milestone orchestration, issue schema templates, Definition of Done enforcement, and post-release board hygiene automation for @fpittelo repositories."
---

# GitHub SCRUM Board, Milestone & Issue Management

This skill is the operational playbook for **`@scrum-master`** and **`@architect`** to manage sprints, groom backlogs, enforce the Definition of Done (DoD), and automate board hygiene across all GitHub repositories under **Frederic Pitteloud (@fpittelo)**.

---

## 1. GitHub SCRUM Cadence & Structure

- **Sprint Length:** 2-week nominal iterations.
- **Demand-Driven Cadence (PO decision A, 2026-10-04, #216):** Sprints execute on demand (often same-day). The date windows in milestone titles are **labels only, not planning commitments** — early/same-day execution is **conformant, not a deviation** (resolves the cadence-honesty flags carried in #201, #215, #216).
- **Milestone Naming Convention:** `Sprint XX — YYYY-MM-DD to YYYY-MM-DD` (e.g., `Sprint 01 — 2026-08-22 to 2026-09-05`).
- **Issue Execution:** Sequential issue-by-issue handoff into `dev` via squash merge.

---

## 2. Standard Label Taxonomy

Every repository maintains this standardized label schema:

| Category | Label Name | Color | Purpose |
| :--- | :--- | :--- | :--- |
| **Type** | `type::story` | `#0E8A16` | User story delivering user/athlete value |
| | `type::task` | `#1D76DB` | Technical task or implementation sub-task |
| | `type::bug` | `#D93F0B` | Defect or regression requiring a fix |
| | `type::spike` | `#5319E7` | Architectural research or feasibility study |
| **Status** | `status::todo` | `#CCCCCC` | Backlog item ready for active sprint execution |
| | `status::in-progress`| `#FBCA04` | Actively being developed on a feature branch |
| | `status::review` | `#006B75` | PR opened targeting `dev`, pending review |
| | `status::done` | `#0E8A16` | Merged into `dev`, DoD verified, issue closed |
| **Agent** | `agent::architect` | `#BFD4F2` | Solution architecture, ADRs, backlog grooming |
| | `agent::scrum-master`| `#F9D0C4` | Milestone management, DoD audit, board hygiene |
| | `agent::developer` | `#C2E0C6` | Python/FastMCP implementation with TDD |
| | `agent::code-reviewer`| `#FEF2C0` | Read-only PR inspection and quality gate |
| | `agent::devops` | `#D4C5F9` | CI/CD workflows, Docker, release promotion |
| | `agent::cyber-security`| `#FFC0CB`| Threat modeling, vulnerability scanning |
| **Blockers**| `blocker::active` | `#B60205` | Blocked item (e.g. 3-attempt circuit breaker triggered) |
| **Severity**| `severity::critical` | `#B60205` | CVSS 9.0-10.0 blocker |
| | `severity::high` | `#D93F0B` | CVSS 7.0-8.9 |
| | `severity::medium` | `#FBCA04` | CVSS 4.0-6.9 |
| | `severity::low` | `#0E8A16` | CVSS 0.1-3.9 |

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

- **Branch Naming:** `feature/<issue-#>-<slug>`, `fix/<issue-#>-<slug>`, `chore/<issue-#>-<slug>` branched from `dev`.
- **PR Target:** Must ONLY target `dev`.
- **PR Description:** Must reference issue: `Resolves #<issue-#>`.
- **Squash Merge Title:** `feat(<scope>): <description> (#<pr_number>)` or `fix(<scope>): <description> (#<pr_number>)`.
- **Commit Body:**
  ```text
  Resolves #<issue_number>

  Reviewed-by: @code-reviewer
  ```

---

## 5. DoD Closeout Comment Template

When closing an issue upon squash merge into `dev`, **`@scrum-master`** posts this closing comment:

```markdown
### 🏁 Definition of Done (DoD) Verification Summary

- [x] **Acceptance Criteria:** All acceptance criteria fulfilled and verified against test suite.
- [x] **Branching & Merge:** Feature branch squash-merged into `dev` via PR #<PR_NUMBER>.
- [x] **CI Pipeline:** 100% clean GitHub Actions run on `dev` (0 warnings, 0 failures).
- [x] **Code Review:** Formal `APPROVE` decision documented by `@code-reviewer`.
- [x] **Traceability:** PR and commits linked to Issue #<ISSUE_NUMBER>.

**Status:** Completed and verified. Issue closed.
```

### Pending-PO Closeout Precedent (#180, #181)

When a story's acceptance criteria are all fulfilled **except** a pending-PO one-click acceptance (e.g. a template flag toggle, a CI glance), **`@scrum-master`** must **close the issue** with an explicit `pending-PO` note referencing the one-click item (precedent: #180, #181), rather than holding the closeout (the #190 deviation).

**Guard:** this allowance must NOT weaken the 5-criteria DoD gate — a closeout genuinely lacking DoD evidence (no merged PR, no formal `@code-reviewer` `APPROVE`, failing CI) is still **rejected**.

### MCP Write-Verification Pattern

- **Separated calls:** `GITHUB_issue_write` updates MUST use separated calls (state-only first, then labels-only); combined label+state+state_reason update calls are prohibited — known silent-failure mode (3 occurrences: #218, #221, #229).
- **Fresh-read verification:** Every write MUST be verified with a fresh read before reporting success.
- **`parent_issue_number`:** valid on `create` only.

### Closeout-Fallback

- **Fallback rule:** If `@scrum-master` write tooling fails during DoD closeout, the closeout falls back to `@architect` (precedent 2×: Sprint 13 pre-promotion remediation of #218/#221/#229; Sprint 14 #236 closeout).
- **Correct tool usage notes:**
  - `GITHUB_add_issue_comment` takes `body` only — never combine with `comment_id`.
  - Remote branch deletion is a bash operation (`git push origin --delete <branch>`), not an MCP tool.
  - All writes follow the MCP Write-Verification Pattern (separated calls + fresh-read verification).

---

## 6. Post-Merge Board Hygiene Protocol (Triggered on Release to `main`)

When all sprint deliverables are promoted and merged into `main`:

1. **Board Audit:** Verify all issues assigned to the active Sprint Milestone are closed with `status::done`.
2. **Clear Stale Labels:** Remove lingering `blocker::active` or intermediate status labels.
3. **Close Sprint Milestone:** Set milestone state to `closed`.
4. **Create Sprint Retrospective Issue:**
   - Title: `Retrospective: Sprint XX — YYYY-MM-DD`
   - Labels: `type::spike`, `agent::scrum-master`, `status::done`
   - Body:
     ```markdown
     # Sprint XX Retrospective

     ## 📊 Sprint Metrics
     - **Milestone:** Sprint XX
     - **Issues Completed:** X / X (100%)
     - **Release Tag:** vX.Y.Z

     ## 🌟 What Went Well
     - [Successful autonomous execution items, clean CI passes]

     ## 🔧 Opportunities for Improvement
     - [Refactorings, test runtime improvements, schema refinements]

     ## 🚀 Action Items for Next Sprint
     - [Actionable process improvements for upcoming backlog]
     ```
5. **Initialize Next Sprint:** Create the next Sprint Milestone (`Sprint XX+1`) and groom initial backlog items with `@architect`.
