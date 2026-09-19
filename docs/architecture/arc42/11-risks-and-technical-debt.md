# 11. Risks & Technical Debt

*Status: seeded (Sprint 03, STORY-02 #59).*

| Risk / Debt | Impact | Mitigation | Tracking issue |
| :--- | :--- | :--- | :--- |
| GitHub MCP server lacks branch-delete and milestone CRUD tools → REST fallbacks needed | Medium — hygiene operations require bash+token sessions | REST fallback documented and executed by @architect; upstream enhancement candidate | #66 retro item 3; upstream issue TBD |
| Coach agent permission anomalies: lowercase `github_*` deny rule and server-name-as-key patterns (`"COACH MAIN": allow`) may not match | Medium — coach's GitHub isolation may be void | Fix scheduled as F5 of the architecture review | #56 (F5) |
| Tool-surface bloat: 2× GitHub + 3× COACH + openrouter servers loaded into every agent context | Medium — token bloat, cross-domain access | Per-agent scoping decision pending; requires ADR | #56 (F6) — ADR candidate |
| No invariant test suite (parity gap with work config) | Medium — drift (e.g. unregistered model reference) passes CI silently | STORY planned: minimal pytest suite (model registry validity, secret-interpolation-only, exec bit) | #56 (F4) |
| Permission semantics ("last match wins") verified by spec, not runtime tests | Low–Medium | Live-session witnesses (AC3 of #68 passed); runtime test candidate for harness work | #61 |
| Branch protection on `qa`/`main` still procedural, not technical | Medium — promotion gate not machine-enforced | WP3/WP4 in progress | #46, #49, #50 |