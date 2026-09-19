# arc42 Architecture Documentation — HOME OpenCode Profile

Architecture documentation for the **HOME OpenCode configuration** (`opencode-home-config`), following the **arc42** template (v8.0) as operationalized by the `arc42-documentation` skill.

**Document status:** seeded in Sprint 03 (STORY-02, issue #59). §9 MADR index is wired by STORY-03 (issue #60).

## Index

| Section | File | Status |
| :--- | :--- | :--- |
| 1. Introduction & Goals | [01-introduction-and-goals.md](01-introduction-and-goals.md) | seeded |
| 2. Architecture Constraints | [02-architecture-constraints.md](02-architecture-constraints.md) | seeded |
| 3. System Context & Scope | [03-context-and-scope.md](03-context-and-scope.md) | seeded (C4 Context) |
| 4. Solution Strategy | [04-solution-strategy.md](04-solution-strategy.md) | seeded |
| 5. Building Block View | [05-building-block-view.md](05-building-block-view.md) | seeded (C4 Container) |
| 6. Runtime View | [06-runtime-view.md](06-runtime-view.md) | seeded (sprint loop) |
| 7. Deployment View | [07-deployment-view.md](07-deployment-view.md) | seeded |
| 8. Cross-cutting Concepts | [08-cross-cutting-concepts.md](08-cross-cutting-concepts.md) | seeded |
| 9. Architecture Decisions (MADR index) | [09-architecture-decisions.md](09-architecture-decisions.md) | placeholder — wired by #60 |
| 10. Quality Requirements | [10-quality-requirements.md](10-quality-requirements.md) | seeded |
| 11. Risks & Technical Debt | [11-risks-and-technical-debt.md](11-risks-and-technical-debt.md) | seeded |
| 12. Glossary | [12-glossary.md](12-glossary.md) | seeded |

## Maintenance Rules

- Update triggers per section: see the `arc42-documentation` skill §4.
- An architectural change and its arc42 update travel in the **same PR**.
- Governance SSOT remains the `home-governance` skill; this documentation describes, it does not govern.