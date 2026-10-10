# MADR-0010: Per-pane dual-profile coexistence and secrets isolation

- **Status:** accepted
- **Date:** 2026-10-10
- **Deciders:** @fpittelo (PO approval 2026-10-10, incl. explicit risk-acceptance below), @architect, @cyber-security (STRIDE threat model #253 — verdict APPROVE-WITH-CONDITIONS, controls MC1–MC10)
- **Driven by:** issue #244 · Prerequisite: #253 (STRIDE threat model) · Mirrored WORK ticket: fpittelo/opencode-work-config#177

## Context

Both profile installers (HOME and WORK) historically symlinked into the same
global directory `~/.config/opencode/` (`opencode.jsonc`, `agents`, `skills`)
and both managed `~/.config/opencode/.secrets.env` — last install wins. Any
OpenCode instance started after a profile flip silently picked up the flipped
profile (config is loaded once at startup, never hot-reloaded), producing a
non-deterministic mixed state. `.secrets.env` was sourced globally in
`.bashrc`/`.profile` and imported into the systemd user environment, so WORK
GitLab PATs and EPFL keys were exported into every shell — including HOME
panes — and vice versa (cross-context secret exposure). A legacy switcher
(`opencode-switch-context()` / `opencode-status()` referencing
`/AI_OS_ROOT/CONFIGS/OPENCODE`) remained in `.bashrc` as a stale second
mechanism able to silently re-flip symlinks.

The WORK profile already shipped per-pane selection (`oc-work`, issue #177 in
the work repo). The HOME profile must coexist with it: both profiles running
simultaneously in separate Herdr panes, each loading its own config, agents,
and skills, with secrets confined to the pane that needs them.

## Decision Drivers

- **Parallel contexts:** HOME and WORK instances must run at the same time
  (one Herdr pane each) without overwriting each other's configuration.
- **Secrets isolation (MC1/MC2/MC9):** HOME secrets must never persist in the
  interactive pane shell after `opencode` exits, and must never be exported
  into shells that do not need them (no global rc sourcing, no systemd import).
- **Convergence (MC3/F9):** both installers must be idempotent and convergent;
  the HOME installer must never clobber `oc-work()` in the shared
  `profiles.sh`.
- **Determinism:** a pane's profile must be fixed at launch time, not by the
  last installer run.
- **KIS/YAGNI:** no Herdr changes, no data-dir split, no new components —
  configuration-layer change only.

## Considered Options

1. **Global symlink flipping (status quo):** `install.sh` re-points
   `~/.config/opencode/*` at the desired profile. Rejected: last-install-wins,
   non-deterministic mixed state for instances started after a flip, and the
   legacy switcher made it worse (silent re-flips).
2. **Per-pane env-based profile selection (chosen):** a sourced
   `profiles.sh` snippet defines per-pane wrappers (`oc-home`, `oc-work`) that
   source their profile-scoped secrets file inside a subshell (`set -a` /
   `set +a`), prefix-assign `OPENCODE_CONFIG` / `OPENCODE_CONFIG_DIR` to the
   profile repo, and end in `exec opencode "$@"`. The global symlink stays the
   base layer for bare `opencode`.
3. **Strict global-config isolation:** point the global symlink at a minimal
   stub so bare `opencode` loads nothing profile-specific. Rejected (YAGNI):
   adds a second config artifact to maintain; the merge caveat is documented
   instead (MC8).

## Decision Outcome

Option 2 — per-pane env-based profile selection, mirroring the WORK profile
(#177). `install.sh` provisions `~/.config/opencode/profiles.sh` with
`oc-home()` (subshell + `set -a`/`set +a` + `exec opencode "$@"`, appended
without clobbering `oc-work()`), migrates the shared `.secrets.env` into
`.secrets-home.env` (mode 600, umask 077) and removes it, retires the
`.secrets.env` sourcing from `.bashrc`/`.profile` and the systemd
`import-environment` call (unset + `show-environment` verification instead),
removes the legacy `/AI_OS_ROOT` switcher, and hardens `~/.config/opencode`
to mode 700 with a fail-closed permission assertion on `.secrets-*.env`
files. Bare `opencode` remains the global-symlink default but is unsupported
for secret-bearing work (MC8).

**Explicit PO risk-acceptance (MC5, @fpittelo 2026-10-10):** the provider
OAuth token store `~/.local/share/opencode/auth.json` (and `mcp-auth.json`)
remains **shared** between the HOME and WORK profiles — provider logins are
global and switching profiles does not switch identities. Splitting the data
directory is out of scope (YAGNI); the residual is documented in arc42 §11
and accepted by the Product Owner.

## Consequences

- HOME and WORK instances coexist deterministically: one Herdr pane per
  context, launched via `oc-home` / `oc-work`; `herdr agent list` tracks each
  instance independently.
- Secrets are confined to the wrapper's execution subshell; nothing persists
  in the pane shell, and the systemd user environment is verified secret-free
  post-install.
- Config-merge caveat: the global symlink config remains the base layer and
  env-var configs merge over it, so non-conflicting keys from the global
  layer stay visible in every pane (documented in README; MC8).
- Same-UID `/proc/<pid>/environ` exposure of a running pane's environment
  remains possible (RR1) — documented in arc42 §11 (MC7), accepted.
- Convergence asymmetry residual: the WORK installer (#177) still writes
  `profiles.sh` with a full-file heredoc; running it after the HOME installer
  removes `oc-home()` until the mirrored fix lands in the work repo
  (re-run HOME `install.sh` to restore). Tracked for the work-repo ticket.
