# MADR-0004: Allow-by-default bash permission posture with catastrophic-deny guardrails

- **Status:** accepted
- **Date:** 2026-10-03
- **Deciders:** @fpittelo, @architect, @cyber-security

## Context

The Product Owner directed on 2026-10-03: *"remove the restriction requiring my constant validation, while preventing catastrophic commands like rm"*. The bash permission posture had accreted over three hardening rounds (#86 repo-level guardrails → #89 targeted `~/.config` credential denylist → #123 per-agent allowlists) into two friction layers:

1. **Global** `opencode.jsonc` `permission.bash`: `"*": "ask"` plus a short allowlist — every off-list command prompted the PO.
2. **Per-agent** `agents/{architect,developer,devops,cyber-security}.md` front-matter: `"*": deny` plus long hand-curated allowlists — every off-list command was blocked outright, forcing manual PO action.

The result was that routine autonomous work (git plumbing, python invocations, harness gates, file operations) constantly interrupted the sprint loop the governance system exists to enable — the exact failure mode MADR-0003's Proportionate Quality Gates principle (KIS/YAGNI) warns against, applied to permissions.

A STRIDE threat model by @cyber-security (2026-10-03) returned **APPROVE-WITH-CHANGES** for an allow-by-default posture on this single-user, git-tracked, non-production workstation, with required changes baked into the specification (issue #158): keep the three gatekeeper/charter agents unchanged, add an ask-tier checkpoint, extend the catastrophic deny tail, compensate the bash-read gap, and deny inline-code interpreters.

## Decision Drivers

- **PO velocity mandate (2026-10-03):** routine agent work must run without constant validation prompts.
- **Proportionate guardrails (MADR-0003 principle extended to permissions):** a control's cost must be proportional to the risk it mitigates — per-agent hand-curated allowlists are high-cost, high-friction, and rot across sprints.
- **Catastrophic-command prevention:** `rm -rf /`, device writes, privilege escalation, force-push and friends must remain hard-blocked, not merely prompted.
- **Separation of duties:** `@code-reviewer` (read-only gatekeeper), `@scrum-master` and `@coach` (zero local bash) keep their postures unchanged.
- **Bash-read gap:** file `read` permission denies are NOT enforced on bash tool output (pre-existing #89 advisory) — secret files readable via `cat` need bash-level compensating denies.
- **Swiss nLPD:** zero secrets in repo or logs; all credential denies unchanged.

## Considered Options

### Option 1: Status quo — ask/deny-by-default with allowlists

- Pros: strictest default; every off-list command surfaces to a human.
- Cons: constant validation prompts (global layer) and hard blocks (per-agent layer) on routine work; allowlists rot (three accretion rounds #86 → #89 → #123); explicitly rejected by the Product Owner.

### Option 2: Blanket allow — no denies, no ask-tier

- Pros: zero friction.
- Cons: nothing stops `rm -rf /`, `dd of=/dev/sda`, `git push --force`, or secret reads; fails the STRIDE review; rejected.

### Option 3: Allow-default + ask-tier + catastrophic deny tail

- Pros: routine work runs unprompted; a single checkpoint covers destructive-but-recoverable operations; catastrophic/irreversible/bypass commands are hard-denied; one uniform, auditable posture across the four build agents; allowlist rot eliminated.
- Cons: pattern denies stop impulsive/accidental damage, not a determined adversarial agent (residual risk — see Security Considerations).

## Decision Outcome

Chosen option: **Option 3 — allow-by-default with a three-tier bash permission table**, implemented in `opencode.jsonc` (global) and `agents/{architect,developer,devops,cyber-security}.md` (per-agent, role-tailored; `@devops` keeps an explicit `docker *` allow and `@cyber-security` keeps its audit-tool allows as legible role signatures):

1. **Allow tier:** `"*": allow` — routine commands run unprompted.
2. **Ask tier:** single checkpoint for destructive-but-recoverable operations — `rm *`, `pip install*`, `npm install -g*` / `npm i -g*`, `kill*` / `pkill*` / `killall*`, `chmod *`, `chown *`, `systemctl*`.
3. **Deny tail:** hard denies for catastrophic / irreversible / bypass commands — privilege escalation (`sudo*`); filesystem destruction (`rm -rf` variants on `/`, `~`, `$HOME`); disk and device tools (`mkfs*`, `dd *of=/dev/*`, `shred*`, `wipefs*`, `blockdev*`, `fdisk*`, `sfdisk*`, `gdisk*`, `parted*`, `truncate * /dev/*`); block-device redirection and moves (`* > /dev/sd*` and the nvme/mmcblk/vd/hd variants, `mv * /dev/…`); power/state (`shutdown*`, `reboot*`, `halt*`, `poweroff*`, `systemctl poweroff*` / `reboot*` / `halt*`); persistence (`crontab*`, `systemd-run*`); recursive permission changes on absolute paths (`chmod -R * /*`, `chown -R * /*`); bulk deletion (`find * -delete*`, `find * -exec rm*`); git history destruction (`git push --force*`, `git push -f*`, `git filter-branch*`, `git filter-repo*`, `git clean*`, `git reset --hard*`); network fetchers (`curl*`, `wget*`); inline-code interpreters (`bash -c *`, `sh *`, `python* -c*`, `node -e*`, `node --eval*`, `perl -e*`, `ruby -e*`); environment and secret reads (`printenv*`, `env`, `cat *.secrets.env*`, `cat /proc/*/environ*`).

Ordering is normative: broad rules first, deny rules last — opencode evaluates rules in order and the **last matching rule wins**; compound commands (`&&`, `;`, `|`) are split and **every segment** is evaluated, so one denied segment blocks the whole command.

**Supersession:** this decision supersedes the #123 per-agent bash allowlist policy (AC4 of #89) and the #86-era global ask-default + allowlist. The #89 targeted `~/.config` `read`/`edit` credential denylist and the #150 `COACH_*` MCP denies are NOT affected. The `@code-reviewer` read-only bash allowlist and the `@scrum-master` / `@coach` scalar `bash: deny` remain unchanged (SoD / charter invariants).

## Consequences

- **Positive:** routine agent work (git, python, harness, file ops) runs without prompts; destructive-but-recoverable operations get exactly one checkpoint; catastrophic/irreversible/bypass commands are hard-blocked; the four build agents share one uniform, auditable posture; the allowlist-maintenance burden disappears.
- **Negative:** accepted residual risk — pattern denies stop impulsive/accidental damage, NOT a determined adversarial agent: write-then-execute (`bash evil.sh` written via the file-write tool), variable indirection (`CMD="rm -rf /"; $CMD`), fork bombs, `docker run -v /:/host --privileged`, and the upstream opencode symlink/realpath permission gap all remain open bypasses.
- **Mitigations (compensating controls):** git recoverability of the tracked tree; gitleaks (diff-scoped per PR, full-history weekly and at every qa → main promotion — MADR-0003); human promotion gates (`dev` → `qa` → `main` require explicit @fpittelo approval); `@code-reviewer` SoD APPROVE before any merge; session transcripts; CODEOWNERS on the permission surface; single-user blast radius (no multi-tenant exposure).

## Security Considerations

- **STRIDE verdict (2026-10-03): APPROVE-WITH-CHANGES** — proportionate for a single-user git-tracked workstation, non-production. Required changes, all implemented in #158: (1) do not flip `@code-reviewer` / `@scrum-master` / `@coach`; (2) ask-tier checkpoint for destructive-but-recoverable operations; (3) extended catastrophic deny tail (device tools, block-device redirection, persistence, git history destruction, inline interpreters); (4) bash-read gap compensating denies; (5) inline-code interpreter denies matching the existing `bash -c` / `sh` rationale; (6) residual risk documented and accepted (this section).
- **Bash-read gap:** file `read` denies are not enforced on bash tool output (pre-existing #89 advisory) — `cat ~/.config/opencode/.secrets.env` would pass a bare `cat *` allow. Compensating bash denies close the primary secret store: `cat *.secrets.env*`, `printenv*`, `env`, `cat /proc/*/environ*`. The `read`/`edit` credential denies remain the primary control for the file tools.
- **Accepted residual risk:** write-then-execute, variable indirection, fork bombs, `docker --privileged` / host-mount, and the upstream symlink/realpath permission gap. These are documented, accepted, and bounded by the compensating controls above; the docker hardening and upstream gap are candidate follow-ups (out of scope here).