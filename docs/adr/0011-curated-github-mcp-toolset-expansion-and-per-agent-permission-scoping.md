# MADR-0011: Curated GitHub MCP Toolset Expansion and Per-Agent Permission Scoping

- **Status:** accepted
- **Date:** 2026-10-10
- **Deciders:** @fpittelo (PO approval 2026-10-10), @architect, @cyber-security (Security Review #254 — verdict APPROVE-WITH-CONDITIONS, controls C1–C9)
- **Driven by:** issue #252 (US-2401) · Prerequisite: #254 (Architecture & Security Spike)

## Context

The initial GitHub MCP server integration (MADR-0002) operates on the default toolsets (`repos`, `issues`, `pull_requests`, `context`, `users`, `copilot`), with `GITHUB_CODE_REVIEWER` constrained to `context,repos,pull_requests` for separation of duties. While this minimized prompt overhead (~127 KB schema baseline), it created operational friction across delivery and auditing workflows (US-2401 / #252):

1. **CI/CD triage is blind:** `@devops` and `@developer` cannot query workflow runs, check failing step logs, or trigger workflows (`actions` toolset disabled).
2. **Security automation is blocked:** Dependabot, Secret Scanning, and CodeQL alerts cannot be reviewed or triaged programmatically by `@cyber-security` (`code_security`, `secret_protection`, and `dependabot` toolsets disabled).

US-2401 proposed activating all disabled toolsets (`actions`, `code_security`, `projects`, `discussions`) or enabling `--toolsets all`, and evaluating **Dynamic Toolset Discovery**.

Architecture Spike #254 and Cyber-Security Review investigated the pinned binary (`v1.12.2`, commit `85598ba6`) and established:

1. **Dynamic Toolset Discovery is obsolete and removed:** upstream PR `#2512` (May 2026) removed dynamic tool discovery entirely. In `v1.12.2`, `--dynamic-toolsets` is an unknown flag. Static toolset selection via `--toolsets` is the sole supported mechanism.
2. **Shared-server topology flaw:** adding extended toolsets directly to the shared `GITHUB` server would auto-grant all tools to five agents (`@architect`, `@developer`, `@devops`, `@scrum-master`, `@cyber-security`), violating least-privilege by default and causing prompt schema bloat (+40–60%).
3. **Monolithic tool risks:** `actions_run_trigger` combines workflow dispatch, cancellation, and log deletion into a single tool parameterized by `method`. OpenCode permission patterns match tool names, not argument payloads; parameter-level restrictions cannot be expressed at the config layer.
4. **Secret-scanning exposure:** `secret_protection` alert payloads contain detected secret material and file locations; unconstrained access risks leaking credentials into general development conversations and egressing to model providers (Swiss nLPD cross-border processor disclosure).

## Decision Drivers

- **Least privilege per agent (MADR-0002, MADR-0008):** each agent receives only the tools essential to its specific SCRUM role.
- **KIS & YAGNI (#180):** no speculative scope; reject capabilities without an active, verified operational need.
- **Prompt context efficiency (MADR-0002):** keep system prompt schemas lean to prevent latency regressions and tool selection confusion.
- **Swiss nLPD & credential containment:** strict segregation and redaction of secret scanning and vulnerability data.
- **Fail-closed machine enforcement:** security boundaries machine-validated by automated CI quality gates.

## Considered Options

### Option 1: Enable `--toolsets all` on the shared `GITHUB` server
- Pros: Zero new server definitions.
- Cons: Injects 64+ tools (~180 KB schema) into every agent's prompt on every turn; auto-grants destructive actions and secret-scanning alerts to all agents; violates least privilege; high prompt latency penalty. Rejected.

### Option 2: Dynamic Toolset Discovery (`GITHUB_DYNAMIC_TOOLSETS=1` / `--dynamic-toolsets`)
- Pros: Theoretical on-demand tool loading.
- Cons: Removed upstream in PR `#2512`; unsupported in pinned binary `v1.12.2` (unknown flag); rejected by upstream maintainers due to agent confusion and client-side tool search evolution. Rejected.

### Option 3: Dedicated namespaced servers with per-agent scoping (Chosen)
- Pros: Follows proven `COACH_*` and `BROWSER_*` topology patterns; preserves lean default schemas for agents that do not need extended capabilities; enforces strict separation of duties and read-only flags at the process level.
- Cons: Introduces two additional local MCP server definitions in `opencode.jsonc`.

## Decision Outcome

Chosen option: **Option 3 — Dedicated namespaced servers with per-agent scoping**, governed by Mandatory Conditions C1–C9:

1. **Reject `projects` and `discussions` (C9, YAGNI #180):** HOME SCRUM operates on GitHub Milestones/Issues/Labels. Discussions are inactive. Omission eliminates the broad `project` PAT scope and unnecessary attack surface.
2. **Dedicated Namespaced Servers (C1):** Do not modify the shared `GITHUB` server toolsets. Provision two dedicated local MCP servers:
   - `GITHUB_ACTIONS`: `--toolsets=actions` (write-capable native binary).
   - `GITHUB_SECURITY`: `--toolsets=code_security,secret_protection,dependabot --read-only` (read-only native binary).
3. **Actions Access Scoping (C3, C4):**
   - `@devops`: allow `GITHUB_ACTIONS_*` (full CI/CD operations; workflow cancellation and log deletion are documented accepted residuals for the trusted CI owner).
   - `@developer`: allow read-only operations (`GITHUB_ACTIONS_actions_get`, `GITHUB_ACTIONS_actions_list`, `GITHUB_ACTIONS_get_job_logs`); explicitly deny `GITHUB_ACTIONS_actions_run_trigger`.
   - All other agents (`@architect`, `@scrum-master`, `@code-reviewer`, `@coach`): deny `GITHUB_ACTIONS_*`.
4. **Security Toolset Access Scoping (C2):**
   - `@cyber-security`: allow `GITHUB_SECURITY_*` exclusively.
   - Server runs with `--read-only` flag enforced at process startup.
   - All other agents: deny `GITHUB_SECURITY_*`.
   - **Redaction Rule:** Raw secret payloads and tokens from `get_secret_scanning_alert` must be redacted before recording in issue or PR threads.
5. **Machine-Enforced CI Gates (C8):**
   - Extend `harness/config-validation/check_coach_exclusivity.py` to enforce global default-deny baselines and agent allowlists for `GITHUB_ACTIONS` and `GITHUB_SECURITY`.
   - Add flag validation asserting `GITHUB_SECURITY` carries `--read-only` and neither server enables `projects`, `discussions`, or `all`.

## Consequences

- **Positive:**
  - `@devops` and `@developer` gain complete CI run inspection and job log triage capabilities.
  - `@cyber-security` gains automated vulnerability, dependency, and secret scanning audit tools.
  - Zero schema bloat for `@scrum-master`, `@architect`, `@code-reviewer`, and `@coach`.
  - Least privilege strictly enforced; `actions_run_trigger` blocked for `@developer`.
  - No broad `project` PAT scope required on host credentials.
- **Negative:**
  - Two additional `github-mcp-server` processes spawned when OpenCode starts (~20 MB memory each, milliseconds startup via native binary).
- **Residual Risks (Accepted):**
  - `@devops` holds monolithic `actions_run_trigger` (can delete workflow logs or cancel runs): accepted residual for the trusted CI owner; operations are audited by GitHub-side audit logs and tied to sprint issues.
  - Secret scanning alert metadata egresses to OpenRouter (US) when `@cyber-security` analyzes findings: accepted Swiss nLPD processor disclosure with redaction controls.
