---
name: arc42-documentation
description: "Repeatable arc42 method for authoring and maintaining architecture documentation: 3 cohesive view templates (context/building blocks, runtime/delivery, cross-cutting/security), Mermaid C4 diagram standards, update triggers, and a documentation quality checklist for all HOME projects."
---

# arc42 Documentation Method

This skill establishes the **arc42** architecture documentation method for the HOME portfolio of **@fpittelo**. It provides the section templates, authoring rules, and update triggers so that architecture documentation stays maintainable, version-controlled, and diagram-native.

**Authoritative template source:** https://docs.arc42.org/ (arc42 template version 8.0). This skill adapts arc42 to the HOME governance context (`home-governance` skill is the SSOT for governance rules).

---

## 1. When to Activate

- **Mandatory** when authoring or updating anything under `docs/architecture/arc42/`.
- **Mandatory** during design inception of a new project or major component (produces `01` §3 Context & Scope).
- **Mandatory** when an architectural change lands (see §4 Update Triggers below).
- Recommended when onboarding a new agent or contributor to a HOME project.

## 2. Where Documentation Lives

- Per-project arc42 root: `docs/architecture/arc42/`
- Three cohesive view files (3-view standard, #342):
  - `01-context-and-building-blocks.md` — §1 Introduction & Goals · §2 Architecture Constraints · §3 System Context & Scope (C4 Context) · §4 Solution Strategy · §5 Building Block View (C4 Container)
  - `02-runtime-and-delivery.md` — §1 Runtime View · §2 Deployment View
  - `03-cross-cutting-and-security.md` — §1 Cross-cutting Concepts · §2 Quality Requirements · §3 Risks & Technical Debt · §4 Glossary · §5 Architecture Decisions (MADR pointer)
- An index `README.md` links the three views and records the document status.
- MADR decisions are indexed in `docs/adr/README.md` — the single authoritative index (arc42 §5 of the third view points there; no duplicate table).
- Diagrams are inline Mermaid blocks (GitHub-renderable), following the `mermaid-diagrams` skill syntax rules.

## 3. Authoring Rules

1. **Cohesive views by default:** documentation lives in the three view files of §2; never fragment into more files and never collapse the views into one monolithic document.
2. **Diagrams are mandatory** in `01` §3 (C4 Context), `01` §5 (C4 Container), and `02` §1 (Runtime) — text-only architecture documentation is not accepted.
3. **Mermaid only** for diagrams; use C4 syntax (`C4Context`, `C4Container`) per the `mermaid-diagrams` skill; validate rendering on GitHub before merge.
4. **No secrets, no personal data** beyond facts already public in the repository (Swiss nLPD — see `home-governance` §2).
5. **English** for all architecture documentation (language policy, `home-governance` §2).
6. **Traceability:** every section that records a decision links the governing MADR/ADR in `docs/adr/README.md`.
7. **Honest status:** unfinished sections are marked `Status: draft` — never leave placeholder text pretending to be content.
8. **Update in the same PR:** an architectural change and its arc42 update travel in the same feature branch and PR.

## 4. Section Update Triggers (for @architect)

| Architectural event | View/section to update |
| :--- | :--- |
| Design inception / new system or actor | **`01` §3 Context & Scope** |
| New/changed application component, agent, skill, or MCP server | **`01` §5 Building Block View** |
| Interaction, API, transport, or protocol change | **`02` §1 Runtime View** |
| Standards, policy, security, or quality-gate change | **`03` §1 Cross-cutting Concepts** |
| Architectural decision taken | **`docs/adr/README.md`** (single MADR index entry) |
| New quality requirement or risk identified | **`03` §2 Quality** / **`03` §3 Risks** |

## 5. View Templates (3-view skeletons)

### `01-context-and-building-blocks.md`
```markdown
# Context & Building Blocks
## 1. Introduction & Goals
### 1.1 Requirements Overview
<Short description of what the system must achieve and who needs it.>
### 1.2 Quality Goals
| Goal | Why it matters |
| :--- | :--- |
### 1.3 Stakeholders & Their Goals
| Stakeholder | Goal |
| :--- | :--- |
## 2. Architecture Constraints
| Constraint | Source | Impact |
| :--- | :--- | :--- |
## 3. System Context & Scope
### 3.1 Business Context
**C4 Context diagram** (Mermaid `C4Context`): the system, its users (Person),
and neighboring systems (System / System_Ext), with labeled relationships.
### 3.2 Technical Context
| Channel | Protocol | Notes |
| :--- | :--- | :--- |
### 3.3 Scope Decisions
- In scope: ... / - Out of scope: ...
## 4. Solution Strategy
- Key architectural decisions summarized (link each to `docs/adr/README.md`).
## 5. Building Block View
### 5.1 Whitebox Overall System
**C4 Container diagram** (Mermaid `C4Container`): containers, technologies,
descriptions, boundaries, and the relationships between them.
### 5.2 Level 2 — Motivation & Explanation
| Building block | Responsibility | Key interfaces |
| :--- | :--- | :--- |
### 5.3 Level 3 (optional)
```
(HOME constraints to always include in §2: trunk+tag lifecycle (MADR-0017), zero-warning CI, Swiss nLPD, board-as-SSOT, technology stack standards.)

### `02-runtime-and-delivery.md`
```markdown
# Runtime & Delivery
## 1. Runtime View
One subsection per important runtime scenario. Each contains a Mermaid
`sequenceDiagram` (or `flowchart`) plus a short narrative:
### 1.x Scenario: <name>
- Trigger / preconditions
- Diagram
- Postconditions / failure modes
## 2. Deployment View
| Node | Hosts | Infrastructure |
| :--- | :--- | :--- |
Include infrastructure-as-code references (OpenTofu/Terraform) where applicable.
```

### `03-cross-cutting-and-security.md`
```markdown
# Cross-cutting Concerns, Quality & Decisions
## 1. Cross-cutting Concepts
### 1.1 Security & Privacy (Swiss nLPD)
### 1.2 Quality Gates & CI
### 1.3 Configuration & Secrets
### 1.4 Language & Communication Policy
### 1.5 Naming & Structure Conventions
## 2. Quality Requirements
| Scenario | Metric | Target |
| :--- | :--- | :--- |
## 3. Risks & Technical Debt
| Risk / Debt | Impact | Mitigation | Tracking issue |
| :--- | :--- | :--- |
## 4. Glossary
| Term | Definition |
| :--- | :--- |
## 5. Architecture Decisions (MADR)
**The authoritative MADR index is `docs/adr/README.md`** — link it, never
duplicate the decision table here. The pre-MADR back-index candidate table
lives in this section.
```

## 6. Documentation Quality Checklist (pre-merge)

- [ ] All 3 view files exist; `README.md` index links them.
- [ ] `01` §3 contains a Mermaid `C4Context` diagram; `01` §5 contains a Mermaid `C4Container` diagram; `02` §1 contains at least one runtime diagram.
- [ ] All Mermaid blocks render on GitHub (no syntax errors, no unsupported features).
- [ ] Every decision referenced links its MADR/ADR in `docs/adr/README.md` (the single MADR index).
- [ ] No secrets, no personal data beyond repo-public facts (gitleaks passes).
- [ ] Links valid, headings consistent, English language, honest `Status:` markers.
- [ ] CI pipeline green (0 warnings / 0 failures), including the skill-presence inventory.

---

*Established by STORY-02 (#59), Epic 3 (#57) — HOME SCRUM Team. §9 wiring followed in STORY-03 (#60); consolidated to the 3-view standard with a single MADR index by #342.*