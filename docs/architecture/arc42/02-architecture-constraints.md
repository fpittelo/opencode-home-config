# 2. Architecture Constraints

*Status: seeded (Sprint 03, STORY-02 #59). SSOT: `home-governance` skill.*

| Constraint | Source | Impact |
| :--- | :--- | :--- |
| Three persistent branches (`dev`, `qa`, `main`); feature branches only merge into `dev` | `home-governance` Rule 1–3 | All delivery automation is shaped around this lifecycle. |
| Zero-tolerance quality gate: CI with 0 warnings / 0 failures on every merge | `home-governance` Rule 4 | CI pipeline (JSONC validation + Gitleaks) is a merge precondition. |
| Promotion gates require explicit @fpittelo approval (`dev`→`qa`, `qa`→`main`) | `home-governance` Rule 5 | Autonomous loop stops at `dev`; promotions are human-gated. |
| Swiss nLPD / FADP data protection; personal data local & encrypted | `home-governance` §2 | No personal data in config/docs; secrets via `{env:VAR}` interpolation only. |
| Board-as-SSOT: GitHub Issues + labels + milestones (no file-based backlogs, no Projects v2) | Epic 3 (#57) refinement | SCRUM state machine maps onto the label taxonomy. |
| Segregation of duties: reviews by machine account `@devfpittelo` via `GITHUB_CODE_REVIEWER_*` MCP only | #52/#53, enforced by #68 | Permission patterns deny cross-access in both directions. |
| Technology stack: Python ≥ 3.12 (FastMCP/Pydantic v2) for MCP tooling; Rust stable for control planes | `home-governance` §3 | Harness images and future MCP servers follow these standards. |
| Language policy: software deliverables in English; personal topics in French | `home-governance` §2 | All config, docs, PRs, issues in English. |