# 8. Cross-cutting Concepts

*Status: seeded (Sprint 03, STORY-02 #59). SSOT: `home-governance` skill.*

## 8.1 Security & Privacy (Swiss nLPD)

- **Zero secrets in repo:** all credentials referenced as `{env:VAR}` in `opencode.jsonc`; actual values live in `~/.config/opencode/.secrets.env`, imported into the systemd user environment. Gitleaks scans the **PR diff on every pull request** (pinned action) and the **full git history weekly and at every qa → main promotion** (MADR-0003; the per-PR full-history scan introduced by #68 is retired).
- **Segregation of duties:** PR reviews are performed by machine account `@devfpittelo` through the dedicated `GITHUB_CODE_REVIEWER` MCP server; cross-impersonation is denied in both directions via permission patterns (#68).
- **Least privilege:** per-agent permission rules scope MCP tool access (e.g. Coach tools for `@coach` only; reviewer tools denied to all other agents).
- **MCP namespace scoping (#150, #207/MADR-0009, MADR-0011):** scoped MCP namespaces follow the defense-in-depth pattern — a global default-deny baseline in `opencode.jsonc` plus explicit per-agent restatement in `agents/*.md`, with `allow` reserved to designated whitelist agents. `COACH_*` (Intervals.icu training data) is @coach-only; `BROWSER_*` (Playwright browser automation — ephemeral profile, loopback-origin allowlist, pinned `@playwright/mcp`) is @developer/@devops-only; `GITHUB_ACTIONS_*` (CI/CD operations) is @devops-only for writes (`actions_run_trigger`) with read-only triage granted to @developer; `GITHUB_SECURITY_*` (code scanning, secret scanning, dependabot alerts — read-only) is @cyber-security-only under raw secret redaction rules; built-in subagents (`explore`, `general`, `task`) inherit zero access to all scoped namespaces. The invariant is machine-enforced by the config gate (`harness/config-validation/check_coach_exclusivity.py`).
- **Bash permission posture (MADR-0004, #158):** allow-by-default with catastrophic-deny guardrails — routine commands run unprompted; a single ask-tier checkpoint covers destructive-but-recoverable operations (`rm *`, kills, global installs, `chmod *` / `chown *`, `systemctl*`); a hard deny tail blocks catastrophic / irreversible / bypass commands (privilege escalation, filesystem and device destruction, block-device redirection, power-off, persistence, git history destruction, network fetchers, inline-code interpreters, environment/secret reads). Rules are evaluated last-match-wins and compound commands (`&&`, `;`, `|`) are judged per segment. Supersedes the #123 per-agent allowlist policy. Unchanged: the `@code-reviewer` read-only allowlist and the `@scrum-master` / `@coach` zero-bash charter (SoD), all file `read`/`edit` credential denies, and the `COACH_*` MCP denies.
- **File-centric secret denies (#167, refines MADR-0004):** the bash deny tail additionally blocks **any command referencing a credential filename** (`*.env*`, `*.pem*`, `*.key*`), closing the read-command-family bypass (`head`, `rg`, `strings`, …) left open by the #158 `cat`-specific deny, which `*.env*` subsumes. Token-named files are excluded (command-agnostic `*token*` over-matches); false positives such as `ls *.pem` block in the safe direction. Interpreter-based reads remain accepted residual (MADR-0004).
- **Boundary separation:** HOME profile and EPFL work profile are strictly isolated (deep-merge shield on the work side); zero personal/professional cross-contamination.

## 8.2 Quality Gates & CI (Proportionate — MADR-0003)

*Status: target state per MADR-0003 (accepted 2026-09-21) — lands progressively with #134 (slim per-PR CI), #133 (deep-validation workflow) and #131 (harness fast path); the legacy 4-job pipeline runs until then.*

- **Proportionate Quality Gates principle:** the cost of a control must be proportional to the risk it mitigates. Every-PR gates run natively in < 90 s; deep checks run weekly and pre-release. Adding a gate requires stating what it catches that existing gates don't (YAGNI); each governance review must identify at least one candidate for removal (KIS).
- **KIS & YAGNI delivery principle (#180):** agents deliver the minimal diff satisfying the issue's acceptance criteria, with brief evidence; scope beyond the ACs is a review finding. Extends MADR-0003's Proportionate Quality Gates principle from pipeline controls to agent delivery behavior (Sprint 08 provenance: #167).
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

## 8.6 Parallel Agent Sessions — Git Worktree Pattern

*Status: adopted 2026-09-21 (#119), from the #107 incident: concurrent agent sessions sharing one working directory cause branch-checkout collisions.*

When multiple agent sessions are dispatched in parallel, each session MUST own an isolated working tree via `git worktree` — never share a checkout:

```bash
# 1. Create (from a synced dev): one worktree per session, named for its issue
git fetch origin && git worktree add -b feature/<issue-#>-<slug> \
  ../wt-<issue-#>-<slug> origin/dev

# 2. Work: cd ../wt-<issue-#>-<slug> — branch, commit, push, PR as normal
#    (the worktree is a full working tree; harness/validators run inside it)

# 3. Clean up (after squash-merge + remote branch deletion; -D because squash
#    merges do not preserve branch ancestry, so -d would refuse):
git worktree remove ../wt-<issue-#>-<slug> && git branch -D feature/<issue-#>-<slug>
```

Rules:
- **One worktree per concurrently active issue**; the shared clone stays parked on `dev` for read-only inspection.
- Worktrees live outside the repo (`../wt-…`) so they never pollute the main checkout or `gitleaks`/docs scans.
- Cleanup is part of the DoD closeout: no `wt-*` directories may outlive their merged issue.
- Single-agent sequential work (the default loop, WIP limit 1) does not need a worktree — plain feature branches in the main checkout remain the norm.

## 8.7 Responsibility Harness — Four-Quadrant Agent Collaboration (MADR-0008)

*Status: adopted 2026-10-03 (#194, MADR-0008). SSOT: MADR-0008; the duty blocks live in the four quadrant agent specs (`agents/architect.md`, `agents/cyber-security.md`, `agents/code-reviewer.md`, `agents/devops.md`).*

The HOME SCRUM Team is a single PO (@fpittelo) leading AI agents. Every collaboration arrow in the harness is **agent-to-agent** — the PO is in the loop for none of the four quadrants:

```
┌────────────────┐    Review Security Impact     ┌────────────────┐
│   Architect    │ ◄───────────────────────────► │ Cyber-Security │
│                │    arc42 Sec 8 & Sec 11       │                │
└───────┬────────┘                               └───────┬────────┘
        │                                                │
        │ MADRs & Specs                                  │ STRIDE & Guardrails
        ▼                                                ▼
┌────────────────┐    Static/Diff Audits         ┌────────────────┐
│ Code-Reviewer  │ ◄───────────────────────────► │ DevOps / CI-CD │
│                │    CVE & Secret Gates         │                │
└────────────────┘                               └────────────────┘
```

- **Architect ↔ Cyber-Security:** designs with security impact (new MCP tools, API integrations, permission changes, auth flows) are reviewed by `@cyber-security` against arc42 §8 (cross-cutting security) & §11 (technical risks) before spec finalization.
- **Architect → Code-Reviewer:** MADRs & specs are handed to `@code-reviewer` as the review baseline.
- **Cyber-Security → DevOps:** STRIDE threat models + guardrail specifications are delivered to `@devops` as implementable CI requirements (gates, not prose).
- **Code-Reviewer ↔ DevOps:** every review verifies CVE & secret gate results (CI evidence); gate gaps are coordinated with `@devops`.

### PO Gate Inventory (closed list — everything else is autonomous)

- **(a) Promotion approvals** `dev` → `qa` → `main` — **one approval per release covers both legs** (codifies the "please, full promotion" practice).
- **(b) Release publication.**
- **(c) Milestone lifecycle** (upstream-blocked).
- **(d) Ask-tier bash checkpoints** (MADR-0004).
- **(e) Reviewer access on new private repos:** grant `@devfpittelo` read access (or make public) at creation time — the SoD reviewer otherwise gets 404 (Sprint 10 finding).

### Agent-probe verification pattern

Runtime acceptance criteria are verified by **agent probes** posting evidence to the issue (precedent: Sprint 09 model probe); the PO intervenes only on failure. This replaces the "PO fresh-session spot-check" as the default AC pattern.