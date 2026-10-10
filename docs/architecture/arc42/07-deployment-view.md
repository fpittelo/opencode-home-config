# 7. Deployment View

*Status: seeded (Sprint 03, STORY-02 #59).*

| Node | Hosts | Infrastructure |
| :--- | :--- | :--- |
| Local workstation (VIDAR, Linux) | OpenCode runtime, agent/skill profile (`~/.config/opencode/`), profile-scoped secrets files (`.secrets-home.env` / `.secrets-work.env`, mode 600, MADR-0010), `github-mcp-server` native binary (`~/.local/bin/`, pinned v1.12.2, checksum-verified by `install.sh`) | Bare metal |
| Docker runtime (local) | MCP server container: `COACH_DEV/QA/MAIN` (toggle pattern — one enabled at a time) | Docker Engine; tokens injected via environment |
| GitHub Actions runners (ubuntu-latest) | CI pipeline jobs (JSONC validation, Gitleaks via Docker) | GitHub-hosted |
| OpenRouter SaaS | LLM inference + `openrouter` remote MCP endpoint | Public HTTPS, OAuth |
| Intervals.icu SaaS | Training analytics backend for Coach MCP | HTTPS API |

**Installation flow:** `install.sh` symlinks profile files from the repo checkout (`SCRIPT_DIR`-relative, path-independent since #68) into `~/.config/opencode/`, provisions `profiles.sh` with the per-pane `oc-home()` wrapper, and migrates secrets to the profile-scoped file. Secrets are sourced per-pane inside the wrapper subshell; the systemd user environment is retired and verified secret-free post-install (see §8.3, MADR-0010).

**Infrastructure-as-code:** none for this repo itself (it is configuration, not deployed infrastructure). Cloud workloads are governed in separate `iaac-*` repositories (OpenTofu, per `opentofu-iac` skill).