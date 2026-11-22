#!/usr/bin/env python3
"""Enforce the bash tier invariants after root inheritance (#340).

Design shift (#340): the MADR-0004 five-file mirroring of the bash tiers is
SUPERSEDED by root inheritance. Verified opencode semantics (empirical probe
via ``opencode debug agent``, opencode 1.19.0):

  * An agent spec that OMITS the ``bash:`` key receives every config-level
    bash rule of ``opencode.jsonc`` (probe: agent with no ``bash:`` key
    resolved to exactly the root rule list, zero agent rules).
  * An agent that declares a (partial) ``bash:`` map has its rules APPENDED
    AFTER all config-level rules in the last-match-wins list (probe: an
    agent allow for a root-denied marker pattern overrode the config deny).

Consequences enforced below:

  1. ROOT BASELINE INTEGRITY — the root ``permission.bash`` block of
     opencode.jsonc equals BASELINE_ROOT_RULES exactly (order-sensitive pin
     of the MADR-0015 delta: ``"*"`` allow head + ask tier + frozen deny
     tail). The root block is the single source of truth; any edit must be
     a deliberate, reviewed change to this constant.
  2. CLEAN AGENT INHERITANCE — each of the four allow-default agent specs
     (agents/architect.md, agents/developer.md, agents/devops.md,
     agents/cyber-security.md) either omits ``bash:`` entirely or carries
     ONLY its documented role-deviation patterns (devops: the MADR-0022 gh
     CI-triage carve-out; cyber-security: audit-tool allows). Re-stating any
     root tier pattern in an agent is now the DEFECT (it appends after the
     root deny tail and can widen the posture), not the requirement. The
     MADR-0004 ``docker *`` row was a DEAD REGISTRY ROW — no such rule ever
     existed in agents/devops.md — and was deleted by MADR-0024 (#419, C4);
     that reconciliation is POSTURE-NEUTRAL, not a tightening (the root
     ``"*"`` allow head covers both runtimes).
  3. LAST-MATCH-WINS TRUTH TABLE — a static resolver evaluates command
     strings against the ordered root rule list (fnmatch-style glob,
     last match wins, opencode semantics) and every expected verdict of
     the MADR-0015 delta must hold. A failing verdict against the real
     config is a REAL ordering defect: fix the config, not the table.
     COMPOUND COMMANDS (#419) — the documented evaluation (MADR-0004
     §"ordering is normative", arc42 §1.1) splits a command line on
     ``&&``/``;``/``|`` and judges every segment, so ONE denied segment
     blocks the whole line; COMPOUND_TRUTH_TABLE pins that for the
     MADR-0024 podman denies, whose whole-line globs would otherwise be
     bypassable by appending an allowed segment
     (``podman pull x && podman machine init``).
  4. NON-INHERITANCE AGENT SHAPES (#350) — scrum-master, code-reviewer
     and coach declare an explicit bash posture instead of inheriting;
     each shape is pinned order-sensitively (NON_INHERITANCE_AGENTS).
     scrum-master's three trailing secret-file denies (``*.env*`` /
     ``*.pem*`` / ``*.key*``) must sit AFTER its gh/git allows: agent
     rules append after the root deny tail, so without them an allow
     like ``gh pr *`` re-enables credential-file commands (e.g.
     ``gh pr edit 1 --body-file foo.env``). Every agent spec — including
     the four allow-default ones — is parsed STRUCTURALLY as YAML (PyYAML,
     duplicate keys rejected; #350, C3 fix-up of PR #492), so the block
     mapping, the flow mapping (``bash: {"*": deny}``), the scalar
     (``bash: deny``) and every key spelling (double-quoted, single-quoted,
     unquoted) are seen — the former double-quote-only regexes silently
     skipped an unquoted ``kill*: allow`` and hid it from every check.

  5. WRAPPER-FAMILY DENY (MADR-0029, #475 resolves #468) — the curated
      bash wrapper/executor family (``xargs``, ``env``, ``timeout``,
      ``nohup``, ``setsid``, ``stdbuf``, ``nice``, ``watch``, ``command``,
      ``exec``, ``time``, ``eval``, ``find … -exec…``) is denied at the
      root tail: the engine resolves each subcommand as raw text with
      last-match-wins, so a wrapper prefix used to catch the ``"*": allow``
      head before any ask/deny pattern could match (live-verified on
      opencode v2.3.2). A canary rejects any agent allow/ask rule whose
      executable head is a denied wrapper, and the gate-20 ordered-
      resolution probes are shared from here. Bare-prefix patterns are
      path-insensitive by construction: path-qualified spellings are the
      recorded residual (AC2/C2).

  6. KILL-FAMILY POSTURE (MADR-0032, #485) — the kill deny block is
      TARGET-classified and path-general: ``*/kill *`` closes the R-1
      path-qualified DIRECT kill that used to resolve allow under the
      bare-prefix ask line (``/usr/bin/kill 754``), and the target-``0`` /
      target-``-1`` / negative-process-group forms replace the MADR-0027
      signal-prefix patterns that hard-denied ``kill -15 <pid>`` /
      ``kill <pid> -15`` (R-2). A canary rejects any agent allow/ask rule
      whose executable head is ``kill`` (no carve-out of any kind), the
      gate-20 ordered-resolution probes are shared from here, and the
      residual set (path-qualified wrapper-to-kill, assignment prefixes,
      non-enumerated executors, the unpinned engine) stays recorded —
      the kill checkpoint is NARROWED, never widened.

Usage: check_bash_permission_tiers.py [REPO_ROOT]
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

import yaml

from jsonc_utils import strip_jsonc

# The four allow-default agent specs that used to mirror the tiers verbatim
# (MADR-0004) and now inherit the root baseline (#340).
AGENT_FILES = ("architect.md", "developer.md", "devops.md", "cyber-security.md")

# MADR-0029 (#475, resolves #468 — C1): the curated bash wrapper/executor
# family denied at the ROOT tail. The engine's shell scanner resolves each
# subcommand's own raw text and the rule list is last-match-wins, so a wrapper
# prefix (`xargs curl …`, `timeout 5 printenv …`) used to catch the
# `"*": allow` head BEFORE any ask/deny pattern could match — live-verified on
# opencode v2.3.2 (#468). The upstream maintainers designate wrapper-scoped
# denies as the sanctioned workaround (anomalyco/opencode#54008 closed
# not-planned; #58775 open/reproduced; #62513 closed as duplicate), and the
# engine is unpinned (no CI vehicle for a runtime fix), so the mitigation is
# config-side. Patterns are BARE-PREFIX on purpose (C2): bare-prefix globs are
# path-insensitive, which is reviewed and accepted (false positives such as a
# `nice -n 5 …` invocation block in the safe direction); path-qualified
# wrapper AND direct-command spellings (`/usr/bin/xargs …`, `/usr/bin/curl …`,
# `/bin/sh -c …`) remain the recorded residual (arc42 §3, MADR-0029).
# Alphabetical; the block is appended LAST in the tail (deny rules go last).
WRAPPER_DENY_PATTERNS: tuple[str, ...] = (
    "command *",
    "env *",
    "eval *",
    "exec *",
    "find * -exec*",
    "nice *",
    "nohup *",
    "setsid *",
    "stdbuf *",
    "time *",
    "timeout *",
    "watch *",
    "xargs *",
)

# Executable heads that must never appear in an agent ALLOW/ASK rule (C4
# canary). `find` is deliberately absent: only its `-exec*` form is denied,
# the read-only `find` surface stays allowed. Match is exact-or-head-token,
# after stripping any leading path (`/usr/bin/xargs *` -> `xargs`).
WRAPPER_DENY_HEADS: frozenset[str] = frozenset(
    {
        "command",
        "env",
        "eval",
        "exec",
        "nice",
        "nohup",
        "setsid",
        "stdbuf",
        "time",
        "timeout",
        "watch",
        "xargs",
    }
)

# MADR-0029 C3 (#475): representative wrapper commands that gate 20 must
# resolve to DENY against the ORDERED installed rule list — deny-set
# membership alone is not proof (last-match-wins makes order semantic).
# Shared from here so the checker and the installed-posture gate cannot drift.
WRAPPER_ORDERED_PROBES: tuple[str, ...] = (
    "xargs pip install pkg",
    "timeout 5 curl",
    "env gh api",
    "true && xargs curl",
)

# MADR-0032 (#485): the target-classified kill deny block. MADR-0027 shipped
# three SIGNAL-prefix patterns (`kill 0*`, `kill -1*`, `kill * -1*`); the
# #482 AC7 audit found two defects and this block replaces them:
#
#   * R-1 (medium) — the `kill*` ask checkpoint was PATH-BYPASSABLE:
#     `/usr/bin/kill 754` and `/bin/kill -9 1234` resolved ALLOW under the
#     bare-prefix ask line. `*/kill *` is path-general (whole-value wildcard;
#     `*` includes `/`), so the direct path-qualified spelling now denies
#     while bare `kill <pid>` still resolves ask via the ask tier.
#   * R-2 (low) — signal-prefix classification over-matched: `kill -1*`
#     matched `kill -15 <pid>` and `kill * -1*` matched `kill <pid> -15`, so
#     SIGTERM-by-number was hard-DENIED while plain `kill <pid>` only asked.
#     The block is now TARGET-classified: target `0` (own process group),
#     target `-1` (every process of the user) and negative process-group
#     targets stay denied; single-PID signal forms stay ask.
#
# `kill -* -*` is the negative-process-group classifier: a target below the
# signal range can only be spelled with an explicit signal option
# (`kill -TERM -12345`) or the `--` separator (`kill -- -12345`), both of
# which carry a second hyphen token, whereas the must-ask single-PID forms
# (`kill -15 <pid>`, `kill <pid> -15`, `kill -s TERM <pid>`,
# `kill --signal 1 <pid>`, `kill -0 <pid>`) carry exactly one. Recorded
# limitations (deny-only narrowing, never a capability increase):
# (a) a negative numeric target written as the ONLY hyphen token
#     (`kill 1234 -12345`) is textually indistinguishable from a signal
#     number without regex/quantifier support — it resolves ASK (the
#     checkpoint), never ALLOW;
# (b) path-qualified wrapper-to-kill (`/usr/bin/env kill 754`) and env-var
#     assignment prefixes (`VAR=1 kill 754`) stay in the MADR-0029 residual
#     set (arc42 §3) — R-1 is closed for the DIRECT path-qualified form only.
# Deny-only, so the residual false positives fall in the safe direction.
KILL_DENY_PATTERNS: tuple[str, ...] = (
    # target 0 (own process group)
    "kill 0",
    "kill 0 *",
    "kill * 0",
    "kill * 0 *",
    # target -1 (every process of the user)
    "kill -1",
    "kill -1 *",
    "kill * -1",
    "kill * -1 *",
    # other negative process-group targets
    "kill -* -*",
    # R-1: path-qualified direct kill (path-general whole-value wildcard)
    "*/kill *",
)

# MADR-0032 C3 (#485): representative kill commands gate 20 must resolve to
# DENY against the ORDERED installed rule list — the R-1 bypass is invisible
# to deny-set membership, and last-match-wins makes order semantic.
KILL_ORDERED_PROBES: tuple[str, ...] = (
    "/usr/bin/kill 754",
    "/bin/kill -9 1234",
    "kill 0",
    "kill -TERM -12345",
)

# Deny-tail baseline captured from origin/dev HEAD before the #320 Slice B
# delta (MADR-0015): the ordered deny patterns that must never move.
BASELINE_DENY_TAIL: tuple[str, ...] = (
    "sudo*",
    "rm -rf /*",
    "rm -fr /*",
    "rm -rf /",
    "rm -rf ~*",
    "rm -rf $HOME*",
    "rm -rf ${HOME}*",
    "mkfs*",
    "dd *of=/dev/*",
    "shred*",
    "wipefs*",
    "blockdev*",
    "fdisk*",
    "sfdisk*",
    "gdisk*",
    "parted*",
    "truncate * /dev/*",
    "* > /dev/sd*",
    "* > /dev/nvme*",
    "* > /dev/mmcblk*",
    "* > /dev/vd*",
    "* > /dev/hd*",
    "mv * /dev/sd*",
    "mv * /dev/nvme*",
    "mv * /dev/mmcblk*",
    "shutdown*",
    "reboot*",
    "halt*",
    "poweroff*",
    "systemctl poweroff*",
    "systemctl reboot*",
    "systemctl halt*",
    "crontab*",
    "systemd-run*",
    "chmod -R * /*",
    "chown -R * /*",
    "find * -delete*",
    "find * -exec rm*",
    "git push --force*",
    "git push -f*",
    "git filter-branch*",
    "git filter-repo*",
    "git clean*",
    "git reset --hard*",
    "curl*",
    "wget*",
    "bash -c *",
    "sh *",
    "python* -c*",
    "node -e*",
    "node --eval*",
    "perl -e*",
    "ruby -e*",
    "printenv*",
    "env",
    "cat /proc/*/environ*",
    "*.env*",
    "*.pem*",
    "*.key*",
    # #352 (MADR-0020 no-delete parity, PO decision (a) 2026-10-17): tail
    # append — the retired MADR-0016 server intentionally had no delete
    # capability; release deletion is machine-denied for every agent.
    "gh release delete*",
    # MADR-0022 (#401, C4/C5): tail append — the GITHUB_ACTIONS MCP server is
    # retired and CI triage moves to the pinned gh CLI; the destructive /
    # bypass gh sub-commands are machine-denied at the root baseline.
    # `gh api *` is DECISIVE (MADR-0008 review C5, PR #402): a `gh run
    # delete` deny alone is bypassable via raw REST while `gh api -X DELETE`
    # is allowed.
    "gh run delete*",
    "gh cache delete*",
    "gh auth *",
    "gh api *",
    # MADR-0022 (#401, C6): the retired actions_run_trigger equivalent
    # (workflow dispatch / enable / disable, run cancel / rerun) is
    # @devops-only — root deny, with the agents/devops.md carve-out allow
    # appended after this tail (last-match-wins: only @devops regains it).
    "gh workflow *",
    "gh run cancel*",
    "gh run rerun*",
    # #362 (Sprint 23 spike, upstream anomalyco/opencode#56545): path-scoped
    # deny closing the recursive-read bypass against the secrets directory
    # (grep -r X ~/.config/opencode/ returned .secrets-home.env contents).
    "*/.config/opencode*",
    # MADR-0024 (#419, C1/C2): the local container runtime migrated to
    # rootless Podman (#417), so the runtime's own daemon-style escapes are
    # tail-appended here for every agent. `podman system service` re-creates
    # a Docker-API-compatible socket — the long-lived daemon pattern this
    # migration exists to remove; `podman machine` spawns a VM whose `ssh`
    # can yield guest root with a shared host home (irrelevant on WSL2, so
    # the deny costs nothing). Neither is escalation above uid 1000 under
    # rootless mode: both are persistence / API-surface controls. The
    # remainder of the family (`unshare`, `kube play`, `--connection`,
    # `generate`) stays allowed as a recorded accepted residual (MADR-0024
    # D3, arc42 §3).
    "podman system service*",
    "podman machine*",
    # MADR-0027 (#463, AC0 verdict C3) → MADR-0032 (#485): kill broadcast
    # forms are control-plane-DoS primitives — `kill 0` (own process group),
    # `kill -1` (every process of the user), `kill <pid> -1` (pid +
    # broadcast; empirically grounded by the pre-review probe). MADR-0032
    # REPLACES the three signal-prefix patterns with the target-classified
    # block above: the broadcast denies are preserved (plus negative
    # process-group targets), the R-2 signal-number false positives are
    # removed, and `*/kill *` closes the R-1 path-qualified direct form.
    # No kill allow is introduced: plain `kill <pid>` stays ask (C4(b)).
    *KILL_DENY_PATTERNS,
    # MADR-0029 (#475, resolves #468 — C1): tail append — the curated wrapper/
    # executor family. Additions only (tightening): a wrapper prefix can no
    # longer reach the `"*": allow` head before the ask tier / deny tail
    # (`xargs curl`, `xargs printenv`, `xargs rm -rf /` — all live-verified as
    # executing on v2.3.2); the dispositioned remainder of the executor
    # inventory (ionice, chrt, taskset, flock, unshare, nsenter, setpriv,
    # bwrap, script, unbuffer, parallel) is recorded in MADR-0029. The
    # path-qualified spellings and env-var assignment prefixes stay the
    # recorded residual (arc42 §3, C2).
    *WRAPPER_DENY_PATTERNS,
)

# Ask-tier baseline as ratified by the MADR-0015 delta (#320 Slice B),
# order-sensitive: single ask checkpoint per destructive-but-recoverable
# family, plus the three workspace-scoped allow carve-outs.
BASELINE_ASK_TIER: tuple[tuple[str, str], ...] = (
    ("rm *", "ask"),
    ("rm /tmp/opencode/*", "allow"),
    ("rm -r /tmp/opencode/*", "allow"),
    # MADR-0027 (#463, AC0 verdict C1): scoped cache-cleanup carve-outs,
    # ROOT ask-tier placement ONLY — an agent-level `rm -rf */.venv` allow
    # appends AFTER the deny tail and defeats it for the matching glob
    # (verified in the AC0 review). Enforced by check_rm_carveout_placement.
    ("rm -rf .venv", "allow"),
    ("rm -rf */.venv", "allow"),
    ("rm -rf __pycache__", "allow"),
    ("rm -rf */__pycache__", "allow"),
    ("rm -rf .pytest_cache", "allow"),
    ("rm -rf */.pytest_cache", "allow"),
    ("pip install*", "ask"),
    ("pip3 install*", "ask"),
    ("uv pip install*", "ask"),
    ("*-m pip install*", "ask"),
    ("npm install -g*", "ask"),
    ("npm i -g*", "ask"),
    ("kill*", "ask"),
    ("pkill*", "ask"),
    ("killall*", "ask"),
    ("chmod *", "ask"),
    ("chmod 600 *", "allow"),
    ("chmod 700 *", "allow"),
    ("chown *", "ask"),
    ("systemctl*", "ask"),
)

# The full pinned root bash block: allow head + ask tier + deny tail. The
# root block of opencode.jsonc must equal this list exactly (#340).
BASELINE_ROOT_RULES: tuple[tuple[str, str], ...] = (
    (("*", "allow"),)
    + BASELINE_ASK_TIER
    + tuple((pattern, "deny") for pattern in BASELINE_DENY_TAIL)
)

# Documented role-deviation patterns each agent MAY carry instead of the
# full inheritance (#340). Anything else — including any root tier pattern —
# is a defect. The MADR-0022 gh CI-triage surface (#401) is the exception to
# the "redundant legibility signature" rule: the root deny tail now denies
# the retired actions_run_trigger equivalent (`gh workflow *`, `gh run
# cancel*`, `gh run rerun*`), so the @devops carve-out allow is NOT redundant
# — it overrides the root deny for @devops only (last-match-wins: agent rules
# append after the tail). The @developer read-only allows (`gh run
# list/view/watch`) are redundant under the root "*" head but pinned as an
# explicit legibility signature so any extra gh allow fails the gate (C7).
# MADR-0024 (#419, C3): NO podman pattern is registered here, in either
# direction. A scoped *allow* set (`podman run*`, `pull*`, `ps*`, …) would
# tighten nothing — the root `"*": allow` head already permits every
# sub-command and a partial agent bash map appends AFTER the root deny tail —
# while tripping the #340 duplicate-root defect above. The tightening that WAS
# taken lives in the root tail instead (`podman system service*` /
# `podman machine*`, C1/C2); the rest of the family is an accepted residual
# (MADR-0024 D3, arc42 §3). No blanket `podman *` allow is introduced.
AGENT_DEVIATIONS: dict[str, frozenset[str]] = {
    "architect.md": frozenset(),
    # MADR-0022 (#401, C7): @developer read-only CI triage — explicit allow
    # legibility signature (root "*" already allows these; the pin makes any
    # additional gh allow for @developer a gate failure = drift).
    "developer.md": frozenset(
        {
            "gh run list*",
            "gh run view*",
            "gh run watch*",
        }
    ),
    # MADR-0022 (#401, C6): @devops-only write carve-out — the retired
    # actions_run_trigger equivalent (workflow dispatch/enable/disable, run
    # cancel/rerun). Root deny tail denies these for everyone; this allow
    # re-enables them for @devops only. The MADR-0004 `docker *` row was
    # deleted by MADR-0024 (#419, C4): agents/devops.md never carried the
    # rule, so it was a DEAD ROW in a permitted-but-not-required allowlist and
    # its removal is posture-neutral (the root "*" allow head covers both
    # runtimes) — not a tightening.
    "devops.md": frozenset(
        {
            "gh workflow *",
            "gh run cancel*",
            "gh run rerun*",
        }
    ),
    "cyber-security.md": frozenset(
        {
            "gitleaks*",
            "pip-audit*",
            "trivy*",
            "cargo audit *",
            "cargo deny *",
            "cargo metadata *",
            "cargo tree *",
            "sha256sum *",
            "opencode debug *",
            "opencode agent list*",
        }
    ),
}

# Non-inheritance agent specs (#350): these three declare an explicit bash
# posture instead of inheriting the root baseline. Their shapes are pinned
# ORDER-SENSITIVELY because agent rules append AFTER the root deny tail
# (last-match-wins): scrum-master's three trailing secret-file denies must
# stay AFTER its gh/git allows, or an allow like `gh pr *` would re-enable
# credential-file commands (e.g. `gh pr edit 1 --body-file foo.env`) — the
# append-override closed by #350. coach's scalar `bash: deny` normalizes to
# the single catch-all deny rule (flow/block equivalents accepted). Any edit
# is a deliberate, reviewed change to these constants.
NON_INHERITANCE_AGENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "scrum-master.md": (
        ("*", "deny"),
        ("gh issue *", "allow"),
        ("gh pr *", "allow"),
        ("git push origin --delete *", "allow"),
        ("*.env*", "deny"),
        ("*.pem*", "deny"),
        ("*.key*", "deny"),
    ),
    "code-reviewer.md": (
        ("*", "deny"),
        ("git status *", "allow"),
        ("git diff *", "allow"),
        ("git rev-parse *", "allow"),
        ("git cat-file *", "allow"),
        ("cat *", "allow"),
        ("grep *", "allow"),
        ("ls *", "allow"),
        ("*.env*", "deny"),
        ("*.pem*", "deny"),
        ("*.key*", "deny"),
        # 362: path-scoped deny closing the recursive-read bypass against
        # the secrets directory (upstream anomalyco/opencode#56545).
        ("*/.config/opencode*", "deny"),
    ),
    "coach.md": (("*", "deny"),),
}

# Last-match-wins truth table of the ratified delta (MADR-0015): every
# verdict must hold against the real ordered rule list.
TRUTH_TABLE: tuple[tuple[str, str], ...] = (
    ("rm /tmp/opencode/x", "allow"),
    ("rm -r /tmp/opencode/x", "allow"),
    ("rm -rf /tmp/opencode/x", "deny"),
    ("rm -rf /", "deny"),
    ("rm secrets-home.env", "deny"),
    ("rm x", "ask"),
    ("chmod 600 x", "allow"),
    ("chmod 700 x", "allow"),
    ("chmod 755 x", "ask"),
    ("chmod +x x", "ask"),
    ("chmod -R 777 /", "deny"),
    ("pip install pkg", "ask"),
    ("pip3 install pkg", "ask"),
    ("uv pip install pkg", "ask"),
    ("python -m pip install pkg", "ask"),
    ("env", "deny"),
    ("printenv HOST", "deny"),
    # #352 (MADR-0020 no-delete parity): release deletion is denied; create,
    # view and edit remain allowed (publishing stays governed by the PO
    # approval gate, home-governance Rule 5).
    ("gh release delete v1.0.0", "deny"),
    ("gh release create v1.0.0", "allow"),
    ("gh release view v1.0.0", "allow"),
    ("gh release edit", "allow"),
    # MADR-0022 (#401, C5 — minimum deny set): the retired GITHUB_ACTIONS
    # MCP surface is re-homed on the pinned gh CLI; destructive / bypass
    # sub-commands are machine-denied at the root deny tail. `gh api *` is
    # decisive — without it the gh run delete deny is bypassable via raw
    # REST (MADR-0008 review on PR #402). The write carve-out (gh workflow
    # run/enable/disable, gh run cancel/rerun — C6) and the @developer
    # read-only posture (gh run list/view/watch — C7) are enforced at the
    # agent level (AGENT_DEVIATIONS) and verified by the merged-resolution
    # tests in the test suite (GhCiTriageCarveOutTests).
    ("gh run delete 12345", "deny"),
    ("gh cache delete --all", "deny"),
    ("gh auth status", "deny"),
    ("gh api -X DELETE repos/fpittelo/opencode-home-config/issues/1", "deny"),
    ("gh workflow run ci.yml", "deny"),
    ("gh run cancel 12345", "deny"),
    ("gh run rerun --failed 12345", "deny"),
    # @developer read-only CI triage posture (C7): list/view/watch resolve
    # allow via the root "*" head; the root deny tail above covers every
    # write command, so the inherited posture is read-only without an
    # agent-level map.
    ("gh run list", "allow"),
    ("gh run view --log 12345", "allow"),
    ("gh run watch 12345", "allow"),
    ("gh run download 12345", "allow"),
    # 362: path-scoped deny closes the recursive-read bypass against the
    # secrets directory (upstream anomalyco/opencode#56545).
    ("grep -r X ~/.config/opencode/", "deny"),
    ("grep -r X ~/.config/opencode/sub/", "deny"),
    ("grep -r X secrets/", "allow"),
    # MADR-0024 (#419, C1/C2): the local container runtime migrated to
    # rootless Podman (#417). `podman system service` re-creates a
    # Docker-API-compatible socket (the long-lived daemon pattern the
    # migration exists to remove) and `podman machine` spawns a VM whose
    # `ssh` can yield guest root with a shared host home — both are
    # agent-issuable unprompted under the root head and are now denied for
    # every agent. Under rootless mode neither escalates above uid 1000:
    # these are persistence / API-surface controls, not privilege
    # boundaries.
    ("podman system service", "deny"),
    ("podman system service --time=0 unix:///run/user/1000/podman.sock", "deny"),
    ("podman machine init", "deny"),
    ("podman machine ssh", "deny"),
    ("podman machine ls", "deny"),
    # Scoping proof: the deny is sub-command-scoped, not a `podman system *`
    # blanket — only the API-socket escape was taken (C1); the remainder of
    # the family is the recorded residual (MADR-0024 D3, arc42 §3).
    ("podman system df", "allow"),
    # The migration must keep working (no over-tightening): the ordinary
    # run / pull / inspect surface stays allowed.
    ("podman pull ghcr.io/fpittelo/coach:dev", "allow"),
    ("podman run -i --rm -e VAR=1 ghcr.io/fpittelo/coach:dev", "allow"),
    ("podman ps -a", "allow"),
    ("podman logs coach-dev", "allow"),
    # C8 parity — FORM-dependent, not mechanism-dependent: the `--env-file`
    # form is denied because the `.env` FILENAME appears in the command text
    # (the #167 filename glob), not because the mechanism is constrained.
    ("podman run -i --rm --env-file x.env ghcr.io/fpittelo/coach:dev", "deny"),
    # Recorded accepted residual (MADR-0024 D3/C8, arc42 §3): Podman's
    # run-time secret injection and the non-filename create/start path name
    # no credential FILENAME, so a command-string deny cannot match them —
    # the same class as the accepted recursive-read bypass (#362), tracked
    # upstream (anomalyco/opencode#56545). Pinned as an explicit allow so the
    # residual is legible rather than silently widening; `podman unshare`
    # (arbitrary-UID chown) is likewise pinned as residual — bounded to the
    # invoking uid + subuid range and it is the documented remediation for
    # subuid-owned bind-mount artifacts (#418, C6).
    ("podman run --secret=coach_token,type=env -i --rm x", "allow"),
    ("podman create -e VAR=1 ghcr.io/fpittelo/coach:dev", "allow"),
    ("podman start 7f3a1c9d", "allow"),
    ("podman unshare chown -R 1000:1000 /workspace", "allow"),
    # MADR-0027 (#463, AC0 verdict): the scoped cache-cleanup carve-outs and
    # their preserved boundaries — positive carve-outs, deny preservation on
    # absolute/secret paths, generic-rm and kill-broadcast shapes, and the
    # credential-shadow control that answers the #350 question.
    ("rm -rf .venv", "allow"),
    ("rm -rf pkg/.venv", "allow"),
    ("rm -rf __pycache__", "allow"),
    ("rm -rf pkg/__pycache__", "allow"),
    ("rm -rf .pytest_cache", "allow"),
    ("rm -rf pkg/.pytest_cache", "allow"),
    ("rm -rf /abs/path/.venv", "deny"),
    ("rm -rf /abs/path/__pycache__", "deny"),
    ("rm -rf /abs/path/.pytest_cache", "deny"),
    ("rm -rf ~/.config/opencode/x", "deny"),
    ("rm -rf .venv *", "ask"),
    # Not covered by the carve-outs AND an absolute path: resolves deny via
    # rm -rf /* (pre-existing) — a widening of the carve-outs to absolute
    # paths would flip this to allow and trip the gate.
    ("rm -rf /tmp/opencode/cache", "deny"),
    ("pip install -r creds.env", "deny"),
    ("pip install evil", "ask"),
    # MADR-0032 (#485): the AC2 target-classified kill corpus, verbatim.
    # target 0 (own process group) — the control-plane DoS shape.
    ("kill 0", "deny"),
    ("kill 0 1234", "deny"),
    ("kill 1234 0", "deny"),
    ("kill -TERM 0", "deny"),
    ("kill -s TERM 0", "deny"),
    ("kill --signal TERM 0", "deny"),
    ("kill -- 0", "deny"),
    # target -1 (every process of the user).
    ("kill -1", "deny"),
    ("kill -1 -1", "deny"),
    ("kill -TERM -1", "deny"),
    ("kill -s TERM -1", "deny"),
    ("kill --signal TERM -1", "deny"),
    ("kill -- -1", "deny"),
    ("kill 1234 -1", "deny"),
    # other negative process-group targets (two hyphen tokens).
    ("kill -TERM -12345", "deny"),
    ("kill -- -12345", "deny"),
    # multi-target permutations containing 0 or -1.
    ("kill 0 1234 -15", "deny"),
    ("kill -s TERM 0 1234", "deny"),
    ("kill 1234 0 5678", "deny"),
    ("kill -1 1234", "deny"),
    ("kill 5678 -1", "deny"),
    ("kill 1234 -1 5678", "deny"),
    ("kill -TERM 0 1234", "deny"),
    # R-1: path-qualified DIRECT kill — `*/kill *` is path-general.
    ("/usr/bin/kill 754", "deny"),
    ("/bin/kill -9 1234", "deny"),
    # must-ASK: single-PID forms. The R-2 fix — SIGTERM-by-number (signal
    # `-15` at either position) is a checkpoint, not a hard deny; `-0` is the
    # signal-0 probe (not target 0) and `--signal 1 <pid>` is single-PID
    # SIGHUP.
    ("kill 1234", "ask"),
    ("kill -9 1234", "ask"),
    ("kill -15 1234", "ask"),
    ("kill 1234 -15", "ask"),
    ("kill -s TERM 1234", "ask"),
    ("kill --signal 1 1234", "ask"),
    ("kill -0 1234", "ask"),
    # Recorded limitations (MADR-0032 C2, arc42 §3): a negative numeric
    # target written as the only hyphen token is textually ambiguous with a
    # signal number and stays ASK (the checkpoint) — never ALLOW; and the
    # path-qualified wrapper-to-kill / assignment-prefix classes remain the
    # MADR-0029 residual (pinned as explicit allows for legibility).
    ("kill 1234 -12345", "ask"),
    ("kill -12345", "ask"),
    ("/usr/bin/env kill 754", "allow"),
    ("VAR=1 kill 754", "allow"),
    # MADR-0029 (#475, resolves #468 — C5): the wrapper family resolves DENY
    # at the root tail. Before this delta every one of these commands fell
    # through to the `"*": allow` head (live-verified on v2.3.2); the rows
    # pin both the newly admitted heads and the #468 probe shapes, including
    # the deny-tail command that used to execute (`xargs rm -rf /`).
    ("xargs pip install pkg", "deny"),
    ("env pip install pkg", "deny"),
    ("timeout 5 pip install pkg", "deny"),
    ("xargs rm -rf /", "deny"),
    ("xargs curl --version", "deny"),
    ("xargs printenv --version", "deny"),
    ("exec curl --version", "deny"),
    ("time curl --version", "deny"),
    ("eval curl --version", "deny"),
    ("find . -exec curl --version", "deny"),
    ("nohup curl --version", "deny"),
    ("setsid curl --version", "deny"),
    ("stdbuf -oL curl --version", "deny"),
    ("nice -n 5 curl --version", "deny"),
    ("watch -n 1 curl --version", "deny"),
    ("command curl --version", "deny"),
    # C2 recorded residual, pinned as an explicit ALLOW so the limit is
    # legible rather than a silent widening: bare-prefix patterns are
    # path-insensitive, so a path-qualified wrapper or direct command
    # (`/usr/bin/xargs …`, `/usr/bin/curl …`, `/bin/sh -c …`) is NOT matched.
    # Closing this class needs upstream scanner normalization (arc42 §3).
    ("/usr/bin/xargs curl --version", "allow"),
    ("/usr/bin/timeout 5 curl --version", "allow"),
    ("/usr/bin/curl --version", "allow"),
    ("/bin/sh -c 'curl --version'", "allow"),
)

# Per-segment evaluation of compound command lines (#419): the documented
# opencode semantics (MADR-0004 §"ordering is normative", arc42 §1.1) split a
# command line on ``&&`` / ``;`` / ``|`` and judge EVERY segment, so one
# denied segment blocks the whole line. Without that, the MADR-0024 whole-line
# glob denies would be bypassable by appending an allowed segment.
COMPOUND_TRUTH_TABLE: tuple[tuple[str, str], ...] = (
    # C1/C2 bypass proofs: the deny survives the compound form.
    ("podman pull ghcr.io/fpittelo/coach:dev && podman machine init", "deny"),
    ("podman ps; podman system service --time=0 unix:///run/u/podman.sock", "deny"),
    ("podman ps | podman machine ssh", "deny"),
    # The pre-existing filename deny composes the same way.
    ("podman logs coach-dev; cat .secrets-home.env", "deny"),
    # Non-deny tiers still propagate per segment, and an all-allowed compound
    # stays allowed (the migration is not broken by the compound rule).
    ("rm x; podman ps", "ask"),
    ("podman ps && podman run -i --rm ghcr.io/fpittelo/coach:dev", "allow"),
    # MADR-0029 C5 (#475): the wrapper deny composes per segment — one denied
    # wrapper segment blocks the whole line, so an allowed segment cannot
    # launder `xargs curl` / `timeout 5 printenv`.
    ("true && xargs curl --version", "deny"),
    ("echo ok && timeout 5 printenv --version", "deny"),
    # MADR-0032 C3 (#485) compound controls: the path-qualified kill deny
    # survives the compound form, and the R-2 fix means a numbered-signal
    # segment ASKS instead of hard-denying the whole line.
    ("true && /usr/bin/kill 754", "deny"),
    ("true && kill -15 1234", "ask"),
)

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
SCALAR_TIERS = frozenset({"allow", "ask", "deny"})


class _DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys with their line number.

    PyYAML silently keeps the last duplicate, which would let a second
    ``kill*``-style rule hide behind the first inside an agent bash block
    (C3 fix-up, PR #492 review). Same loader contract as gate 8
    (``check_agent_frontmatter.py``).
    """

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.YAMLError(
                    f"duplicate key {key!r} at line {key_node.start_mark.line + 1}"
                )
            seen.add(key)
        mapping: dict[object, object] = super().construct_mapping(node, deep=deep)
        return mapping


