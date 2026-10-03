# MADR-0006: Sprint 09 model roster — GPT-6 Luna introduction and per-agent assignment refresh

- **Status:** accepted
- **Date:** 2026-10-03
- **Deciders:** @fpittelo (PO directive, Sprint 09 grooming)

## Context

The HOME OpenCode profile routes every SCRUM agent through OpenRouter. The provider list in
`opencode.jsonc` currently exposes six models, and per-agent model assignments were made ad hoc
in earlier sprints (issues #42, #62) — arc42 §9 has carried them as a "future ADR candidate"
ever since. The architect mandate (`agents/architect.md`, MADR section) requires every
technology introduction to be recorded as a MADR, and `openai/gpt-6-luna` entering the HOME
runtime is exactly such an introduction.

GPT-6 Luna was verified live on OpenRouter (2026-10-03): canonical slug
`openai/gpt-6-luna-20260922`, 1.05M-token context window, $0.10/$0.50 per million tokens
(input/output), tool-capable, reasoning supported. The Sprint 09 PO directive (2026-10-03)
groomed the refresh: introduce GPT-6 Luna and reassign three agents to their new primary
models, executing after #180 so the switch lands on KIS-governed agent specs.

## Decision Drivers

- **Technology-introduction governance:** a new model entering the runtime requires a MADR
  (architect mandate) and arc42 §9 indexing.
- **Discharge the §9 candidate note:** per-agent model assignments (#42/#62) must stop being a
  "future ADR candidate" and receive a discharging record.
- **Capability/cost fit per workload:** each agent's model should match its workload —
  long-context orchestration, fast routine delivery, deterministic review.
- **KIS/YAGNI (MADR-0003, #180):** minimal diff — one roster entry, three frontmatter lines,
  no permission-block or session-default changes.

## Considered Options

### Option 1: Status quo — six-model roster, current assignments

- Pros: zero change risk; all agents remain on verified models.
- Cons: ignores the PO directive; the §9 candidate note stays open; no long-context model in
  the roster for orchestration-heavy roles.

### Option 2: Introduce GPT-6 Luna + reassign architect/scrum-master/devops (chosen)

- Pros: roster gains a verified 1.05M-context, tool-capable model; @scrum-master moves to
  GPT-6 Luna (sprint orchestration benefits from long-context synthesis); @architect and
  @devops move to flash-tier models already proven in the roster (`z-ai/glm-5.3-flash`,
  `deepseek/deepseek-v4.1-flash`); the §9 candidate note is discharged.
- Cons: three agent behavior changes land at once (mitigated: each switch is a one-line
  frontmatter change, trivially reversible).

### Option 3: Introduce GPT-6 Luna without per-agent reassignment

- Pros: smallest possible diff.
- Cons: adds an unused roster entry (YAGNI violation); leaves the PO directive half-done; the
  §9 candidate note stays open.

## Decision Outcome

Chosen option: **Option 2**, implemented in `opencode.jsonc` and `agents/*.md`:

1. **Roster:** add `"openai/gpt-6-luna": { "name": "GPT-6 Luna" }` to
   `provider.openrouter.models` — roster grows 6 → 7. Session defaults `model`/`small_model`
   stay `openrouter/google/gemini-3.8-flash`.
2. **Agent switches (frontmatter `model:` line only):**
   - `agents/architect.md`: `openrouter/z-ai/glm-5.3` → `openrouter/z-ai/glm-5.3-flash`
   - `agents/scrum-master.md`: `openrouter/z-ai/glm-5.3-flash` → `openrouter/openai/gpt-6-luna`
   - `agents/devops.md`: `openrouter/z-ai/glm-5.3-flash` → `openrouter/deepseek/deepseek-v4.1-flash`
3. **Unchanged (explicit):** @developer and @coach (`z-ai/glm-5.3-flash`), @code-reviewer and
   @cyber-security (`deepseek/deepseek-v4.1-flash`); permission blocks byte-identical.

Docs sync: Admin Guide §3.2 (agent table Model column) and §3.5 (model table + default-model
snippet) updated to the post-change truth. arc42 §9 gains the MADR-0006 row and the
per-agent-assignments candidate row (#42/#62) is marked **Delivered — MADR-0006 (accepted)**.

## Consequences

- **Positive:** roster 6 → 7 with a verified long-context, tool-capable model; per-agent model
  assignments finally have a governing record (§9 candidate note discharged); admin guide
  tables match the live config again.
- **Negative:** changes take effect only at the next session start — running sessions keep
  their stale model snapshot (documented stale-snapshot behavior; PO fresh-session
  verification is AC6 of #181).
- **Neutral:** `z-ai/glm-5.3`, `moonshotai/kimi-k2.7-code` and `qwen/qwen3.8-2.4t-a95b` remain
  in the roster as selectable-but-unassigned models.