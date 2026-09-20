# Architecture Decision Records (MADR)

This directory holds the HOME project's Architecture Decision Records in **MADR** format. The authoritative index lives in **arc42 §9**: [`docs/architecture/arc42/09-architecture-decisions.md`](../architecture/arc42/09-architecture-decisions.md).

## Creating an ADR

```bash
bash skills/madr-adr/scripts/new-adr.sh "<short imperative title>"
```

This scaffolds the next sequential `NNNN-<slug>.md` from the template (refuses to overwrite existing files; exits non-zero on misuse). Fill every section, then follow the acceptance and indexing workflow in [`skills/madr-adr/SKILL.md`](../../skills/madr-adr/SKILL.md).

## Status legend

| Status | Meaning |
| :--- | :--- |
| `proposed` | Drafted, awaiting Product Owner acceptance |
| `accepted` | Active — must be indexed in arc42 §9 |
| `superseded` | Replaced by a newer MADR (links forward) |
| `deprecated` | Deliberately retired without replacement |

## Index

| ADR | Title | Status | Date |
| :--- | :--- | :--- | :--- |
| *(empty — first entry will be ADR-0001 per Epic 3 refinement note 5; pre-MADR decisions are listed as back-index candidates in arc42 §9)* | | | |
