# 4. Solution Strategy

*Status: seeded (Sprint 03, STORY-02 #59).*

The architecture follows four strategic pillars:

1. **Agent-spec-driven configuration.** Every agent is a Markdown file (`agents/<name>.md`) with YAML frontmatter (model, temperature, permission rules) and a prompt body defining its mandate. The configuration is data, not code — reviewable, diffable, and CI-validated.

2. **Skills as knowledge modules.** Domain knowledge (governance, SCRUM board operations, diagramming, IaC, TDD, …) lives in `skills/<name>/SKILL.md` and is activated contextually. This keeps agent prompts lean and knowledge versioned. CI enforces the skill inventory.

3. **MCP as the only integration layer.** Agents never touch platforms directly; all platform access (GitHub, Intervals.icu, OpenRouter) flows through scoped MCP servers with explicit per-agent permission patterns (allow/deny, last-match-wins). Secrets are provisioned via `{env:VAR}` interpolation from `.secrets.env` (systemd-imported), never stored in the repo.

4. **Board-as-SSOT delivery.** The SCRUM process is encoded in agent specs (`github-scrum-board` skill + #58 state machine) and executed against GitHub Issues/labels/milestones. The autonomous loop delivers into `dev`; humans gate promotions.

Key decisions are indexed in §9 (MADR — wired by STORY-03 #60).