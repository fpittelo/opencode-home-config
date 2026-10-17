# MADR-0021: Model roster rebalance — capability-matched per-agent assignments

- **Status:** accepted
- **Date:** 2026-10-17
- **Deciders:** @fpittelo (PO directive "go" executing audit recommendation #343, 2026-10-17), @architect (author)

## Context

MADR-0006 (Sprint 09) assigned `openai/gpt-6-luna` — the roster's flagship reasoning model — to `@scrum-master`, while `@developer` (dual-stack Rust/Python implementation under `mypy --strict` + zero-warning gates) and `@architect` (architecture trade-offs, ADRs, threat modeling) ran on flash-tier models. The 2026-10-17 architecture audit flagged this as an **inverted allocation**: the most expensive reasoning capacity spent on mechanical ticket moves (label flips, DoD checklists), the most intellectually demanding roles on the lightest models.

The audit also collected four sprints of empirical evidence that the `gpt-6-luna`-driven `@scrum-master` repeatedly violates minimal-payload MCP discipline (#304 failure mode: pre-filling `parent_issue_number` on update calls — #218, #221, #229, and again on 2026-10-17 during the #338 closeout), forcing Closeout-Fallback escalations to `@architect`.

## Decision Drivers

- **Capability-to-task matching:** reasoning depth belongs where reasoning is consumed (code, architecture), not where determinism suffices (board state transitions).
- **Empirical compliance evidence:** the #304 pathology recurred on the flagship model despite explicit prompt-level prohibitions — model-level remediation is the remaining lever.
- **Cost proportionality:** flash-tier models for high-frequency mechanical roles; flagship only where its capability pays for itself.
- **Roster stability:** no new models introduced; the rebalance uses only models already in the `opencode.jsonc` roster (MADR-0006 introduced `gpt-6-luna`; `kimi-k2.7-code` was already available for selection).

## Considered Options

### Option 1: Capability-matched rebalance (chosen)

- Pros: flagship moves to the architect role (deep reasoning where it compounds); coding-specialized model on the developer role; cheap compliant flash model on the mechanical scrum-master role; zero roster changes.
- Cons: per-agent behavior shifts (review gates must observe the new models' output quality); scrum-master loses deep reasoning it never productively used.

### Option 2: Status quo (MADR-0006 assignments)

- Pros: zero change.
- Cons: permanent inverted allocation; #304 pathology lever unused.

### Option 3: Flagship for developer AND architect

- Pros: maximum capability on both build roles.
- Cons: doubles flagship spend; architect and developer rarely run concurrently (WIP=1) — the marginal benefit does not justify the cost (YAGNI).

## Decision Outcome

Chosen option: **"Option 1 — Capability-matched rebalance"**:

| Agent | Before (MADR-0006) | After | Rationale |
| :--- | :--- | :--- | :--- |
| `@architect` | `z-ai/glm-5.3-flash` | `openai/gpt-6-luna` | Deep reasoning for architecture trade-offs, ADRs, threat modeling — the flagship compounds here. |
| `@developer` | `z-ai/glm-5.3-flash` | `moonshotai/kimi-k2.7-code` | Coding-specialized model for dual-stack implementation under strict gates. |
| `@scrum-master` | `openai/gpt-6-luna` | `z-ai/glm-5.3-flash` | Mechanical board transitions need determinism and payload discipline, not deep reasoning; flash-tier is the #304 remediation lever. |
| `@code-reviewer` | `deepseek/deepseek-v4.1-flash` | unchanged | Fast, effective gate performance across Sprints 19–21. |
| `@devops` | `deepseek/deepseek-v4.1-flash` | unchanged | Same. |
| `@cyber-security` | `deepseek/deepseek-v4.1-flash` | unchanged | Same. |
| `@coach` | `z-ai/glm-5.3-flash` | unchanged | Conversational domain role. |
| Root default/small | `google/gemini-3.8-flash` | unchanged | Fallback only; every agent declares its own model. |

**Supersession:** this decision supersedes MADR-0006's per-agent assignment table (its GPT-6 Luna introduction and roster entries remain valid history). The root `opencode.jsonc` model list is unchanged — no roster additions or removals.

## Consequences

- **Positive:** flagship reasoning where it compounds (architecture); coding-specialized model on implementation; scrum-master cost and #304 pathology addressed at the model level; zero roster churn.
- **Negative:** output-quality risk during the transition (new models on developer/architect roles) — mitigated by the unchanged zero-warning CI gate + formal review gate, which catch regressions regardless of model; scrum-master compliance is empirical-probability, not a guarantee (the #344 bash allowlist and #350 hardening remain structural mitigations).
- **Mitigations:** unchanged quality gates (CI 0-warnings, @code-reviewer SoD approval); observe the next sprint's review findings for model-attributable defects and re-decide if needed.
