# OpenCode Home Configuration

**Personal AI agents, skills, MCP tools, and global profile** for Frederic Pitteloud (@fpittelo).

This repository implements the **Golden Architecture v3.1** — fully decoupled from the enterprise work configuration, with native workspace scoping, `{env:VAR}` secret interpolation, and zero hardcoded credentials.

## Repository Structure

```
opencode-home-config/
├── .github/workflows/ci.yml   # JSONC validation + Gitleaks scan
├── .gitignore
├── install.sh                 # Idempotent Linux/WSL bootstrap
├── opencode.jsonc            # Global default profile for HOME
├── agents/                   # HOME SCRUM Team Agents (7)
│   ├── architect.md
│   ├── coach.md
│   ├── code-reviewer.md
│   ├── cyber-security.md
│   ├── developer.md
│   ├── devops.md
│   └── scrum-master.md
└── skills/                   # Personal Skills (10)
    ├── coach/
    ├── docker-expert/
    ├── fastmcp-builder/
    ├── find-skills/
    ├── github-scrum-board/
    ├── home-governance/
    ├── mermaid-diagrams/
    ├── opentofu-iac/
    ├── release-automation/
    └── test-driven-development/
```

## Installation

```bash
git clone git@github.com:fpittelo/opencode-home-config.git ~/projects/opencode-home-config
cd ~/projects/opencode-home-config
chmod +x install.sh && ./install.sh
```

Then populate `~/.config/opencode/.secrets.env` with your API keys (file is created with `chmod 600`).

## Security

- **Zero hardcoded secrets:** All credentials use `{env:VAR}` interpolation.
- **Secrets file:** `~/.config/opencode/.secrets.env` (never committed, in `.gitignore`).
- **Gitleaks scanning:** CI pipeline scans every push and PR.

## Governance

This repository follows the HOME SCRUM 3-branch lifecycle: `dev` (integration) → `qa` (staging) → `main` (production). All merges require 100% clean CI.

---

**Architecture:** Golden Architecture v3.1  
**Author:** `@architect` (HOME SCRUM Squad)  
