# MADR-0025: Model roster refresh — glm-5.3-flash review tier and new DeepSeek and MiniMax snapshots

- **Status:** accepted
- **Date:** 2026-11-14
- **Deciders:** @fpittelo (PO directive #431, 2026-11-14), @architect (author)

## Context

Per-agent model assignments were last set by MADR-0021 (2026-10-17) and corrected by the PO hotfix recorded in MADR-0023 (2026-10-18, #378/#379). On 2026-11-14 the PO directed a fresh roster refresh (#431) covering five roles, verbatim:

> "I want to refresh the agents models:"

| Agent | New model | Currently |
| :--- | :--- | :--- |
| `@architect` | `glm-5.3-flash` | `deepseek-v4.1-flash` |
| `@developer` | `deepseek-v4.1-flash-1017` | `glm-5.3-flash` |
| `@code-reviewer` | `glm-5.3-flash` | `deepseek-v4.1-flash` |
| `@devops` | `glm-5.3-flash` | `deepseek-v4.1-flash` |
| `@cyber-security` | MiniMax M3.1 Flash | `deepseek-v4.1-flash` |

The directive also prunes the retired snapshot: with all five moves executed, `deepseek/deepseek-v4.1-flash` (Sep 10 snapshot) has **no agent assigned**, and the PO decided (2026-11-14) to **remove it from the `opencode.jsonc` models list** rather than carry it unassigned. Its successor snapshot `deepseek/deepseek-v4.1-flash-1017` (Oct 17) takes over for `@developer`.

Catalog evidence (OpenRouter MCP, 2026-11-14): `deepseek/deepseek-v4.1-flash-1017` exists (Oct 17 snapshot; 1M ctx; tools + structured outputs; prompt $0.038/M vs $0.0507/M for the outgoing flash); `minimax/minimax-m3.1-flash` exists (Oct 19 snapshot; 1M ctx; prompt $0.15/M, off-peak $0.075/M). `z-ai/glm-5.3-flash` was already in the models list — the three agents moving **to** it require no catalog change.

## Decision Drivers

- **Governance:** superseding decisions MUST be recorded as MADRs and the single index must not contradict the live SSOT (`madr-adr` skill §1/§4); model-roster changes are a recorded lineage (0006 → 0021 → 0023 → **0025**).
- **PO directive:** the assignment table above is the PO's explicit choice for the 2026-11-14 refresh.
- **Cost awareness:** the security-triage role lands on a reasoning-mandatory model (see below); the cost implication must be recorded even though no capability or access changes.
- **Roster hygiene:** an unassigned snapshot is dead weight — the PO elected to prune it rather than carry it.
- **Immutability precedent:** ADR bodies are never rewritten (#378 AC4); partial supersession is annotated in the index only (0006→0021, 0011→0022, 0014→0018/0022 precedent).

## Considered Options

### Option 1: Record the refresh as MADR-0025 with the five assignments and the roster prune (chosen)

- Pros: records the superseding decision; index reflects the live state; supersession chain extended to 0025; the unassigned snapshot is pruned atomically with the assignments that orphan it.
- Cons: one additional ADR for a configuration state; the prune removes a selectable model from the catalog.

### Option 2: Apply the assignments only, keep the unassigned snapshot in the catalog

- Pros: minimal catalog churn; the snapshot remains manually selectable.
- Cons: leaves an orphaned roster entry the PO explicitly retired; contradicts the PO decision of 2026-11-14.

### Option 3: Rewrite MADR-0021/MADR-0023 assignment rows in place

- Pros: single in-place source.
- Cons: violates the ADR immutability rule (#378 AC4) and the point-in-time record principle.

## Decision Outcome

Chosen option: **"Option 1 — Record the refresh as MADR-0025 with the five assignments and the roster prune"**.

Per-agent assignments after this decision (live SSOT in `agents/*.md` front-matter):

| Agent | Before (MADR-0023 / live since #379) | After (this MADR) |
| :--- | :--- | :--- |
| `@architect` | `deepseek/deepseek-v4.1-flash` | `z-ai/glm-5.3-flash` |
| `@developer` | `z-ai/glm-5.3-flash` | `deepseek/deepseek-v4.1-flash-1017` |
| `@code-reviewer` | `deepseek/deepseek-v4.1-flash` | `z-ai/glm-5.3-flash` |
| `@devops` | `deepseek/deepseek-v4.1-flash` | `z-ai/glm-5.3-flash` |
| `@cyber-security` | `deepseek/deepseek-v4.1-flash` | `minimax/minimax-m3.1-flash` |

Unchanged (out of scope): `@scrum-master` on `glm-5.3-flash` (the #304 remediation lever stands), `@coach` on `glm-5.3-flash`, root default/small `gemini-3.8-flash`. The `glm-5.3-flash` review tier (architect + code-reviewer + devops) is the directive's central move.

**Model-list pruning:** `deepseek/deepseek-v4.1-flash` is removed from the `opencode.jsonc` `models` map (PO decision 2026-11-14). This removal is safe only **atomically with the assignment flip** — four agents referenced it until this change. `deepseek/deepseek-v4.1-flash-1017` and `minimax/minimax-m3.1-flash` are added to the map with display names `DeepSeek V4.1 Flash 1017` and `MiniMax M3.1 Flash`.

**MiniMax cost flag:** `minimax/minimax-m3.1-flash` is **reasoning-mandatory with default effort `max`** — a material cost consideration for the security-triage role. Its catalog description highlights agentic/coding/**cybersecurity** strengths, which is the rationale for the assignment. No capability or access change results; the cost/perf implication is recorded here for awareness only.

**Provenance note:** after this change no agent remains on the retired `deepseek/deepseek-v4.1-flash` (Sep 10) snapshot; `@developer` moves to its `-1017` successor.

**Supersession:** the **assignment rows** of MADR-0023 (its `@architect`/`@developer` rows) and the overlapping **assignment rows** of MADR-0021 are superseded by this ADR (index-annotated; both prior ADRs keep `Status: accepted` because their other decisions — MADR-0021's `@scrum-master` remediation, MADR-0023's supersession record — remain in force; the 0006/0011/0014 partial-supersession pattern). MADR-0021's **gate-role** content is untouched by this ADR.

## Consequences

- **Positive:** the review tier (architect + code-reviewer + devops) runs on `glm-5.3-flash` per the directive; the developer role moves to the cheaper, newer DeepSeek snapshot; the security-triage role gains a cybersecurity-tuned model; the orphaned snapshot is pruned; supersession chain 0006 → 0021 → 0023 → 0025 extended.
- **Negative:** `@cyber-security` on a reasoning-mandatory, `max`-effort model raises per-invocation cost — accepted and recorded; a new model on the security-triage role carries output-quality risk during the transition.
- **Mitigations:** quality gates unchanged (zero-warning CI + `@code-reviewer` SoD approval) and model-agnostic; observe the next sprint's security-triage findings and re-decide via a new MADR if needed.
