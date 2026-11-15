# MADR-0027: Scoped cleanup and process-management carve-outs

- **Status:** accepted
- **Date:** 2026-11-15
- **Deciders:** @fpittelo (PO — audit #460 R3 sponsor), @architect (phase-2 binding spec), @cyber-security (AC0 pre-implementation verdict — the reviewed basis)

## Context

Audit #460 R3 (shell autonomy): routine agent cleanup commands (virtualenv/build caches) and process management currently hit **ask-tier prompts**, pausing autonomous runs for the PO. The friction is real but the fix must not weaken the deny tail: since #350, **agent rules append AFTER the root deny tail** (last-match-wins), so an agent-level allow for a glob that also matches deny-tail shapes would silently defeat the tail — verified in the AC0 review: an agent-level `rm -rf */.venv` allow flips `rm -rf /home/fr/proj/.venv` from `deny` to `allow`, defeating 71/72 tail entries for that glob.

The @cyber-security AC0 verdict (comment 6894867168) reviewed the proposed allow set and delivered the binding scope: **1 of 3 families approved, 1 modified, 1 rejected**. It also surfaced a finding that reframes the whole recommendation: **the ask tier is bypassable by command prefixes** (`xargs`/`env`/`timeout`/`nohup` catch the root `"*": allow` head before any ask/deny pattern matches — confirmed live: `xargs printenv --version` and `xargs curl --version` execute despite root deny-tail entries). The ask tier is therefore a **friction boundary, not a security boundary** against a determined agent — which argues for a *smaller* carve-out set, not a larger one. The bypass is routed to follow-up **#468** (out of #463's scope).

## Decision Drivers

- PO burden: evidence-first carve-outs only (observed ask prompts; no speculative allows — YAGNI).
- #350 mechanics: agent-level placement of glob allows defeats the deny tail — placement is normative.
- Supply-chain surface: `pip install` executes attacker-chosen code from a remote index at install time (PEP 517 build backends) with access to the profile-scoped secrets.
- Control-plane DoS: `kill` broadcast forms (`kill 0`, `kill -1`, `kill <pid> -1`) can terminate the opencode service daemon — a session-wide tool outage for every agent.
- Evidence-first kill inventory: no per-case AC1 evidence of a legitimate recurring `kill` need surfaced.

## Considered Options

### Option 1: rm cache-cleanup carve-outs — APPROVE with scope

- Pros: bounded to regenerable build artifacts; exact-literal and trailing-fixed-segment globs verified safe against the real resolver (18/18 negative controls deny; 50+6 pinned truth tables green).
- Cons: the `*/` variants can reach matching directories **outside** the workspace via `..` (same traversal class as MADR-0015's `rm /tmp/opencode/*` gap) — accepted residual; the traversal is visible in the command string.

### Option 2: kill carve-outs — MODIFY, then DEFERRED

- Pros: single-PID process management is a plausible convenience.
- Cons: no per-case AC1 evidence (the audit's evidence was "process management" without inventory); the naive allow forms match broadcast shapes (`kill 1234 -1` verified matching `kill [1-9][0-9]*`); the daemon-kill self-DoS is not eliminable by pattern (PIDs are runtime values).

### Option 3: pip install carve-outs — REJECT

- Pros: none established — the observed dependency path (`uv sync`, `uv sync --frozen`, `uv sync --all-extras`, `uv pip compile`) already resolves **allow** via the root `"*"` head (verified).
- Cons: no scoped form is safe here — hash-pinned installation is theoretically defensible but not implementable (no `pyproject.toml`/`uv.lock`/`requirements*.txt`; this repo's Python tooling installs inside the hardened container via `uv sync --frozen`); version-pinning alone still trusts the index artifact.

## Decision Outcome

Chosen ruling (the three families, per the AC0 verdict and the phase-2 binding spec):

1. **`rm` — APPROVED, 6 patterns, ROOT ask-tier placement only** (after the `rm *` ask line, before the deny tail): `rm -rf .venv`, `rm -rf */.venv`, `rm -rf __pycache__`, `rm -rf */__pycache__`, `rm -rf .pytest_cache`, `rm -rf */.pytest_cache`. **C1 (normative):** agent-level placement of these patterns is FORBIDDEN — enforced by the gate-14 canary `check_rm_carveout_placement` (asserts the allows exist in the root permission block and in NO agent profile block; a mutation moving them agent-level fails the suite). The trailing `*.env*`/`*.pem*`/`*.key*` denies keep their position (no allow is added after them; root placement keeps the deny tail last and winning — `pip install -r creds.env` and `rm -rf x.env` stay deny, asserted in the truth table).
2. **`kill` — allow DEFERRED (C4(b)):** no per-case AC1 evidence, so **no kill allow lands** (YAGNI); plain `kill <pid>` stays ask-tier. The **3 protective deny-tail entries DO land** (empirically grounded by the pre-review mass-SIGTERM probe): `kill 0*`, `kill -1*`, `kill * -1*` — appended at the end of the root deny tail (after the MADR-0024 podman entries), additions only (tightening: `kill 0`/`kill -1` were ask, now deny).
3. **`pip install` / `uv pip install` — REJECTED:** no permission change; `pip install*`, `pip3 install*`, `uv pip install*`, `*-m pip install*` stay ask-tier. The legitimate dependency path (`uv sync`) already resolves allow; the docs correction (Admin guide §2.x/§3.8) states "use `uv sync` — `pip install` intentionally remains ask-tier (AC0 verdict, supply-chain)". If a future friction demand persists, the vehicle is a new MADR introducing hash-pinned installation with a committed lockfile — not a carve-out.
4. **Prefix bypass** (ask/deny tiers bypassable via `xargs`/`env`/`timeout`/`nohup` prefixes and compound commands) is **out of scope** — routed to **#468** (severity high, @architect-groomed); recorded in `arc42/03` §3 as an accepted limitation of the string-matching model, alongside the recursive-read (#362) and Podman `--secret` (#419) residuals.

## Consequences

- **Positive:** the six cache-cleanup commands no longer prompt (PO-burden relief without deny-tail weakening); kill broadcast forms are **tightened** from ask to deny (the one posture change, justified by the C2 blast radius); the placement invariant is machine-enforced (C1 canary), closing the #350 trap for this family.
- **Negative:** the root deny tail grows 70 → 73 (every future tail edit must update the gate-20 parity canary deliberately); the `*/` rm variants keep the `..` traversal residual; the prefix bypass remains until #468 lands.
- **Mitigations:** C1 canary in gate 14; the truth table now pins the positive carve-outs, the deny-preservation controls (absolute-path and credential-shadow), the generic-rm and kill-broadcast shapes, and the `/tmp/opencode/cache` negative control; gate 20 asserts the 73-entry parity on the INSTALLED posture (symlink → live on the working-tree edit).

## References

- #463 (this change), #460 (audit R3), #468 (prefix-bypass residual), #350 (append-override mechanics), #405/#448 (the `git add -A`/credential incident class motivating the file-centric denies)
- MADR-0015 (ask-tier slimming — the tail-touching precedent), MADR-0024 (root deny + scoped carve-outs precedent)
- `harness/config-validation/check_bash_permission_tiers.py` (BASELINE_ASK_TIER, BASELINE_DENY_TAIL 73, `check_rm_carveout_placement`), gate 20 parity canary
- @cyber-security AC0 verdict 2026-11-15 (comment 6894867168) — binding spec (comment 6894876606)
