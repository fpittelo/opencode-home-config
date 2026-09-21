# 9. Architecture Decisions (MADR Index)

*Status: live — wired by STORY-03 (issue #60). ADRs are created via the `madr-adr` skill (`bash skills/madr-adr/scripts/new-adr.sh "<title>"`) and stored under `docs/adr/`; the format and machine-checkable header schema are specified in `skills/madr-adr/SKILL.md` (CI lint enforcement lands with STORY-04, #61).*

**This section is the authoritative index of Architecture Decision Records.** Each decision is recorded as a separate MADR document under `docs/adr/` and indexed here. *Every accepted ADR MUST be listed below (number, title, status, link); the directory-level inventory mirrors this index in `docs/adr/README.md`.*

| ADR | Title | Status | Date |
| :--- | :--- | :--- | :--- |
| [MADR-0001](../../adr/0001-validator-tooling-for-the-harness-docs-quality-gate-mermaid-links-madr.md) | Validator tooling for the harness docs quality gate (mermaid, links, MADR) | accepted | 2026-09-20 |
| [MADR-0002](../../adr/0002-mcp-server-efficiency-baseline-toolset-scoping-per-agent-tool-denial-pinned-native-transport.md) | MCP server efficiency baseline: toolset scoping, per-agent tool denial, pinned native transport | accepted | 2026-09-21 |

## Decisions currently embodied in config/specs (pre-MADR, to be back-indexed)

| Decision | Where recorded | Candidate ADR |
| :--- | :--- | :--- |
| Board-as-SSOT: GitHub Issues + labels + milestones, no Projects v2, no file-based backlogs | Epic 3 #57 refinement note 1 | ADR-0002 candidate |
| SoD: code-reviewer re-platformed to machine account `@devfpittelo` via dedicated MCP server | #52/#53, enforced #68 | ADR-0003 candidate |
| OpenRouter as sole enabled provider; per-agent model assignments | #42, #62 | ADR-0004 candidate |
| Remote OpenRouter MCP server for model-catalog access | #67 | ADR-0005 candidate |
| Mermaid-validation tooling choice for CI gates | STORY-04 #61 refinement note 5 | **Delivered — MADR-0001 (accepted)** |