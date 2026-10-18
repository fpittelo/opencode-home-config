# Admin and User Guide — OpenCode HOME Configuration

> **Version:** v1.2.0 | **Date:** 2026-09-07 | **Author:** `@architect` (HOME SCRUM Squad)

---

## Table of Contents

1. [What is OpenCode?](#1-what-is-opencode)
2. [Admin Guide](#2-admin-guide)
   - [Prerequisites](#21-prerequisites)
   - [Installation](#22-installation)
   - [Secrets Management](#23-secrets-management)
   - [Directory Structure](#24-directory-structure)
   - [Trunk+Tag Git Lifecycle](#25-trunktag-git-lifecycle)
   - [MCP Servers](#26-mcp-servers)
   - [Herdr Agent Runtime](#27-herdr-agent-runtime)
   - [CI/CD Pipeline](#28-cicd-pipeline)
   - [Troubleshooting](#29-troubleshooting)
   - [GitHub PAT Permissions Checklist](#210-github-pat-permissions-checklist)
3. [User Guide](#3-user-guide)
   - [Starting a Session](#31-starting-a-session)
   - [Agents](#32-agents)
   - [Skills](#33-skills)
   - [MCP Tools](#34-mcp-tools)
   - [Models](#35-models)
   - [Daily Workflow](#36-daily-workflow)
   - [Dos and Donts](#37-dos-and-donts)
   - [Permission Posture & Safety Guardrails](#38-permission-posture--safety-guardrails)
4. [Switching Between HOME and WORK Profiles](#4-switching-between-home-and-work-profiles)
   - [How Profile Switching Works](#41-how-profile-switching-works)
   - [Switch to HOME Profile](#42-switch-to-home-profile)
   - [Switch to WORK Profile](#43-switch-to-work-profile)
   - [Verify Active Profile](#44-verify-active-profile)
   - [Project-Level Overrides (Deep-Merge Shielding)](#45-project-level-overrides-deep-merge-shielding)
   - [Warnings](#46-warnings)

---

## 1. What is OpenCode?

OpenCode is an AI-powered coding assistant that runs on your workstation. It uses **agents** (specialized AI personas like an architect, developer, or coach), **skills** (domain-specific knowledge modules), and **MCP tools** (external service connectors like GitHub and Intervals.icu) to help you work on projects. OpenCode reads a configuration file (`opencode.jsonc`) that defines which AI models to use, which agents and skills are available, and which external tools are connected.

You run OpenCode by navigating to a project directory and launching a profile wrapper — `oc-home` for the HOME profile, `oc-work` for the WORK profile (see §4). Bare `opencode` is unsupported for secret-bearing work: it loads only the global base layer with no profile-scoped secrets. The agents then help you plan, code, review, and manage your work — all from your terminal.

---

## 2. Admin Guide

This section is for the person who sets up and maintains the OpenCode environment on a workstation (e.g., VIDAR).

### 2.1 Prerequisites

| Requirement | Details |
|:---|:---|
| **OS** | Linux (tested on Ubuntu/Debian) |
| **Shell** | `bash` (for `~/.bashrc` + `~/.profile` sourcing) |
| **Docker** | Installed and running (for MCP containers) |
| **OpenCode CLI** | Installed at `~/.opencode/bin/opencode` (v1.18.29+) |
| **Git** | Installed and configured with SSH keys for GitHub |
| **openssl** | Installed (required by `install.sh` to verify the pinned `@playwright/mcp` tarball integrity, #207) |
| **GitHub account** | With access to `fpittelo/opencode-home-config` |

### 2.2 Installation

Clone-and-install commands: SSOT is [README — Installation](../README.md).

**What `install.sh` does:**

| Step | Action | Target |
|:---|:---|:---|
| 1 | Symlink the config file | `~/.config/opencode/opencode.jsonc` → repo's `opencode.jsonc` |
| 1 | Symlink the agents directory | `~/.config/opencode/agents` → repo's `agents/` |
| 1 | Symlink the skills directory | `~/.config/opencode/skills` → repo's `skills/` |
| 2 | Install pinned `github-mcp-server` v2.0.2 binary — downloaded from the official GitHub release, SHA256-verified against the published release checksums file (skipped if the pinned version is already installed) | `~/.local/bin/github-mcp-server` |
| 3 | Install pinned `herdr` v0.9.3 binary — downloaded from the official Herdr release, SHA256-verified against the pinned release-asset digest (skipped if the pinned version is already installed) | `~/.local/bin/herdr` |
| 4 | Verify the pinned `@playwright/mcp` v0.0.83 registry tarball (SHA512 via `openssl`; read-only pin-time audit — nothing is installed, `npx` resolves the pinned version at session start) | npm registry (verification only) |
| 5 | Pre-pull the pinned Coach image | `ghcr.io/fpittelo/coach:dev` (Docker) |
| 6 | Provision `profiles.sh` with the `oc-home()` wrapper (appended without clobbering `oc-work()`) | `~/.config/opencode/profiles.sh` |
| 7 | Create or migrate the profile-scoped secrets file (chmod 600, umask 077; a populated shared `.secrets.env` is migrated into it and removed) | `~/.config/opencode/.secrets-home.env` |
| 8 | Retire the legacy mechanism: remove `.secrets.env` sourcing from `~/.bashrc` / `~/.profile`, unset the systemd user environment (verified secret-free), remove the legacy `/AI_OS_ROOT` switcher | `~/.bashrc`, `~/.profile`, systemd user session |

The installer is **idempotent** — running it again will update the symlinks but will NOT overwrite existing secrets files (`.secrets-home.env`).

### 2.3 Secrets Management

Secrets mechanics (profile-scoped files, per-pane wrapper-subshell sourcing, bare-`opencode` restriction): SSOT is [README — Per-pane profile selection](../README.md) and arc42 [Security & Privacy §1.1](architecture/arc42/03-cross-cutting-and-security.md).

**Required environment variables (HOME profile):**

| Variable | Purpose | Where to get it |
|:---|:---|:---|
| `OPENROUTER_HOME_API_KEY` | OpenRouter API access (all AI models) | https://openrouter.ai/keys |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub MCP server (issues, PRs, releases) | https://github.com/settings/tokens (fine-grained, read/write) |
| `GITHUB_TOKEN_CODE_REVIEWER` | GitHub MCP server for @code-reviewer (the @devfpittelo machine account — PR approvals under separation of duties) | https://github.com/settings/tokens (fine-grained, read/write) |
| `INTERVALS_API_KEY` | Intervals.icu API (coach MCP — workout data) | https://intervals.icu/api/v1/auth |
| `INTERVALS_ATHLETE_ID` | Intervals.icu athlete ID (coach MCP) | https://intervals.icu/athlete (numeric ID in URL) |

**To populate secrets:**

```bash
# Edit the file (created by install.sh)
nano ~/.config/opencode/.secrets-home.env

# Fill in your keys (replace the <...> placeholders):
# export OPENROUTER_HOME_API_KEY="<your-openrouter-key>"
# export GITHUB_PERSONAL_ACCESS_TOKEN="<your-github-token>"
# export GITHUB_TOKEN_CODE_REVIEWER="<your-code-reviewer-token>"
# export INTERVALS_API_KEY="<your-intervals-key>"
# export INTERVALS_ATHLETE_ID="<your-athlete-id>"

# Verify permissions
ls -la ~/.config/opencode/.secrets-home.env
# Should show: -rw------- ... .secrets-home.env

# Load secrets by launching the profile wrapper (secrets are confined to the
# wrapper subshell — they do not persist in the pane shell after exit)
oc-home

# Verify all 5 keys are populated inside the pane (without printing values)
for v in OPENROUTER_HOME_API_KEY GITHUB_PERSONAL_ACCESS_TOKEN GITHUB_TOKEN_CODE_REVIEWER INTERVALS_API_KEY INTERVALS_ATHLETE_ID; do
    echo "$v: $([ -n "${!v}" ] && echo 'OK' || echo 'EMPTY')"
done
```

> **Security:** Never print secret values. Never commit `.secrets-home.env`. The `.gitignore` already excludes it. Gitleaks scans every push in CI.

### 2.4 Directory Structure

SSOT: [README — Recommended Directory Structure on VIDAR](../README.md).

### 2.5 Trunk+Tag Git Lifecycle

SSOT: the `home-governance` skill §5 ([SKILL.md](../skills/home-governance/SKILL.md), MADR-0017) — single trunk `main`, feature-branch isolation, squash merge, tag-from-trunk releases under explicit PO approval; summarized in [README — Governance](../README.md).

### 2.6 MCP Servers

SSOT: arc42 [Context & Building Blocks §5](architecture/arc42/01-context-and-building-blocks.md) — C4 container view, building-block table, and the namespace-exclusivity invariants; runtime registry: [opencode.jsonc](../opencode.jsonc).

### 2.7 Herdr Agent Runtime

*Since #148 (MADR-0005, 2026-10-03), VIDAR runs the **Herdr agent runtime** — a terminal
multiplexer purpose-built for coding agents. Herdr hosts OpenCode TUI panes as real PTYs, so agent
sessions survive terminal detach and Herdr server restarts, and a sidebar shows live agent state
(working / blocked / idle) across all projects.*

**Agent-facing skill:** HOME SCRUM agents operate Herdr through the tracked skill
`skills/herdr/SKILL.md` (#170) — scope-gated on `HERDR_ENV=1` and explicit user intent; the
pane-history-off invariant below also binds agent usage (no pane-content scraping).

**Client / server model:**

| Piece | What it is | How you use it |
|:---|:---|:---|
| Herdr server | Background process hosting the panes (auto-spawned on first `herdr` start — no systemd unit) | `herdr server stop` stops it; restarting restores the saved layout |
| Herdr client (TUI) | The terminal UI you interact with | Start/reattach with `herdr` |
| OpenCode panes | Real PTY panes running `opencode` (HOME SCRUM agents) | Detach with `ctrl+b q` — panes keep running; reattach later with `herdr` |
| Integration plugins | Files Herdr wrote into `~/.config/opencode/` that report OpenCode session state + session IDs to the server over the local Unix socket `~/.config/herdr/herdr.sock` | Managed by Herdr — see lifecycle below |

**Daily usage:**

```bash
herdr            # start (or reattach to) the Herdr TUI
# ... open/switch to an OpenCode pane and work as usual ...
# detach: ctrl+b q   (agents keep running)
herdr            # reattach later — same panes, same sessions
herdr server stop   # stop the server; a later `herdr` restores the layout and
                    # OpenCode resumes its conversation (session snapshots ON by default)
```

**Integration file lifecycle (owned by Herdr — untracked):** `herdr integration install opencode`
wrote these files into `~/.config/opencode/` (integration version 13 at the time of writing):

| File | Role |
|:---|:---|
| `plugins/herdr-agent-state.js` | OpenCode plugin reporting lifecycle state (working/blocked/idle) + session IDs |
| `herdr-tui-session.js` | TUI session bridge (pane ↔ server reporting) |
| `herdr-opencode/tui.js` | V2 entrypoint shim (resolves the directory's TUI entrypoint; V1 uses the original file) |
| `tui.jsonc` | Plugin registration (`{"plugin": ["./herdr-tui-session.js"]}`) |

These files are **local and untracked** — this repository does not commit or edit them. Herdr owns
their lifecycle:

```bash
herdr integration install opencode   # install / re-install (idempotent)
herdr integration status             # show installed integrations + versions
herdr integration uninstall opencode # remove the integration files
herdr integration update             # update integrations after a Herdr upgrade
```

After (re-)installing the integration, restart OpenCode panes so they load the plugin.

**Upgrades:** Herdr is **pinned** — do not run `herdr update`. To upgrade, bump `HERDR_VERSION` (and
its `HERDR_BINARY_SHA256`) in `install.sh` and re-run it; then run `herdr integration update` if the
new release ships a newer integration.

**Security invariants (MADR-0005):**

- **Pane screen history stays OFF.** Pane output may contain tokens, secrets, or personal data —
  do not enable pane screen-history capture. Session snapshots and agent resume stay at their
  defaults (ON): they preserve session identity, not pane screen content.
- **Local only.** Herdr runs strictly on VIDAR over a local Unix socket (same trust model as tmux);
  no SSH remote attach is configured.
- Herdr's update/detection-manifest calls to herdr.dev carry version metadata only — no session
  content leaves the machine.

### 2.8 CI/CD Pipeline

SSOT: arc42 [Quality Gates & CI §1.2](architecture/arc42/03-cross-cutting-and-security.md) — per-PR gate composition, deep-validation split, and the 0-warnings/0-failures merge gate; harness details: [harness/README.md](../harness/README.md); workflow: [.github/workflows/ci.yml](../.github/workflows/ci.yml).

### 2.9 Troubleshooting

| Symptom | Likely Cause | Fix |
|:---|:---|:---|
| `opencode` fails to start | `OPENROUTER_HOME_API_KEY` empty | Populate `~/.config/opencode/.secrets-home.env`, then launch via `oc-home` |
| MCP tools not available | Docker not running (Coach servers) or binary missing (GitHub servers) | `systemctl --user start docker`; re-run `install.sh` to (re)install `~/.local/bin/github-mcp-server` |
| MCP Coach image pull fails | Network or GHCR auth issue | `docker pull ghcr.io/fpittelo/coach:dev` to test |
| Agents not loading | Broken symlink in `~/.config/opencode/agents` | Re-run `install.sh` |
| Skills not activating | Broken symlink in `~/.config/opencode/skills` | Re-run `install.sh` |
| Wrong model used | `opencode.jsonc` has wrong `model` field | Check `opencode.jsonc` line 3 |
| Secrets not loaded in a pane | `oc-home` / `oc-work` wrapper missing from `profiles.sh`, or secrets file absent | Re-run `install.sh` (provisions `profiles.sh` and `.secrets-home.env`) |
| `oc-home()` missing after a WORK install | WORK installer (work repo #177) rewrites `profiles.sh` wholesale | Re-run HOME `install.sh` to restore `oc-home()` (mirrored fix tracked in the work repo) |
| `herdr: command not found` | Herdr binary not installed | Re-run `install.sh` (installs the pinned binary to `~/.local/bin/herdr`) |
| OpenCode panes show no live state in the Herdr sidebar | Integration files missing or stale (e.g. after a Herdr upgrade) | `herdr integration install opencode`, then restart the OpenCode panes; verify with `herdr integration status` |
| OpenCode conversation lost after `herdr server stop` | Session snapshots disabled or Herdr stopped uncleanly | Keep session snapshots at defaults (ON); restart with `herdr` — the layout restores and OpenCode resumes via its session ID |
| GitHub MCP issue-label writes silently no-op in subagent sessions | `GITHUB_issue_write` intermittently drops the `labels` array param during serialization (server executes the zero-field payload it receives) | Re-apply labels from the main session (`GITHUB_issue_write`, labels-only update), then fresh-read verify — proven Sprint 24 pattern (#370/#372/#373/#376/#389) |

### 2.10 GitHub PAT Permissions Checklist

Minimum scopes for squad PATs (fine-grained; classic-PAT equivalent in parentheses). A missing scope causes #40-class multi-hour delivery blocks — check this list **first** when GitHub MCP tools or pushes suddenly fail with 403:

- [ ] **Metadata: Read** (auto-selected) — mandatory baseline
- [ ] **Contents: Read and write** (`repo`) — push branches/tags, open PRs
- [ ] **Issues: Read and write** (`repo`) — board hygiene, issue comments
- [ ] **Pull requests: Read and write** (`repo`) — reviews, approvals, merges
- [ ] **Actions: Read** (`repo`) — CI status; **Read and write** only for tokens that dispatch/re-run workflows
- [ ] **Workflows: Read and write** (`workflow`) — required to push changes touching `.github/workflows/**`
- [ ] **Packages: Read** (`read:packages`) — pull `ghcr.io/fpittelo/*` images; **Read and write** (`write:packages`) only for tokens that publish images

**After a token rotation, verify in this order:**

1. `gh auth status` (or MCP `get_me`) — token valid.
2. `docker pull ghcr.io/fpittelo/coach:dev` — Packages OK.
3. Push a trivial branch and open a draft PR — Contents/Workflows/PRs OK.
4. Comment on any issue — Issues OK.
5. Trigger a `workflow_dispatch` run (Actions tab) — Actions OK.

---

## 3. User Guide

This section is for anyone who uses OpenCode day-to-day. No deep technical knowledge required.

### 3.1 Starting a Session

SSOT: [README — Per-pane profile selection](../README.md) — launch `oc-home` from your project directory; the wrapper sources the profile-scoped secrets and starts OpenCode with the HOME config.

### 3.2 Agents

SSOT: the agent specs ([agents/](../agents/)) — role mandates, model assignments, permission boundaries; invariants summarized in arc42 [Building Block View §5.2](architecture/arc42/01-context-and-building-blocks.md).

### 3.3 Skills

SSOT: each skill's frontmatter ([skills/](../skills/)); the tracked 15-skill inventory is listed in [README](../README.md).

**External skills channel (`~/.agents/skills/`):** Some skills are installed outside this repo via the Vercel `skills` CLI into `~/.agents/skills/` — that channel is **not** covered by this repository's CI-validated surface. Wrapper skills may declare cross-skill dependencies as prose (e.g. "Call the Skill tool with X") that `skills add` does **not** auto-install. After any external skill install, verify with `npx skills list` and a smoke invocation in a fresh session. Precedents: #101 (`grill-me` was non-functional until its `grilling` dependency was installed manually) and #77 (external-skills governance).

### 3.4 MCP Tools

SSOT: arc42 [Context & Building Blocks §5](architecture/arc42/01-context-and-building-blocks.md) and [opencode.jsonc](../opencode.jsonc) — same server registry and availability invariants as §2.6.

### 3.5 Models

SSOT: [opencode.jsonc](../opencode.jsonc) — OpenRouter-only provider scoping and the configured model catalog.

### 3.6 Daily Workflow

SSOT: arc42 [Runtime & Delivery §1.1](architecture/arc42/02-runtime-and-delivery.md) (autonomous issue-by-issue delivery loop) and the `home-governance` skill §6 ([SKILL.md](../skills/home-governance/SKILL.md)).

### 3.7 Dos and Donts

SSOT: the `home-governance` skill §5 ([SKILL.md](../skills/home-governance/SKILL.md)) — feature-branch isolation, issue-referenced PRs, clean-CI merge gate, secrets hygiene.

### 3.8 Permission Posture & Safety Guardrails

SSOT: arc42 [Security & Privacy §1.1](architecture/arc42/03-cross-cutting-and-security.md) and [MADR-0004](adr/0004-allow-by-default-bash-permission-posture.md) — allow-by-default with catastrophic-deny guardrails, last-match-wins evaluation, per-segment compound-command checks, file-centric secret denies (#167).

---

## 4. Switching Between HOME and WORK Profiles

SSOT for profile-switching mechanics (per-pane wrappers, secrets sourcing, base-layer merge, simultaneous HOME/WORK panes): [README — Per-pane profile selection](../README.md).

### 4.1 How Profile Selection Works

Wrapper semantics and the HOME/WORK comparison: see [README](../README.md) — 'Per-pane profile selection'.

### 4.2 Switch to HOME Profile

Launch `oc-home` from your project directory; re-provision with the HOME `install.sh` — see [README](../README.md).

### 4.3 Switch to WORK Profile

Launch `oc-work` from your EPFL project directory; re-provision with the WORK `install.sh` (mirrored mechanism, work repo #177) — see [README](../README.md).

### 4.4 Verify Active Profile

Verification: `herdr agent list` recognizes each OpenCode instance; the base-layer symlink is inspected with `ls -la ~/.config/opencode/opencode.jsonc` — see [README](../README.md).

### 4.5 Project-Level Overrides (Deep-Merge Shielding)

OpenCode supports **project-level configuration overrides**. A project directory can contain its own `.opencode/opencode.jsonc` that is deep-merged with the global config.

**How it works in WORK mode:**

The WORK `opencode.jsonc` sets the `GITHUB` and `COACH *` MCP servers to `"enabled": false`:

```jsonc
"mcp": {
    "GITHUB": { ..., "enabled": false },
    "COACH_DEV": { ..., "enabled": false },
    ...
}
```

This means even if a project under `~/projects/WORK/` somehow had access to the HOME config, the WORK config would suppress personal MCP tools in EPFL project directories. This **deep-merge shielding** prevents personal tools from leaking into the EPFL workspace.

**Practical effect:**
- In `~/projects/HOME/` → HOME profile active → GITHUB + COACH MCPs work
- In `~/projects/WORK/` → WORK profile active → GITHUB + COACH MCPs suppressed
- A project-level `.opencode/opencode.jsonc` under `~/projects/WORK/my-epfl-project/` can further override settings per-project

### 4.6 Warnings

| Warning | Why |
|:---|:---|
| ⚠️ **Do NOT mix profiles** | Launch each context in its own pane via its wrapper (`oc-home` / `oc-work`); never run EPFL work from a HOME pane or personal work from a WORK pane. |
| ⚠️ **Profile is fixed at pane launch** | OpenCode loads the config at session start; a pane's profile is fixed by the wrapper that launched it. To change profile, close the pane and relaunch with the other wrapper. |
| ⚠️ **Secrets are per-pane, but residuals remain** | Each profile sources its own secrets file (`.secrets-home.env` / `.secrets-work.env`, mode 600) inside the wrapper subshell — no global rc sourcing, no systemd import. The cross-profile residual risks are accepted (STRIDE review #253 / MADR-0010). |
| ⚠️ **Don't edit the symlink directly** | The global base-layer symlink is managed by `install.sh` only. Manually editing it can break the path. |

**Cross-profile residual risks (RR1–RR9):** single SSOT in [README — Residual risks](../README.md) (STRIDE review #253 / MADR-0010, accepted).

---

## Further Reading

| Resource | Location | Description |
|:---|:---|:---|
| Migration Plan v3.1 (historical) | `docs/history/opencode-config-migration-plan-v3.1.md` | Full migration plan from Google Drive to Git-tracked repos (historical record) |
| README | `README.md` | Quick-start and repository structure |
| WORK Guide | GitLab `isgov/ea/opencode-work-config` → `docs/Admin-and-User-Guide.md` | Admin and User Guide for the WORK (EPFL) profile |

---

**Architecture:** Golden Architecture v3.1  
**Author:** `@architect` (HOME SCRUM Squad)  
**Repository:** `fpittelo/opencode-home-config` (GitHub)  
**License:** Personal — Frederic Pitteloud (@fpittelo)
