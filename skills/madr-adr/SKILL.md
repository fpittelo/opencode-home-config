# Skill: madr-adr — MADR Decision Records

Authoritative specification for **MADR** (Markdown Anybody Decision Records) in HOME repositories. Every architectural spike or technology introduction MUST be recorded as a numbered MADR under `docs/adr/` and indexed in arc42 §9.

**Mandated for:** `@architect` (creation, acceptance, indexing). Lint enforcement is owned by STORY-04 (#61).

---

## 1. When to Create an ADR

Create a MADR whenever a decision is:

- An **architectural spike** outcome (technology selection, pattern choice, trade-off resolution), or
- A **technology introduction** (new language, framework, provider, MCP server, container base, CI mechanism), or
- A **superseding decision** that invalidates a prior accepted ADR.

Do NOT create ADRs for: implementation details confined to one issue (the issue is the record), routine config chores, or reversible day-to-day tuning.

---

## 2. MADR Template

Files live at `docs/adr/NNNN-<slug>.md` (4-digit zero-padded sequence number; slug derived from the title).

```markdown
# MADR-0000: <short imperative title>

- **Status:** proposed
- **Date:** YYYY-MM-DD
- **Deciders:** <@architect, @fpittelo, other deciders>

## Context

<The architectural forces at play: the problem, the constraints, what triggered this decision.>

## Decision Drivers

- <Driver 1 — e.g., a governance rule, cost constraint, Swiss nLPD privacy constraint>

## Considered Options

### Option 1: <name>

- Pros: <...>
- Cons: <...>

### Option 2: <name>

- Pros: <...>
- Cons: <...>

## Decision Outcome

Chosen option: "<Option name>", because <rationale tying back to the decision drivers>.

## Consequences

- **Positive:** <...>
- **Negative:** <...>
- **Mitigations:** <...>
```

---

## 3. Machine-Checkable Header Schema (for CI lint — STORY-04 #61)

An ADR is **conforming** if and only if ALL of the following hold. A file missing any mandatory field or section is **non-conforming** and must be flagged by lint:

| Check | Rule (regex / condition) |
| :--- | :--- |
| H1 header | `^# MADR-\d{4}: .+$` — number is 4-digit zero-padded and MUST equal the number in the file name |
| Status field | `^- \*\*Status:\*\* (proposed\|accepted\|superseded\|deprecated)( \(superseded by MADR-\d{4}\))?$` |
| Date field | `^- \*\*Date:\*\* \d{4}-\d{2}-\d{2}$` |
| Deciders field | `^- \*\*Deciders:\*\* .+$` |
| Mandatory sections | `## Context`, `## Decision Drivers`, `## Considered Options`, `## Decision Outcome`, `## Consequences` — all present as H2 headings, in this order |
| File naming | `^\d{4}-[a-z0-9-]+\.md$` — sequence numbers unique and gap-free from 0001 |
| No secrets | ADRs MUST NOT contain tokens, keys, or endpoints requiring disclosure (gitleaks applies — Swiss nLPD) |

---

## 4. Creation Workflow

1. **Scaffold:** `bash skills/madr-adr/scripts/new-adr.sh "<title>"` — generates `docs/adr/NNNN-<slug>.md` from the template with the next sequence number. The script refuses to overwrite existing files and exits non-zero on misuse.
2. **Author:** fill every section — no placeholder text may remain at commit time.
3. **Propose → Accept:** new ADRs start as `proposed`. On `@fpittelo` (Product Owner) acceptance, set `Status: accepted`.
4. **Index:** upon acceptance, add the entry to the **arc42 §9 index** (`docs/architecture/arc42/09-architecture-decisions.md`) — number, title, status, link. The `docs/adr/README.md` inventory mirrors this index.
5. **Commit:** ADR files and index updates travel on the feature branch of the work that prompted the decision (or their own `docs/<n>-adr-...` branch) — standard 3-branch lifecycle applies.

---

## 5. Status Lifecycle

```
proposed ──▶ accepted ──▶ superseded (by MADR-NNNN)
                └───────▶ deprecated
```

- **proposed:** drafted, awaiting PO acceptance.
- **accepted:** active and indexed in §9.
- **superseded:** replaced — the old ADR links forward (`Status: superseded (superseded by MADR-NNNN)`), the new ADR references it.
- **deprecated:** deliberately retired without replacement.

---

## 6. KIS Notes

- One decision per ADR. Short and honest beats exhaustive and vague.
- "Negative" consequences are mandatory — no decision is free.
- Do not backfill history: pre-MADR decisions are back-indexed as candidates (see arc42 §9 back-index table) only when they are actually needed going forward.
