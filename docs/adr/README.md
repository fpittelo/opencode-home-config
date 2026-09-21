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
| [0001 — Validator tooling for the harness docs quality gate](0001-validator-tooling-for-the-harness-docs-quality-gate-mermaid-links-madr.md) | Mermaid, link, and MADR validation tooling — per-PR render usage superseded by MADR-0003 | accepted | 2026-09-20 |
| [0002 — MCP server efficiency baseline](0002-mcp-server-efficiency-baseline-toolset-scoping-per-agent-tool-denial-pinned-native-transport.md) | Toolset scoping, per-agent tool denial, pinned native transport | accepted | 2026-09-21 |
| [0003 — Proportionate quality gates](0003-proportionate-quality-gates-ci-and-harness-simplification.md) | CI and harness simplification (KIS/YAGNI) | accepted | 2026-09-21 |
