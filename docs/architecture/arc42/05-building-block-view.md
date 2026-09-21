# 5. Building Block View

*Status: seeded (Sprint 03, STORY-02 #59).*

## 5.1 Whitebox Overall System

```mermaid
C4Container
    title Container Diagram — HOME OpenCode Profile

    Person(fpittelo, "@fpittelo", "Product Owner")
    System_Ext(github, "GitHub", "Issues, PRs, CI, releases")
    System_Ext(openrouter_api, "OpenRouter", "LLM inference & MCP")
    System_Ext(intervals, "Intervals.icu", "Training analytics")

    Container_Boundary(home_profile, "HOME OpenCode Profile (installed to ~/.config/opencode)") {
        Container(opencode_jsonc, "opencode.jsonc", "JSONC", "Provider scoping, MCP server registry, env interpolation")
        Container(agents, "Agent Specs (7)", "Markdown + YAML frontmatter", "Mandates, models, permission rules per agent")
        Container(skills, "Skills (11)", "Markdown", "Governance, SCRUM board, arc42, mermaid, IaC, TDD, ...")
        Container(installer, "install.sh", "Bash", "Path-independent symlinking into ~/.config/opencode")
        Container(ci, "CI Pipeline", "GitHub Actions", "JSONC validation, agent/skill presence, Gitleaks history scan")
        Container(arc42docs, "arc42 Docs", "Markdown", "Architecture documentation (this tree)")
    }

    Container_Boundary(mcp_servers, "MCP Servers (Docker / remote)") {
        Container(mcp_github, "GITHUB MCP", "Docker container", "Board & repo operations as @fpittelo")
        Container(mcp_reviewer, "GITHUB_CODE_REVIEWER MCP", "Docker container", "Formal PR reviews as @devfpittelo (SoD)")
        Container(mcp_coach, "COACH_DEV/QA/MAIN MCP", "Docker containers", "Intervals.icu coaching, env-scoped")
        Container(mcp_openrouter, "openrouter MCP", "Remote streamable-HTTP", "Model catalog & docs lookup, OAuth")
    }

    Rel(fpittelo, agents, "Owns & approves")
    Rel(agents, mcp_github, "Board ops via", "GITHUB_* tools")
    Rel(agents, mcp_reviewer, "Reviews via (code-reviewer only)", "GITHUB_CODE_REVIEWER_*")
    Rel(agents, mcp_coach, "Coaching via (coach only)", "COACH_* tools")
    Rel(agents, mcp_openrouter, "Model catalog via", "openrouter_* tools")
    Rel(agents, openrouter_api, "LLM inference via", "HTTPS")
    Rel(mcp_github, github, "Operates", "REST API")
    Rel(mcp_reviewer, github, "Reviews as @devfpittelo", "REST")
    Rel(mcp_coach, intervals, "Reads/writes training data", "HTTPS")
    Rel(mcp_openrouter, openrouter_api, "Serves catalog", "MCP over HTTPS")
    Rel(installer, agents, "Symlinks profile files")
    Rel(ci, opencode_jsonc, "Validates JSONC + secrets")
```

## 5.2 Level 2 — Motivation & Explanation

| Building block | Responsibility | Key interfaces |
| :--- | :--- | :--- |
| `opencode.jsonc` | Single runtime configuration: `enabled_providers: ["openrouter"]`, MCP registry, `{env:VAR}` secret interpolation | OpenCode runtime schema (https://opencode.ai/config.json) |
| `agents/*.md` (7) | Role mandates, model assignments, permission boundaries (allow/deny, last-match-wins) | OpenCode agent loading; frontmatter schema |
| `skills/*/SKILL.md` (11) | Versioned domain knowledge activated on demand | Skill frontmatter (`name`, `description`) |
| `install.sh` | Path-independent installation (symlinks from `SCRIPT_DIR`) into `~/.config/opencode` | Bash, systemd env import |
| `.github/workflows/ci.yml` | Zero-warning gate: JSONC validation, agent/skill presence inventory, Gitleaks full-history scan | GitHub Actions |
| MCP servers | Platform integration with credential isolation; SoD via separate server + machine account | MCP stdio (Docker) / streamable-HTTP (remote) |

**Permission model invariants (enforced since #68, extended by #108):**
- `@code-reviewer`: `GITHUB_*: deny` then `GITHUB_CODE_REVIEWER_*: allow` — acts ONLY as `@devfpittelo`.
- All other agents: `GITHUB_*: allow` then `GITHUB_CODE_REVIEWER_*: deny` — cannot impersonate the reviewer.
- `@coach` only: `COACH_DEV_*` / `COACH_QA_*` / `COACH_MAIN_*`: allow — Coach MCP is coach-only (SoD).
- All other agents: `COACH_DEV_*` / `COACH_QA_*` / `COACH_MAIN_*`: deny.
- `@architect` and `@coach` only: `openrouter_*: allow`; all other agents `openrouter_*: deny` (supersedes #67's "all agents" rule).

## 5.3 Level 3

Not required at this stage — the profile is configuration, not layered code. Component-level detail may be added for the harness (`harness/`) if it grows.