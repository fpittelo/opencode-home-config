---
name: arc42-documentation
description: "Repeatable, modular arc42 method for authoring and maintaining architecture documentation: 12-section templates, Mermaid C4 diagram standards, section update triggers, and a documentation quality checklist for all HOME projects."
---

# arc42 Documentation Method

This skill establishes the **arc42** architecture documentation method for the HOME portfolio of **@fpittelo**. It provides the section templates, authoring rules, and update triggers so that architecture documentation stays maintainable, version-controlled, and diagram-native.

**Authoritative template source:** https://docs.arc42.org/ (arc42 template version 8.0). This skill adapts arc42 to the HOME governance context (`home-governance` skill is the SSOT for governance rules).

---

## 1. When to Activate

- **Mandatory** when authoring or updating anything under `docs/architecture/arc42/`.
- **Mandatory** during design inception of a new project or major component (produces §3 Context & Scope).
- **Mandatory** when an architectural change lands (see §4 Update Triggers below).
- Recommended when onboarding a new agent or contributor to a HOME project.

## 2. Where Documentation Lives

- Per-project arc42 root: `docs/architecture/arc42/`
- One Markdown file per section: `NN-<section-slug>.md` (e.g. `03-context-and-scope.md`)
- An index `README.md` links all sections and records the document status.
- Diagrams are inline Mermaid blocks (GitHub-renderable), following the `mermaid-diagrams` skill syntax rules.

## 3. Authoring Rules

1. **Modular by default:** each section lives in its own file; never create a monolithic architecture document.
2. **Diagrams are mandatory** in §3 (C4 Context), §5 (C4 Container), and §6 (Runtime) — text-only architecture documentation is not accepted.
3. **Mermaid only** for diagrams; use C4 syntax (`C4Context`, `C4Container`) per the `mermaid-diagrams` skill; validate rendering on GitHub before merge.
4. **No secrets, no personal data** beyond facts already public in the repository (Swiss nLPD — see `home-governance` §2).
5. **English** for all architecture documentation (language policy, `home-governance` §2).
6. **Traceability:** every section that records a decision links the governing MADR/ADR in §9.
7. **Honest status:** unfinished sections are marked `Status: draft` — never leave placeholder text pretending to be content.
8. **Update in the same PR:** an architectural change and its arc42 update travel in the same feature branch and PR.

## 4. Section Update Triggers (for @architect)

| Architectural event | Sections to update |
| :--- | :--- |
| Design inception / new system or actor | **§3 Context & Scope** |
| New/changed application component, agent, skill, or MCP server | **§5 Building Block View** |
| Interaction, API, transport, or protocol change | **§6 Runtime View** |
| Standards, policy, security, or quality-gate change | **§8 Cross-cutting Concepts** |
| Architectural decision taken | **§9 Architecture Decisions** (MADR index entry) |
| New quality requirement or risk identified | **§10 Quality** / **§11 Risks** |

## 5. Section Templates

### §1 Introduction & Goals
```markdown
## 1. Introduction & Goals
### 1.1 Requirements Overview
<Short description of what the system must achieve and who needs it.>
### 1.2 Quality Goals
| Goal | Why it matters |
| :--- | :--- |
### 1.3 Stakeholders & Their Goals
| Stakeholder | Goal |
| :--- | :--- |
```

### §2 Architecture Constraints
```markdown
## 2. Architecture Constraints
| Constraint | Source | Impact |
| :--- | :--- | :--- |
```
(HOME constraints to always include: 3-branch lifecycle, zero-warning CI, Swiss nLPD, board-as-SSOT, technology stack standards.)

### §3 System Context & Scope (rich template)
```markdown
## 3. System Context & Scope
### 3.1 Business Context
**C4 Context diagram** (Mermaid `C4Context`): the system, its users (Person),
and neighboring systems (System / System_Ext), with labeled relationships.
### 3.2 Technical Context
| Channel | Protocol | Notes |
| :--- | :--- | :--- |
### 3.3 Scope Decisions
- In scope: ...
- Out of scope: ...
```

### §4 Solution Strategy
```markdown
## 4. Solution Strategy
- Key architectural decisions summarized (link each to §9 MADR entries).
- Building-block approach, cross-cutting approach, and how quality is achieved.
```

### §5 Building Block View (rich template)
```markdown
## 5. Building Block View
### 5.1 Whitebox Overall System
**C4 Container diagram** (Mermaid `C4Container`): containers, technologies,
descriptions, boundaries, and the relationships between them.
### 5.2 Level 2 — Motivation & Explanation
For each important container: purpose, responsibilities, key interfaces.
### 5.3 Level 3 (optional)
Component-level detail only where complexity demands it.
```

### §6 Runtime View (rich template)
```markdown
## 6. Runtime View
One subsection per important runtime scenario. Each contains a Mermaid
`sequenceDiagram` (or `flowchart`) plus a short narrative:
### 6.x Scenario: <name>
- Trigger / preconditions
- Diagram
- Postconditions / failure modes
```

### §7 Deployment View
```markdown
## 7. Deployment View
| Node | Hosts | Infrastructure |
| :--- | :--- | :--- |
Include infrastructure-as-code references (OpenTofu/Terraform) where applicable.
```

### §8 Cross-cutting Concepts (rich template)
```markdown
## 8. Cross-cutting Concepts
### 8.1 Security & Privacy (Swiss nLPD)
### 8.2 Quality Gates & CI
### 8.3 Configuration & Secrets
### 8.4 Language & Communication Policy
### 8.5 Naming & Structure Conventions
```

### §9 Architecture Decision Records (MADR index)
```markdown
## 9. Architecture Decisions
**This section is the MADR decision index.** Each decision is a separate
MADR document under `docs/adr/` (wired by STORY-03, issue #60).

| ADR | Title | Status | Date |
| :--- | :--- | :--- | :--- |
```

### §10 Quality Requirements
```markdown
## 10. Quality Requirements
| Scenario | Metric | Target |
| :--- | :--- | :--- |
```

### §11 Risks & Technical Debt
```markdown
## 11. Risks & Technical Debt
| Risk / Debt | Impact | Mitigation | Tracking issue |
| :--- | :--- | :--- | :--- |
```

### §12 Glossary
```markdown
## 12. Glossary
| Term | Definition |
| :--- | :--- |
```

## 6. Documentation Quality Checklist (pre-merge)

- [ ] All 12 section files exist; `README.md` index links them.
- [ ] §3 contains a Mermaid `C4Context` diagram; §5 contains a Mermaid `C4Container` diagram; §6 contains at least one runtime diagram.
- [ ] All Mermaid blocks render on GitHub (no syntax errors, no unsupported features).
- [ ] Every decision referenced links its MADR/ADR in §9 (or is flagged as pending STORY-03 wiring).
- [ ] No secrets, no personal data beyond repo-public facts (gitleaks passes).
- [ ] Links valid, headings consistent, English language, honest `Status:` markers.
- [ ] CI pipeline green (0 warnings / 0 failures), including the skill-presence inventory.

---

*Established by STORY-02 (#59), Epic 3 (#57) — HOME SCRUM Team. §9 wiring follows in STORY-03 (#60).*