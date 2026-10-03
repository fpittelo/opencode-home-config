# MADR-0005: Adopt Herdr agent runtime for OpenCode on VIDAR (pinned, local-only)

- **Status:** accepted
- **Date:** 2026-10-03
- **Deciders:** @fpittelo, @architect

## Context

HOME SCRUM agents run as OpenCode TUI sessions on VIDAR. A TUI session lives and dies with its
terminal: closing the terminal window, detaching, or a laptop restart kills every running agent
conversation mid-task. Long autonomous deliveries (multi-issue sprint loops) are exactly the
workloads that suffer: an agent dispatched by @architect cannot survive the terminal it was
launched from, and there is no single place where @fpittelo can see which agents are working,
blocked, or idle across projects.

Herdr (github.com/herdrdev/herdr) is a terminal multiplexer purpose-built for coding agents: a
background server hosts panes as real PTYs, a client TUI detaches/reattaches (`ctrl+b q` / `herdr`),
an agent sidebar reports live lifecycle state (working/blocked/idle), and sessions resume after a
server restart. Its OpenCode integration (installed via `herdr integration install opencode`) wires
OpenCode session state and session IDs into the Herdr server over a local Unix socket.

The Product Owner groomed the integration scope with @architect (issue #148, design decisions 1–5):
pinned binary install, default-on and idempotent, integration files untracked, local-only, manual
server start. A grooming correction by @architect renumbered this record from the originally
announced "MADR-0004" to **MADR-0005** — 0004 is taken by the allow-by-default bash posture ADR
(merged in `a709ecf`); the MADR sequence must stay gap-free (0001–0005).

## Decision Drivers

- **Session survivability:** agent work must survive terminal detach (`ctrl+b q` → `herdr`) and
  Herdr server restarts (layout restore + OpenCode conversation resume via `opencode --session <id>`).
- **Live state visibility:** one sidebar showing working/blocked/idle for every OpenCode agent.
- **Supply-chain posture (consistent with MADR-0002's pinned native transport):** version-pinned
  binary, SHA256-verified, no curl-to-shell of upstream installers; upgrades are deliberate pin bumps.
- **Config-repo hygiene:** Herdr owns the lifecycle of the integration files it writes into
  `~/.config/opencode/` — this repo must not track or overwrite them.
- **Swiss nLPD / secrets:** pane output may contain tokens and secrets; nothing agent-related may
  leave the machine; no new secret stores.
- **KIS/YAGNI (MADR-0003):** no systemd unit, no SSH remote attach, no tracked `config.toml` —
  defaults and manual start are proportionate for a single-user workstation.

## Considered Options

### Option 1: Status quo — plain OpenCode TUI sessions (no agent runtime)

- Pros: zero new moving parts; current behavior unchanged.
- Cons: agents die with the terminal; no detach/reattach; no cross-project live state; long
  autonomous deliveries remain hostage to one terminal window. Rejected by the Product Owner.

### Option 2: Adopt Herdr — pinned binary, default-on idempotent install, local-only (chosen)

- Pros: detach/reattach, server-restart resume, live agent state sidebar; OpenCode integration is
  first-party (integration ≥ version 5 supports V1 and V2); supply-chain posture identical to the
  github-mcp-server block of `install.sh`; integration files stay Herdr-owned and untracked.
- Cons: one more pinned binary to maintain (deliberate pin bumps); integration files in
  `~/.config/opencode/` are outside this repo's CI-validated surface (documented in the Admin Guide).

### Option 3: Adopt Herdr with systemd autostart + SSH remote attach + tracked integration files

- Pros: server always running; remote machines attachable; integration files version-controlled.
- Cons: systemd unit and SSH remote are out of scope per grooming (candidate follow-ups); tracking
  Herdr-owned files creates merge conflicts with `herdr integration update` and double ownership —
  explicitly rejected (design decision 3).

## Decision Outcome

Chosen option: **Option 2**, implemented in `install.sh` (step 3) and documented in the Admin Guide:

1. **Pinned binary:** `install.sh` downloads `herdr-linux-x86_64` v0.9.3 from the official release
   (`github.com/herdrdev/herdr/releases`, tag `v0.9.3`) and SHA256-verifies it against the pinned
   digest `18a8dc65f1c2fa485884344356dea1cfd911c6f06cf46fa78e193f4087f4dba7` before installing to
   `~/.local/bin/herdr` (mode 0755). Upstream publishes no checksums file; the pin source is the
   asset digest published by the GitHub release API for the tag. No curl-to-shell of upstream
   installers. Upgrades = deliberate `HERDR_VERSION` bump (same policy as `GITHUB_MCP_VERSION`).
2. **Default-on, idempotent:** every `install.sh` run installs or verifies Herdr; re-runs skip when
   the pinned version is already installed (trusted on `--version` alone, with a token-boundary
   match so a future `0.9.31` cannot substring-match a `0.9.3` pin) and never clobber.
3. **Integration files untracked:** `herdr integration install opencode` writes
   `plugins/herdr-agent-state.js`, `herdr-tui-session.js`, `herdr-opencode/tui.js` and the plugin
   registration in `tui.jsonc` under `~/.config/opencode/`. These stay **local and untracked** —
   Herdr owns their lifecycle (`herdr integration install/uninstall/update`); this repo documents
   them but never commits or edits them.
4. **Local-only:** no SSH remote attach, no `config.toml` managed by this repo. Pane screen history
   stays **OFF** (invariant — see Security Considerations). Session snapshots and agent resume stay
   at defaults (ON).
5. **Manual server start:** Herdr's default auto-spawn behavior; no systemd unit.

ArchiMate: Technology Layer — Node (VIDAR) *hosts* System Software (Herdr server); Herdr *hosts*
OpenCode TUI panes (Application Components); the integration plugins (Application Interface) *serve*
OpenCode lifecycle reporting. Indexed in arc42 §3 (technical context), §5 (building blocks) and §9.

## Consequences

- **Positive:** OpenCode agent sessions survive terminal detach and Herdr server restarts; live
  working/blocked/idle state for all agents in one sidebar; supply-chain posture identical to the
  established github-mcp-server pattern; zero new tracked config surface; integration lifecycle
  stays with the tool that owns it.
- **Negative:** one more pinned binary to bump deliberately on upgrades; the integration files under
  `~/.config/opencode/` are outside this repo's CI-validated surface (compensating: documented
  lifecycle in the Admin Guide; Herdr regenerates them on `integration install/update`); a Herdr
  upgrade that changes integration behavior requires re-running `herdr integration install opencode`.
- **Mitigations:** the Admin Guide documents the integration file list, the install/uninstall/update
  commands, and a troubleshooting entry; `install.sh` re-runs are safe by construction (skip path);
  the pane-history-off invariant is documented as a security boundary, not a preference.

## Security Considerations

- **Local Unix-socket trust model (same as tmux):** the Herdr server and its clients communicate
  over `~/.config/herdr/herdr.sock` (and the OpenCode integration plugins over the same socket).
  Anything that can reach the user's socket can drive the panes — identical to the tmux control
  socket trust model on a single-user workstation. No network listener is involved for local use.
- **Pane screen history stays OFF (invariant):** pane output may contain tokens, secrets, or
  personal data (agent transcripts routinely quote environment values). Screen-history capture must
  not be enabled; session snapshots and agent resume remain at their defaults (ON) — they preserve
  session identity, not pane screen content.
- **SSH-only remote NOT enabled:** remote machine attach (`herdr machine`) is out of scope and not
  configured; Herdr runs strictly local on VIDAR. Any future remote enablement is a separate ADR.
- **Update-manifest network calls:** Herdr contacts herdr.dev for update/detection manifests; these
  calls carry no session content, pane output, or agent data — only version/metadata exchange.
  The pinned install means `install.sh` itself never calls herdr.dev.
- **Supply chain:** binary pinned + SHA256-verified against the GitHub release API asset digest;
  platform-guarded (Linux x86_64); fail-hard on mismatch; no upstream installer scripts executed.