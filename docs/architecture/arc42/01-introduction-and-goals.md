# 1. Introduction & Goals

*Status: seeded (Sprint 03, STORY-02 #59).*

## 1.1 Requirements Overview

The **HOME OpenCode profile** is the agent runtime configuration that turns OpenCode into a governed, autonomous software-delivery team for the personal ecosystem of **Frederic Pitteloud (@fpittelo)**. It must:

- Provide **seven specialized agents** (architect, scrum-master, developer, code-reviewer, devops, cyber-security, coach) with precise mandates, model assignments, and permission boundaries.
- Integrate **MCP servers** (GitHub, GitHub Code Reviewer, Coach, OpenRouter) so agents operate on real platforms with real credentials — without ever handling secrets in plaintext.
- Enforce **deterministic, auditable SCRUM delivery** anchored to GitHub Issues, labels, and milestones (board-as-SSOT).
- Separate the HOME (personal) profile from the professional work profile (`opencode-work-config`) with zero cross-contamination.

## 1.2 Quality Goals

| Goal | Why it matters |
| :--- | :--- |
| Deterministic agent collaboration | Autonomous sprint delivery must not require human intervention except at promotion gates. |
| Auditability | Every delivery decision is traceable on the GitHub board (issue → PR → review → merge). |
| Security & privacy | Swiss nLPD compliance; zero secrets in repo; segregation of duties for reviews. |
| Zero-warning quality | Every merge passes CI with 0 warnings / 0 failures. |

## 1.3 Stakeholders & Their Goals

| Stakeholder | Goal |
| :--- | :--- |
| @fpittelo (Product Owner) | Governed autonomy: the squad delivers sprints autonomously; he approves only promotions (`dev`→`qa`→`main`). |
| HOME SCRUM agents | Clear mandates, tool access scoped to their role, no permission leakage. |
| @devfpittelo (machine account) | Independent review identity enabling segregation of duties. |