# MADR-0031: Model roster refresh — four catalog additions and @architect on Gemini 4 Carbon

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** @fpittelo (PO directive #489, 2026-11-22), @architect (author)

## Context

The PO directed a model roster refresh for `opencode-home-config` (#489, 2026-11-22) with two atomic moves: expand the `provider.openrouter.models` catalog in `opencode.jsonc` by four entries, and move `@architect` from `z-ai/glm-5.3-flash` to `google/gemini-4-carbon`.

Catalog evidence (OpenRouter API, 2026-11-22, 476-model catalog; re-verified at implementation time on #489):

| Requested slug | Status | Notes |
| :--- | :--- | :--- |
| `google/gemini-4-carbon` | present | canonical `20261110`; 1,048,576 ctx; $2/M prompt, $10/M completion; **reasoning mandatory**, supported efforts `high`/`medium`/`low`, default `medium` |
| `mistralai/mistral-large-4-0` | present | 1,048,576 ctx; $0.70/M prompt, $2.10/M completion |
| `moonshotai/kimi-k3.1-pro` | present | 1,048,576 ctx; $0.253/M prompt, $8.80/M completion |
| `typesafe/jev-1.13` | **absent** | only `typesafe/jev-router` exists under the `typesafe` vendor |
| `typesafe/jev-router` | present | 1,000,000 ctx; the PO-authorized substitute for the unavailable `typesafe/jev-1.13` |

The absent `typesafe/jev-1.13` was not silently substituted: the PO authorized `typesafe/jev-router` in a recorded decision on #489 (comment `7077272350`, 2026-11-22), and the exact substitute slug was re-verified against the live catalog before the entry was added.

Prior state: `@architect` was assigned `z-ai/glm-5.3-flash` by MADR-0025 (the 2026-11-14 roster refresh), which itself superseded the assignment rows of MADR-0023 and MADR-0021.

## Decision Drivers

- **Governance:** model-roster changes form a recorded lineage (MADR-0006 → 0021 → 0023 → 0025 → **0031**) and a superseding decision MUST be a MADR with the single index kept consistent (`madr-adr` skill §1/§4; #378/#408 audit precedent: unrecorded reassignments are a defect).
- **PO directive:** the four catalog additions and the `@architect` reassignment are the PO's explicit choice of 2026-11-22 (#489).
- **Cost awareness:** `google/gemini-4-carbon` is reasoning-mandatory at $2/M prompt / $10/M completion — a step up in cost from `z-ai/glm-5.3-flash` for the architect role; accepted by PO directive and recorded here.
- **KIS/YAGNI:** the change is additive-only — no catalog removals, no renames, no variant entries, no other agent touched.
- **Immutability precedent:** ADR bodies are never rewritten (#378 AC4); partial supersession is annotated in the index only (0006→0021, 0011→0022, 0014→0018/0022, 0025→0031 pattern).

## Considered Options

### Option 1: Add the four catalog entries and reassign @architect (chosen)

- Pros: executes the PO directive in one atomic change; the catalog gains the requested models; `@architect` lands on the PO-selected reasoning model; supersession chain extended to 0031; additive-only, so no agent loses access to a model.
- Cons: the architect role moves to a pricier reasoning-mandatory model; the substitute slug differs from the originally requested `typesafe/jev-1.13`.

### Option 2: Add the four catalog entries only, leave @architect on glm-5.3-flash

- Pros: no cost increase on the architect role.
- Cons: contradicts the PO directive; the reassignment would happen unrecorded later, which is the defect class the 0006→0025 lineage exists to prevent.

### Option 3: Substitute `typesafe/jev-router` without a recorded PO decision (or drop the fourth entry)

- Pros: none material — fewer entries or a smaller decision record.
- Cons: violates the "no substitution without PO decision" guard; dropping the entry ignores the authorized PO direction. Rejected.

## Decision Outcome

Chosen option: **"Option 1 — Add the four catalog entries and reassign @architect"**.

`provider.openrouter.models` in `opencode.jsonc` gains exactly four entries, appended after the pre-existing eight (no existing key reordered or modified):

| Slug | Display name |
| :--- | :--- |
| `google/gemini-4-carbon` | `Gemini 4 Carbon` |
| `mistralai/mistral-large-4-0` | `Mistral Large 4.0` |
| `moonshotai/kimi-k3.1-pro` | `Kimi K3.1 Pro` |
| `typesafe/jev-router` | `Jev Router` |

Agent assignment (live SSOT in `agents/*.md` front-matter):

| Agent | Before (MADR-0025) | After (this MADR) |
| :--- | :--- | :--- |
| `@architect` | `z-ai/glm-5.3-flash` | `google/gemini-4-carbon` |

Unchanged (out of scope): every other agent assignment — `@code-reviewer`, `@devops`, `@scrum-master`, `@coach` remain on `glm-5.3-flash`, `@developer` on `deepseek/deepseek-v4.1-flash-1017`, `@cyber-security` on `minimax/minimax-m3.1-flash`; root `model`/`small_model` remain `google/gemini-3.8-flash`; `default_agent` remains `architect`. No catalog entry is pruned or renamed.

**PO-authorized substitution:** `typesafe/jev-1.13` is absent from the OpenRouter catalog (verified 2026-11-22). Per the PO authorization recorded on #489 (comment `7077272350`, 2026-11-22), `typesafe/jev-router` is added in its place. No other substitution is authorized.

**Cost flag:** `google/gemini-4-carbon` is reasoning-mandatory with default effort `medium`; the architect role's per-invocation cost rises accordingly (accepted by PO directive). Quality gates are model-agnostic and unchanged.

**Supersession:** the `@architect` assignment row of MADR-0025 is superseded by this ADR (index-annotated; MADR-0025 keeps `Status: accepted` because its other assignment rows and its catalog-prune decision remain in force — the partial-supersession pattern).

## Consequences

- **Positive:** the roster carries the four PO-requested models; `@architect` runs on the PO-selected reasoning model; the decision lineage 0006 → 0021 → 0023 → 0025 → 0031 stays complete and index-consistent.
- **Negative:** a higher-cost, reasoning-mandatory model now drives the architect role; an authorized substitute (`jev-router`) occupies the catalog slot requested as `jev-1.13`.
- **Mitigations:** zero-warning CI and the `@code-reviewer` SoD approval are model-agnostic; the cost delta is accepted and recorded; the substitute is explicitly traced to its PO decision so no later reader mistakes it for a silent swap.
