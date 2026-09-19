# 7. Deployment View

*Status: seeded (Sprint 03, STORY-02 #59).*

| Node | Hosts | Infrastructure |
| :--- | :--- | :--- |
| Local workstation (VIDAR, Linux) | OpenCode runtime, agent/skill profile (`~/.config/opencode/`), `.secrets.env` (systemd user environment) | Bare metal |
| Docker runtime (local) | MCP server containers: `GITHUB`, `GITHUB_CODE_REVIEWER`, `COACH DEV/QA/MAIN` | Docker Engine; tokens injected via environment |
| GitHub Actions runners (ubuntu-latest) | CI pipeline jobs (JSONC validation, Gitleaks via Docker) | GitHub-hosted |
| OpenRouter SaaS | LLM inference + `openrouter` remote MCP endpoint | Public HTTPS, OAuth |
| Intervals.icu SaaS | Training analytics backend for Coach MCP | HTTPS API |

**Installation flow:** `install.sh` symlinks profile files from the repo checkout (`SCRIPT_DIR`-relative, path-independent since #68) into `~/.config/opencode/`. Environment secrets are imported into the systemd user environment (see §8.3).

**Infrastructure-as-code:** none for this repo itself (it is configuration, not deployed infrastructure). Cloud workloads are governed in separate `iaac-*` repositories (OpenTofu, per `opentofu-iac` skill).