# 12. Glossary

*Status: seeded (Sprint 03, STORY-02 #59).*

| Term | Definition |
| :--- | :--- |
| **arc42** | A pragmatic template for architecture documentation (12 sections); https://docs.arc42.org/ |
| **ADR / MADR** | (Markdown) Architecture Decision Record; MADR = Markdown Any Decision Records format |
| **Board-as-SSOT** | The GitHub board (Issues + status labels + sprint marker issues) is the single source of truth for sprint state; no file-based backlogs (MADR-0013) |
| **DoR / DoD** | Definition of Ready (grooming gate) / Definition of Done (closeout gate, 5 criteria) |
| **HOME SCRUM Team** | The six-agent squad (@architect, @scrum-master, @developer, @code-reviewer, @devops, @cyber-security) delivering @fpittelo's personal projects |
| **HOME profile** | This repository's OpenCode configuration (personal domain) — strictly isolated from the EPFL work profile |
| **MCP** | Model Context Protocol — the integration layer through which agents access platforms (GitHub, Intervals.icu, OpenRouter) |
| **OpenCode** | The agentic coding runtime this profile configures |
| **OpenRouter** | LLM gateway providing model routing; the sole enabled provider in this profile |
| **SoD** | Segregation of Duties — PR reviews performed by machine account `@devfpittelo` via a dedicated MCP server, never by the owner identity |
| **Sprint marker issue** | One issue per sprint (epic/sub-issue pattern) expressing sprint membership; created/closed autonomously by @scrum-master (MADR-0013). Milestones are historical records only |
| **Tier A / Tier B** | Branch protection levels: Tier A (light, `dev`), Tier B (strict, `qa`/`main` with mandatory @fpittelo approval) |
| **WIP limit 1** | At most one `status::in-progress` issue per sprint (sprint marker issue) — preserves the sequential issue-by-issue loop |
| **Zero-warning gate** | CI must complete with 0 warnings and 0 failures for any merge |