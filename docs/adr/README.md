# Architecture Decision Records (MADR)

This directory holds the HOME project's Architecture Decision Records in **MADR** format. The authoritative index lives in **arc42 §9**: [`docs/architecture/arc42/09-architecture-decisions.md`](../architecture/arc42/09-architecture-decisions.md).

## Creating an ADR

```bash
bash skills/madr-adr/scripts/new-adr.sh "<short imperative title>"
```

This scaffolds the next sequential `NNNN-<slug>.md` from the template (refuses to overwrite existing files; exits non-zero on misuse). Fill every section, then follow the acceptance and indexing workflow in [`skills/madr-adr/SKILL.md`](../../skills/madr-adr/SKILL.md).

## Status legend

| Status | Meaning |
| :--- | :--- |
| `proposed` | Drafted, awaiting Product Owner acceptance |
| `accepted` | Active — must be indexed in arc42 §9 |
| `superseded` | Replaced by a newer MADR (links forward) |
| `deprecated` | Deliberately retired without replacement |

## Index

| ADR | Title | Status | Date |
| :--- | :--- | :--- | :--- |
| [0001 — Validator tooling for the harness docs quality gate](0001-validator-tooling-for-the-harness-docs-quality-gate-mermaid-links-madr.md) | Mermaid, link, and MADR validation tooling — per-PR render usage superseded by MADR-0003 | accepted | 2026-09-20 |
| [0002 — MCP server efficiency baseline](0002-mcp-server-efficiency-baseline-toolset-scoping-per-agent-tool-denial-pinned-native-transport.md) | Toolset scoping, per-agent tool denial, pinned native transport | accepted | 2026-09-21 |
| [0003 — Proportionate quality gates](0003-proportionate-quality-gates-ci-and-harness-simplification.md) | CI and harness simplification (KIS/YAGNI) | accepted | 2026-09-21 |
| [0004 — Allow-by-default bash permission posture](0004-allow-by-default-bash-permission-posture.md) | Allow-by-default bash posture with catastrophic-deny guardrails (supersedes the #123 allowlist policy) | accepted | 2026-10-03 |
| [0005 — Adopt Herdr agent runtime](0005-adopt-herdr-agent-runtime.md) | Herdr agent runtime for OpenCode on VIDAR — pinned binary, default-on idempotent install, local-only | accepted | 2026-10-03 |
| [0006 — Sprint 09 model roster refresh](0006-sprint-09-model-roster-gpt-6-luna-introduction-and-per-agent-assignment-refresh.md) | GPT-6 Luna introduction and per-agent assignment refresh (architect/scrum-master/devops switches) | accepted | 2026-10-03 |
| [0007 — Portfolio standardization — FPITTELO PROJECT TEMPLATE](0007-portfolio-standardization-fpittelo-project-template.md) | Template-repo mechanism and FPITTELO PROJECT STANDARD v1 (adoption: scaffold new projects, retrofit existing incrementally, pilot coach) | accepted | 2026-10-03 |
| [0008 — Responsibility harness — single PO, AI-agent SCRUM team](0008-responsibility-harness-single-po-ai-agent-team.md) | Four-quadrant agent collaboration, PO Gate Inventory (a)–(e), agent-probe verification pattern | accepted | 2026-10-03 |
| [0009 — Playwright browser MCP with agent access scoping](0009-playwright-browser-mcp-agent-access-scoping.md) | `BROWSER` MCP (@playwright/mcp, pinned, isolated profile, origin allowlist) — `BROWSER_*` allow for @developer/@devops only, deny baseline for all others | accepted | 2026-10-04 |
| [0010 — Per-pane dual-profile coexistence and secrets isolation](0010-per-pane-profile-selection-and-secrets-isolation.md) | Per-pane `oc-home`/`oc-work` selection (subshell + exec), profile-scoped secrets (`.secrets-home.env`, mode 600), shared `.secrets.env` + systemd import retired, explicit PO risk-acceptance for shared provider OAuth tokens | accepted | 2026-10-10 |
| [0011 — Curated GitHub MCP toolset expansion](0011-curated-github-mcp-toolset-expansion-and-per-agent-permission-scoping.md) | Dedicated namespaced servers `GITHUB_ACTIONS` and `GITHUB_SECURITY` (read-only), per-agent scoping (@devops/@developer for actions, @cyber-security for security alerts), projects/discussions rejected (YAGNI) | accepted | 2026-10-10 |
| [0012 — Promotion topology — eliminate per-release reconcile PRs](0012-promotion-topology-eliminate-per-release-reconcile-prs.md) | Retain three branches; promotions `dev → qa` / `qa → main` executed as merge-commit PRs (never squash); reconcile-PR class retired | accepted | 2026-10-10 |
