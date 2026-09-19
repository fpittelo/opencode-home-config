# 8. Cross-cutting Concepts

*Status: seeded (Sprint 03, STORY-02 #59). SSOT: `home-governance` skill.*

## 8.1 Security & Privacy (Swiss nLPD)

- **Zero secrets in repo:** all credentials referenced as `{env:VAR}` in `opencode.jsonc`; actual values live in `~/.config/opencode/.secrets.env`, imported into the systemd user environment. Gitleaks scans **full git history** in CI (since #68).
- **Segregation of duties:** PR reviews are performed by machine account `@devfpittelo` through the dedicated `GITHUB_CODE_REVIEWER` MCP server; cross-impersonation is denied in both directions via permission patterns (#68).
- **Least privilege:** per-agent permission rules scope MCP tool access (e.g. Coach tools for `@coach` only; reviewer tools denied to all other agents).
- **Boundary separation:** HOME profile and EPFL work profile are strictly isolated (deep-merge shield on the work side); zero personal/professional cross-contamination.

## 8.2 Quality Gates & CI

- Every merge into `dev`/`qa`/`main` requires a 100% green pipeline: **0 warnings, 0 failures**.
- CI jobs: JSONC validation of `opencode.jsonc`; `bash -n install.sh`; agent-file presence; **skill-presence inventory** (hardcoded list — new skills must be registered here or CI fails); Gitleaks full-history secret scan.
- Local pre-flight mirrors CI before every push.

## 8.3 Configuration & Secrets

- Single runtime config `opencode.jsonc` (JSONC, schema: https://opencode.ai/config.json).
- `enabled_providers: ["openrouter"]` — all model assignments route via OpenRouter (`openrouter/<model>` per agent frontmatter).
- Secrets: `.secrets.env` → systemd user environment → `{env:VAR}` interpolation. OAuth flows (e.g. OpenRouter MCP) are interactive; no tokens stored in the repo.

## 8.4 Language & Communication Policy

- Software engineering deliverables (config, docs, PRs, issues, ADRs): **English**.
- Personal non-software topics (finance, tax, household): **French**.

## 8.5 Naming & Structure Conventions

- Agents: `agents/<role>.md`; skills: `skills/<name>/SKILL.md`; arc42: `docs/architecture/arc42/NN-<slug>.md`; ADRs: `docs/adr/` (wired by #60).
- Branches: `feature/<issue-#>-<slug>`, `fix/<issue-#>-<slug>`, `chore/<issue-#>-<slug>` off `dev`.
- Labels: `type::*`, `status::*`, `agent::*`, `blocker::*`, `severity::*` (see `github-scrum-board` skill).