---
name: herdr
description: "Control Herdr, a terminal multiplexer for coding agents. Use only when the user explicitly mentions Herdr or asks to use Herdr to inspect or control panes, tabs, workspaces, commands, or another agent. Do not use merely because a task could benefit from a background terminal, delegation, or parallel work. Requires HERDR_ENV=1."
---

# Herdr

Herdr organizes terminals into workspaces, tabs, and panes, recognizes coding agents running
inside panes, and exposes the current session through the `herdr` CLI. On HOME it hosts the
OpenCode TUI panes (MADR-0005; the Admin Guide §2.7 covers user-facing runtime admin).

## Scope gate

Before issuing any control command, verify that this agent is running inside a Herdr-managed pane:

```bash
test "${HERDR_ENV:-}" = 1
```

If the check fails, say that you are not running inside Herdr and stop. Do not inspect or control
a Herdr session from outside Herdr.

## Read first

The installed binary is the authority for command syntax — start with `herdr --help`. Never run
bare `herdr` for discovery: it launches or attaches the TUI. Most control commands return JSON;
read identifiers and state from those responses instead of predicting them.

Public IDs are opaque stable handles — workspace `w1`, tab `w1:t1`, pane `w1:p1`. Prefer
`--current` when a command should target the calling pane.

Discover live state (metadata only):

```bash
herdr workspace list
herdr tab list --workspace "$HERDR_WORKSPACE_ID"
herdr pane current --current
herdr pane list --workspace "$HERDR_WORKSPACE_ID"
herdr agent list
herdr agent get <agent-name>
```

`agent get` reports the lifecycle state: `idle`/`done` mean ready for input; `blocked` means an
approval or question UI is up — ask the user before answering it; `unknown` means an agent is
present but unclassified.

## Common operations

**Detach / reattach:** the user detaches the TUI with `ctrl+b q` — panes keep running — and
reattaches later with `herdr`. Sessions survive Herdr server restarts. Never run bare `herdr` from
inside a pane (it would attach a TUI there).

**Run a command in a sibling pane** (when the user asks for it):

```bash
herdr pane split --current --direction right --cwd "$PWD" --no-focus
herdr pane run <returned-pane-id> "<command>"
```

Read the new pane ID from `.result.pane.pane_id`. Split a wide pane right and a narrow or tall
pane down; `--no-focus` keeps the user's focus in the calling pane.

**Start and prompt another agent** (only on explicit user instruction):

```bash
herdr agent start <name> --kind <kind> --pane <returned-pane-id>
herdr agent prompt <name> "<task>" --wait --timeout 120000
```

`agent start` requires an existing available shell pane at its interactive prompt; it never
creates, splits, or moves layout. A successful start returns only once the agent is ready for
input; `--wait` waits for the first settled `idle`, `done`, or `blocked` state.

## Safety rails

- **Read-first:** inspect state with the `list`/`get` commands before acting; parse IDs from JSON
  responses, never from sidebar order or examples.
- **Never send commands or prompts to another agent's pane without an explicit user instruction** —
  this includes `agent prompt`, `agent send-keys`, and `pane run` targeting a pane that hosts
  another agent.
- **Pane screen history is OFF (MADR-0005 invariant).** Pane output may contain tokens, secrets,
  or personal data. Never enable screen-history capture and never scrape pane content — `pane read`
  / `agent read` are not part of this skill. If you need another agent's result, ask the user, or
  ask that agent to write it to a file and share the path.
- Do not close workspaces, tabs, panes, or sessions you did not create unless the user explicitly
  asked.
- Never run `herdr server stop` from an active session unless the user explicitly intends to stop
  the server and its pane processes; never kill the main Herdr process.
- SSH remote attach (`herdr machine`) is out of scope on HOME — Herdr runs strictly local
  (MADR-0005).
- CLI server errors are JSON on stderr with exit status 1; syntax errors exit with status 2.