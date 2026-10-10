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

Then populate `~/.config/opencode/.secrets-home.env` with your API keys (file is created with `chmod 600`).

## 🧩 Per-pane profile selection (oc-home / oc-work)

OpenCode loads its config once at startup and never hot-reloads. Instead of a global
symlink flip — where the *last install wins* and any instance started after the flip
silently picks up the other profile — the installer provisions
`~/.config/opencode/profiles.sh` with per-pane wrappers:

```bash
oc-home   # runs opencode with the HOME profile (this repo) for that pane only
oc-work   # runs opencode with the WORK profile (opencode-work-config) for that pane only
```

**How it works:** each wrapper sources its profile-scoped secrets file
(`~/.config/opencode/.secrets-home.env` / `.secrets-work.env`, mode 600) inside a
subshell with `set -a` / `set +a`, prefix-assigns `OPENCODE_CONFIG` and
`OPENCODE_CONFIG_DIR` to the profile repo, and ends in `exec opencode "$@"`.
Secrets never persist in the pane shell and are never printed. `install.sh` sources
the snippet from `.bashrc` and `.profile`, and no longer manages a shared
`.secrets.env`: a populated shared file is migrated into `.secrets-home.env`
(mode 600) and removed; the systemd user-environment secret import is retired
(previous imports are unset and verified absent).

**Config-merge caveat:** the global symlink config (`opencode.jsonc`/`agents`/`skills`
pointing to this repo) remains the **base layer** for bare `opencode`; env-var configs
are **merged** over it, so non-conflicting keys (agents, skills, MCP entries) from the
global layer stay visible in every pane. Secrets cannot leak through the config layer:
every MCP environment value is `{env:VAR}`-only or empty — CI-enforced (gitleaks +
config gate).

**⚠️ Bare `opencode` is unsupported for secret-bearing work:** it loads only the
global symlink layer with no profile-scoped secrets. Always launch a profile via
`oc-home` or `oc-work`.

**Trap — never run the other profile's install.sh while instances are running:**
either installer flips the global symlinks; any opencode instance started afterwards
silently picks up the flipped profile (non-deterministic mixed state). Close running
instances first, run the installer, then restart your panes.

**Herdr (VIDAR):** run HOME and WORK simultaneously — one tab/pane per context,
launching `oc-home` in one pane and `oc-work` in the other; `herdr agent list`
recognizes each OpenCode instance independently. Invariant: pane **screen history
stays OFF** — pane output may contain secrets/personal data; never enable capture,
never scrape pane content.

**Residual risks (STRIDE review #253 / MADR-0010, accepted):**

1. Same-UID `/proc/<pid>/environ` exposure of a running pane's environment (RR1).
2. Shared `~/.local/share/opencode/` (`auth.json`, `mcp-auth.json`, session DB, logs,
   tool output) — **explicit PO risk-acceptance (@fpittelo, 2026-10-10)**: provider
   OAuth logins are global; switching profiles does not switch identities.
3. Config-merge key leakage across profiles via the global base layer (RR3) —
   mitigated by the `{env:}`-only invariant (CI-enforced) and documented above.
4. Herdr screen history must stay OFF — re-verify after Herdr or opencode upgrades.
5. Pane children inherit that pane's profile secrets — never run untrusted code from
   a profile pane.
6. The systemd user environment must be secret-free post-migration — `install.sh`
   unsets and verifies; re-check after upgrades.
7. Secrets files live outside any repo — host backups and dotfile copies are
   secret-bearing; keep them out of any synced store.
8. The legacy shared `.secrets.env` is emptied/removed after migration — do not
   recreate it; the wrappers no longer read it.
9. The WORK installer (work repo #177) still rewrites `profiles.sh` wholesale and
   removes `oc-home()`; re-run HOME `install.sh` to restore it (mirrored fix tracked
   in the work repo).

## Recommended Directory Structure on VIDAR

```
~/projects/
├── opencode-home-config/          ← this repo (HOME config, global default)
├── opencode-work-config/           ← EPFL work config (GitLab, via VPN)
├── HOME/                           ← personal projects (HOME profile)
│   └── my-personal-project/
└── WORK/                           ← EPFL work projects (WORK profile)
    └── my-epfl-service/
```

See the [Migration Plan v3.1](docs/opencode-config-migration-plan-v3.1.md), Section 5 for details on how the WORK profile is activated inside `~/projects/WORK/` projects.

## Security

- **Zero hardcoded secrets:** All credentials use `{env:VAR}` interpolation.
- **Profile-scoped secrets:** `~/.config/opencode/.secrets-home.env` (HOME) and
  `.secrets-work.env` (WORK), mode 600, sourced only inside the per-pane wrapper
  subshell (never committed, covered by `.gitignore`).
- **Directory hardening:** `~/.config/opencode` is mode 700; `install.sh` fails
  closed if any secrets file is group/world-readable.
- **Gitleaks scanning:** CI pipeline scans every push and PR.

## Governance

This repository follows the HOME SCRUM 3-branch lifecycle: `dev` (integration) → `qa` (staging) → `main` (production). All merges require 100% clean CI.

---

**Architecture:** Golden Architecture v3.1  
**Author:** `@architect` (HOME SCRUM Squad)  
