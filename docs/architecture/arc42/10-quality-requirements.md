# 10. Quality Requirements

*Status: seeded (Sprint 03, STORY-02 #59).*

| Scenario | Metric | Target |
| :--- | :--- | :--- |
| Merge into `dev`/`qa`/`main` | CI pipeline result | 100% green — 0 warnings, 0 failures |
| Secret leakage | Gitleaks findings (full history) | 0 findings on every scan |
| Config validity | JSONC parse of `opencode.jsonc` | Valid on every CI run |
| Delivery autonomy | Human interventions per sprint | Only promotion approvals + live-verification witnesses |
| Traceability | Issues closed without DoD evidence links | 0 (scrum-master rejects such closeouts) |
| Review integrity | Reviews attributed to `@fpittelo` by `@code-reviewer` | 0 — all reviews under `@devfpittelo` (SoD) |
| Documentation freshness | Architectural change without same-PR arc42 update | 0 occurrences |
| Agent permission integrity | Cross-impersonation capability between agent identities | 0 (deny rules verified per change) |