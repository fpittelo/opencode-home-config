# 8. Cross-cutting Concepts

*Status: seeded (Sprint 03, STORY-02 #59). SSOT: `home-governance` skill.*

## 8.1 Security & Privacy (Swiss nLPD)

- **Zero secrets in repo:** all credentials referenced as `{env:VAR}` in `opencode.jsonc`; actual values live in `~/.config/opencode/.secrets.env`, imported into the systemd user environment. Gitleaks scans the **PR diff on every pull request** (pinned action) and the **full git history weekly and at every qa → main promotion** (MADR-0003; the per-PR full-history scan introduced by #68 is retired).
- **Segregation of duties:** PR reviews are performed by machine account `@devfpittelo` through the dedicated `GITHUB_CODE_REVIEWER` MCP server; cross-impersonation is denied in both directions via permission patterns (#68).
- **Least privilege:** per-agent permission rules scope MCP tool access (e.g. Coach tools for `@coach` only; reviewer tools denied to all other agents).
- **Boundary separation:** HOME profile and EPFL work profile are strictly isolated (deep-merge shield on the work side); zero personal/professional cross-contamination.

## 8.2 Quality Gates & CI (Proportionate — MADR-0003)

*Status: target state per MADR-0003 (accepted 2026-09-21) — lands progressively with #134 (slim per-PR CI), #133 (deep-validation workflow) and #131 (harness fast path); the legacy 4-job pipeline runs until then.*

- **Proportionate Quality Gates principle:** the cost of a control must be proportional to the risk it mitigates. Every-PR gates run natively in < 90 s; deep checks run weekly and pre-release. Adding a gate requires stating what it catches that existing gates don't (YAGNI); each governance review must identify at least one candidate for removal (KIS).
- **Per-PR gate (single native job, zero Docker):** JSONC validation of `opencode.jsonc`; `bash -n install.sh`; agent-file presence; skill-presence inventory; **diff-scoped pinned gitleaks**; native link and MADR validators; native Mermaid **syntax** check; label-conditional architecture gate.
- **Deep validation (weekly cron + every qa → main promotion):** full-history gitleaks; Chromium render-level Mermaid validation (docs-validator image); image-build verification.
- **Harness runner images:** built on `workflow_dispatch` / `harness-v*` tags only — not on every `harness/docker/**` change.
- **Local pre-flight:** native fast path first (host toolchain); the container path remains the reproducibility fallback with the original security flags and two-phase deps/gate design.
- Every merge into `dev`/`qa`/`main` still requires a 100% green pipeline: **0 warnings, 0 failures** — unchanged.

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