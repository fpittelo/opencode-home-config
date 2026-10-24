# MADR-0023: Record PO-hotfix model reassignment superseding MADR-0021 rows

- **Status:** accepted
- **Date:** 2026-10-24
- **Deciders:** @fpittelo (PO directive #378, 2026-10-18), @architect (author, audit finding F1 of #408)

## Context

MADR-0021 (2026-10-17) rebalanced per-agent model assignments on a capability-matching rationale: `gpt-6-luna` on `@architect`, `kimi-k2.7-code` on `@developer`, `glm-5.3-flash` on `@scrum-master` (the #304 payload-discipline remediation lever). One day later (2026-10-18), the PO directed an urgent hotfix (#378, merged as #379) after two consecutive `@developer` dispatches on #364 were cancelled mid-flight on `kimi-k2.7-code`: `@developer` moved to `z-ai/glm-5.3-flash` and `@architect` to `deepseek/deepseek-v4.1-flash`. #379 changed the live SSOT (`agents/*.md` front-matter) and the assignment docs, but no MADR recorded the superseding decision — and #378 AC4 (ADR bodies are immutable point-in-time records) meant MADR-0021's body was correctly left untouched, leaving the `docs/adr/README.md` index row for 0021 presenting the dead assignment as active. The 2026-10-24 configuration audit (#408, finding F1) flagged the index↔SSOT contradiction: the `madr-adr` skill §1 mandates that a superseding decision invalidating a prior accepted ADR MUST be recorded.

## Decision Drivers

- **Governance:** superseding decisions MUST be recorded as MADRs and the single index must not contradict the live SSOT (`madr-adr` skill §1/§4; audit finding F1 of #408).
- **Empirical performance:** `kimi-k2.7-code` dispatch cancellations on #364 (#378); PO dissatisfaction with `gpt-6-luna` on the architect role (cost/quality, PO directive).
- **Immutability precedent:** ADR bodies are never rewritten (#378 AC4); partial supersession is annotated in the index only (MADR-0006→0021, 0011→0022, 0014→0018/0022 precedent).

## Considered Options

### Option 1: Record the reassignment as MADR-0023 + index annotation

- Pros: closes the governance gap; index reflects the live state; MADR-0021 body stays immutable; completes the supersession chain 0006 → 0021 → 0023.
- Cons: one additional ADR for what is a two-line configuration state.

### Option 2: Annotate the 0021 index row only, no new ADR

- Pros: minimal diff.
- Cons: the reassignment is itself a superseding decision — leaving it unrecorded repeats exactly the F1 defect class this ADR closes.

### Option 3: Rewrite MADR-0021's assignment table

- Pros: single in-place source.
- Cons: violates the ADR immutability rule (#378 AC4) and the point-in-time record principle.

## Decision Outcome

Chosen option: **"Option 1 — Record the reassignment as MADR-0023 + index annotation"**.

This ADR records the **already-merged** PO directive (#378/#379) — it introduces no new model changes. Current per-agent assignments (live since 2026-10-18, unchanged by this record):

| Agent | MADR-0021 (2026-10-17) | Since #379 (live SSOT) |
| :--- | :--- | :--- |
| `@architect` | `openai/gpt-6-luna` | `deepseek/deepseek-v4.1-flash` |
| `@developer` | `moonshotai/kimi-k2.7-code` | `z-ai/glm-5.3-flash` |

All other MADR-0021 rows remain in force: `@scrum-master` on `glm-5.3-flash` (the #304 remediation lever stands), `@code-reviewer`/`@devops`/`@cyber-security` on `deepseek-v4.1-flash`, `@coach` on `glm-5.3-flash`, root default `gemini-3.8-flash`. The root `opencode.jsonc` model catalog (roster) is unchanged — no additions or removals.

**Supersession:** the MADR-0021 assignment-table rows for `@architect` and `@developer` are superseded by this ADR (index-annotated; MADR-0021's status remains `accepted` because its other decisions, notably the `@scrum-master` remediation, remain in force — the 0006/0011/0014 partial-supersession pattern).

## Consequences

- **Positive:** index↔SSOT coherence restored; supersession chain 0006 → 0021 → 0023 complete; the `madr-adr` §1 recording mandate satisfied; future audits read the true model lineage.
- **Negative:** the flagship (`gpt-6-luna`) and the coding-specialist (`kimi-k2.7-code`) roster entries are currently unassigned — carrying them in the catalog is accepted cost (selectable models carry no assignment cost; roster churn rejected per MADR-0021's stability driver).
- **Mitigations:** quality gates unchanged (zero-warning CI + `@code-reviewer` SoD approval) and remain model-agnostic; if the #378 cancellation pathology recurs on `glm-5.3-flash` on the developer role, re-decide via a new MADR rather than a silent hotfix.