def root_rules(root: Path, failures: list[str]) -> list[tuple[str, str]] | None:
    """Ordered (pattern, tier) pairs of the root permission.bash block."""
    config = root / "opencode.jsonc"
    rel = config.relative_to(root)
    try:
        data = json.loads(strip_jsonc(config.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        failures.append(f"{rel}: unreadable or invalid JSONC ({exc})")
        return None
    permission = data.get("permission")
    if not isinstance(permission, dict):
        failures.append(f"{rel}: missing root 'permission' object")
        return None
    bash = permission.get("bash")
    if not isinstance(bash, dict):
        failures.append(f"{rel}: missing root 'permission.bash' object")
        return None
    return [(str(pattern), str(tier)) for pattern, tier in bash.items()]


def parse_bash_value(
    value: object, rel: str, failures: list[str]
) -> list[tuple[str, str]]:
    """Normalize a parsed ``permission.bash`` YAML value (#350, C3 fix-up).

    Three spellings are accepted, all STRUCTURALLY parsed (the former
    double-quote-only regexes silently skipped unquoted/single-quoted keys,
    hiding a rule from every downstream check — PR #492 review C3):

      * scalar tier (``bash: deny``) → the single catch-all rule
        ``[("*", tier)]`` (opencode scalar semantics);
      * mapping (block or flow, ``bash: {"*": deny}``) → the ordered
        (pattern, tier) pairs, YAML key order preserved;
      * anything else fails closed.
    """
    if isinstance(value, str):
        if value in SCALAR_TIERS:
            return [("*", value)]
        failures.append(
            f"{rel}: unparseable bash value {value!r} — use a scalar "
            f"allow/ask/deny or a mapping (#350)"
        )
        return []
    if isinstance(value, dict):
        rules: list[tuple[str, str]] = []
        for pattern, tier in value.items():
            pattern_text, tier_text = str(pattern), str(tier)
            if tier_text not in SCALAR_TIERS:
                failures.append(
                    f"{rel}: bash rule {pattern_text!r} has invalid tier "
                    f"{tier_text!r} — must be allow, ask or deny (#350)"
                )
                continue
            rules.append((pattern_text, tier_text))
        return rules
    failures.append(
        f"{rel}: bash value must be a scalar tier or a mapping, found "
        f"{type(value).__name__} (#350)"
    )
    return []


def agent_bash(
    root: Path, agent: Path, failures: list[str]
) -> tuple[bool, list[tuple[str, str]]]:
    """(present, rules) of an agent spec's bash posture.

    present=False means the agent omits the bash key entirely — the
    legitimate inherited posture (#340). The YAML front-matter is parsed
    STRUCTURALLY (PyYAML, duplicate keys rejected), so every key spelling —
    double-quoted, single-quoted, unquoted — and all three bash forms (block
    mapping, flow mapping, scalar tier) are seen (#350; C3 fix-up of PR
    #492). Parse/read problems are recorded as failures and fail closed.
    """
    rel = agent.relative_to(root)
    try:
        text = agent.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{rel}: unreadable ({exc})")
        return False, []
    match = FRONT_MATTER_RE.match(text)
    if not match:
        failures.append(f"{rel}: no YAML front-matter found")
        return False, []
    try:
        data = yaml.load(match.group(1), Loader=_DuplicateKeyLoader)
    except yaml.YAMLError as exc:
        failures.append(f"{rel}: front-matter is not valid YAML ({exc})")
        return False, []
    if not isinstance(data, dict):
        failures.append(f"{rel}: front-matter is not a YAML mapping")
        return False, []
    permission = data.get("permission")
    if not isinstance(permission, dict):
        failures.append(f"{rel}: front-matter 'permission' is not a mapping")
        return False, []
    if "bash" not in permission:
        return False, []  # inherited posture — no bash key at all
    return True, parse_bash_value(permission["bash"], str(rel), failures)


def check_root_baseline(
    rules: list[tuple[str, str]], rel: str, failures: list[str]
) -> None:
    """The root block equals BASELINE_ROOT_RULES (order-sensitive pin)."""
    baseline = list(BASELINE_ROOT_RULES)
    ask_len = 1 + len(BASELINE_ASK_TIER)
    if rules == baseline:
        return
    failures.append(
        f"{rel}: root bash block has {len(rules)} rules, the MADR-0015 "
        f"baseline has {len(baseline)} — no removal, no insertion (the root "
        f"block is the single source of truth, #340)"
    )
    diverged_at: int | None = None
    for index in range(min(len(rules), len(baseline))):
        if rules[index] != baseline[index]:
            diverged_at = index
            break
    if diverged_at is None:
        # Prefix equality: the change sits at the end (removal/insertion).
        diverged_at = min(len(rules), len(baseline))
    region = "deny tail" if diverged_at >= ask_len else "ask tier"
    expected = baseline[diverged_at] if diverged_at < len(baseline) else "end-of-list"
    failures.append(
        f"{rel}: root bash block {region} diverges from the MADR-0015 "
        f"baseline at position {diverged_at}: expected {expected!r} — fix "
        f"the config, not the baseline constant"
    )


def check_agent_inheritance(root: Path, failures: list[str]) -> None:
    """Agents inherit the root baseline; only documented deviations may stay."""
    root_patterns = {pattern for pattern, _ in BASELINE_ROOT_RULES}
    for name in AGENT_FILES:
        agent = root / "agents" / name
        rel = agent.relative_to(root)
        present, rules = agent_bash(root, agent, failures)
        if not agent.is_file():
            failures.append(f"{rel}: missing agent spec file")
            continue
        if not present:
            continue  # clean inheritance (#340)
        if not rules:
            failures.append(
                f"{rel}: 'bash:' block present but carries no rules — drop "
                f"the key entirely to inherit the root baseline (#340)"
            )
            continue
        allowed = AGENT_DEVIATIONS[name]
        for pattern, tier in rules:
            if pattern in allowed:
                # Documented role deviation. MADR-0022 (#401, C6): the devops
                # gh carve-out patterns are ALSO root deny-tail patterns —
                # that overlap is intentional (the agent allow overrides the
                # tail for this role only, last-match-wins), so the deviation
                # check must precede the root re-statement check.
                if tier != "allow":
                    failures.append(
                        f"{rel}: role deviation {pattern!r} must be allow-tier, "
                        f"found {tier!r} (#340)"
                    )
            elif pattern in root_patterns:
                failures.append(
                    f"{rel}: bash pattern {pattern!r} re-states the root "
                    f"baseline (opencode.jsonc) — duplication is the defect "
                    f"since #340 (an agent bash map appends AFTER the root "
                    f"deny tail and can widen the posture); drop it and "
                    f"inherit"
                )
            else:
                failures.append(
                    f"{rel}: bash pattern {pattern!r} is not a documented "
                    f"role deviation for this agent (allowed: "
                    f"{sorted(allowed) if allowed else 'none'}) — route a "
                    f"new role signature through @architect first (#340)"
                )


def check_non_inheritance_agents(root: Path, failures: list[str]) -> None:
    """The three non-inheritance agents match their pinned bash shapes (#350).

    scrum-master/code-reviewer/coach do NOT inherit the root baseline:
    they declare an explicit bash posture. Each shape is pinned
    order-sensitively (last-match-wins makes order semantic — the
    scrum-master trailing secret-file denies must stay AFTER its allows,
    else an allow re-enables a root-denied credential-file class).
    """
    for name, expected in NON_INHERITANCE_AGENTS.items():
        agent = root / "agents" / name
        rel = agent.relative_to(root)
        if not agent.is_file():
            failures.append(f"{rel}: missing agent spec file")
            continue
        present, rules = agent_bash(root, agent, failures)
        if not present:
            failures.append(
                f"{rel}: bash posture missing — omitting bash inherits the "
                f"root '*': allow head and widens the posture; declare the "
                f"pinned shape (#350)"
            )
            continue
        if rules != list(expected):
            failures.append(
                f"{rel}: bash posture diverges from the pinned "
                f"order-sensitive shape — expected {list(expected)}, found "
                f"{rules}; agent rules append AFTER the root deny tail "
                f"(last-match-wins), so the trailing '*.env*'/'*.pem*'/"
                f"'*.key*' denies must stay AFTER the allows (#350)"
            )


def resolve(rules: list[tuple[str, str]], command: str) -> str:
    """opencode last-match-wins resolution over the ordered rule list.

    Single command SEGMENT only; use ``resolve_command`` for a whole
    command line (compound commands are judged per segment, #419).
    """
    verdict = "allow"  # opencode's default posture when no rule matches
    for pattern, tier in rules:
        if fnmatch.fnmatchcase(command, pattern):
            verdict = tier
    return verdict


# Compound-command splitter (#419). Deliberately naive — it models the
# documented segment-per-segment evaluation (MADR-0004 §"ordering is
# normative", arc42 §1.1) for the patterns pinned here; it is NOT a shell
# parser (no quoting awareness: a `|` inside a quoted argument would also
# split). Segments are evaluated independently and the worst tier wins, so a
# single denied segment blocks the whole command line.
SEGMENT_SPLIT_RE = re.compile(r"\s*(?:&&|;|\|)\s*")


def resolve_command(rules: list[tuple[str, str]], command: str) -> str:
    """Verdict for a whole command line: per-segment, worst tier wins."""
    verdicts = [
        resolve(rules, segment)
        for segment in SEGMENT_SPLIT_RE.split(command)
        if segment
    ]
    for tier in ("deny", "ask"):
        if tier in verdicts:
            return tier
    return "allow"


def check_truth_table(
    rules: list[tuple[str, str]], rel: str, failures: list[str]
) -> None:
    """Every expected verdict of the MADR-0015 delta must hold on the root."""
    for command, expected in TRUTH_TABLE:
        actual = resolve(rules, command)
        if actual != expected:
            failures.append(
                f"{rel}: command {command!r} resolves to {actual!r}, "
                f"expected {expected!r} (last-match-wins ordering defect, "
                f"fix the config ordering)"
            )


def check_compound_truth_table(
    rules: list[tuple[str, str]], rel: str, failures: list[str]
) -> None:
    """A denied segment must block the whole compound command line (#419)."""
    for command, expected in COMPOUND_TRUTH_TABLE:
        actual = resolve_command(rules, command)
        if actual != expected:
            failures.append(
                f"{rel}: compound command {command!r} resolves to {actual!r}, "
                f"expected {expected!r} (a denied segment must block the whole "
                f"line — per-segment evaluation, MADR-0004)"
            )


RM_CARVEOUT_PATTERNS: tuple[str, ...] = (
    "rm -rf .venv",
    "rm -rf */.venv",
    "rm -rf __pycache__",
    "rm -rf */__pycache__",
    "rm -rf .pytest_cache",
    "rm -rf */.pytest_cache",
)


def check_rm_carveout_placement(root: Path, failures: list[str]) -> None:
    """MADR-0027 C1 canary (#463): the rm carve-outs are ROOT ask-tier ONLY.

    Agent rules append AFTER the root deny tail (#350), so an agent-level
    ``rm -rf */.venv`` allow would defeat the tail for any matching glob —
    verified in the AC0 review: ``rm -rf /home/fr/proj/.venv`` resolves deny
    at root but allow once the glob is appended agent-level. This canary
    fails if the carve-outs are ever (a) removed from the root ask tier or
    (b) mirrored into any agent profile block.
    """
    rules = root_rules(root, failures)
    if rules is None:
        return
    root_map = dict(rules)
    for pattern in RM_CARVEOUT_PATTERNS:
        if root_map.get(pattern) != "allow":
            failures.append(
                f"opencode.jsonc: rm carve-out {pattern!r} must be an ALLOW "
                "in the ROOT permission block (MADR-0027 C1) — root "
                "placement keeps the deny tail last and winning"
            )
    for agent in sorted((root / "agents").glob("*.md")):
        present, agent_rules = agent_bash(root, agent, failures)
        if not present:
            continue
        agent_map = dict(agent_rules)
        for pattern in RM_CARVEOUT_PATTERNS:
            if pattern in agent_map:
                failures.append(
                    f"{agent.relative_to(root)}: rm carve-out {pattern!r} is "
                    "FORBIDDEN at agent level (MADR-0027 C1) — an "
                    "agent-level glob allow appends after the deny tail and "
                    "defeats it; the carve-out lives in the root ask tier "
                    "only"
                )


def check_wrapper_carveout_canary(root: Path, failures: list[str]) -> None:
    """MADR-0029 C4 canary (#475): no agent may re-admit a denied wrapper.

    Agent rules append AFTER the root deny tail (last-match-wins, #350), so an
    agent-level allow/ask for a denied wrapper head silently defeats the
    MADR-0029 tail for that role. The canary inspects EVERY agent spec —
    allow-default (inheritance) and non-inheritance alike — and rejects any
    allow/ask rule whose executable head is a denied wrapper, including narrow
    (`xargs rm*`) and path-qualified (`/usr/bin/xargs *`) variants.
    """
    for agent in sorted((root / "agents").glob("*.md")):
        present, agent_rules = agent_bash(root, agent, failures)
        if not present:
            continue
        rel = agent.relative_to(root)
        for pattern, tier in agent_rules:
            if tier not in ("allow", "ask"):
                continue
            tokens = pattern.split()
            head = tokens[0].rsplit("/", 1)[-1] if tokens else ""
            # `find` is not denied as a head; only its `-exec*` form is, so an
            # agent rule re-admitting that form is the same defect.
            readmits = head in WRAPPER_DENY_HEADS or (
                head == "find" and " -exec" in pattern
            )
            if readmits:
                failures.append(
                    f"{rel}: bash rule {pattern!r} ({tier}) re-admits a "
                    "denied wrapper head (MADR-0029 C4) — agent rules append "
                    "after the root deny tail, so this defeats the wrapper "
                    "deny for this role; wrappers have NO agent-level "
                    "carve-out of any kind"
                )


def check_kill_carveout_canary(root: Path, failures: list[str]) -> None:
    """MADR-0032 C4 canary (#485): no agent may re-admit the kill family.

    Agent rules append AFTER the root deny tail (last-match-wins, #350), so an
    agent-level allow/ask for `kill` silently defeats the target-classified
    kill denies for that role. The canary inspects EVERY agent spec —
    allow-default (inheritance) and non-inheritance alike — and rejects any
    allow/ask rule whose executable head is `kill`, including narrow
    (`kill 1234`), globbed (`kill*`, `/usr/bin/kill*`, `*/kill*`, `*kill*`)
    and path-qualified (`/usr/bin/kill *`) variants: the head check strips
    `*` from the basename, so any head whose core is `kill` is caught while
    unrelated words (`pkill`, `killall`) are not (C3 fix-up, PR #492). The
    kill checkpoint has NO agent-level carve-out of any kind (AC6), and the
    bare `kill*` ask line in the root ask tier is the only kill checkpoint.
    """
    for agent in sorted((root / "agents").glob("*.md")):
        present, agent_rules = agent_bash(root, agent, failures)
        if not present:
            continue
        rel = agent.relative_to(root)
        for pattern, tier in agent_rules:
            if tier not in ("allow", "ask"):
                continue
            tokens = pattern.split()
            head = tokens[0].rsplit("/", 1)[-1] if tokens else ""
            if head.strip("*") == "kill":
                failures.append(
                    f"{rel}: bash rule {pattern!r} ({tier}) is an agent-level "
                    "kill carve-out (MADR-0032 C4) — agent rules append after "
                    "the root deny tail, so this defeats the target-classified "
                    "kill denies for this role; kill has NO agent carve-out of "
                    "any kind"
                )


def main(argv: list[str]) -> int:
    root = (
        Path(argv[1]).resolve()
        if len(argv) > 1
        else Path(__file__).resolve().parents[2]
    )
    if not root.is_dir():
        print(f"error: REPO_ROOT is not a directory: {root}", file=sys.stderr)
        return 1
    failures: list[str] = []
    root_rule_list = root_rules(root, failures)
    if root_rule_list is not None:
        check_root_baseline(root_rule_list, "opencode.jsonc", failures)
        check_truth_table(root_rule_list, "opencode.jsonc", failures)
        check_compound_truth_table(root_rule_list, "opencode.jsonc", failures)
    check_agent_inheritance(root, failures)
    check_non_inheritance_agents(root, failures)
    check_rm_carveout_placement(root, failures)
    check_wrapper_carveout_canary(root, failures)
    check_kill_carveout_canary(root, failures)
    if failures:
        print("FAIL check_bash_permission_tiers: bash tier invariant violated:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(
        f"PASS check_bash_permission_tiers: root permission.bash equals the "
        f"MADR-0015 baseline (allow head + {len(BASELINE_ASK_TIER)} ask + "
        f"{len(BASELINE_DENY_TAIL)} deny rules, order-sensitive), "
        f"{len(TRUTH_TABLE)}-case last-match-wins truth table green, "
        f"{len(COMPOUND_TRUTH_TABLE)}-case per-segment compound table green, "
        f"{len(AGENT_FILES)} allow-default agents inherit the root baseline "
        f"with zero root re-statements, and {len(NON_INHERITANCE_AGENTS)} "
        f"non-inheritance agents match their pinned order-sensitive bash "
        f"shapes incl. the scrum-master trailing secret-file denies "
        f"(#340, #350; opencode 1.19.0 verified); {len(WRAPPER_DENY_PATTERNS)}-"
        f"pattern wrapper-family deny with zero agent re-admission "
        f"(MADR-0029, #475); {len(KILL_DENY_PATTERNS)}-pattern "
        f"target-classified kill deny (broadcast + negative process-group + "
        f"path-qualified direct kill) with zero agent re-admission "
        f"(MADR-0032, #485)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
