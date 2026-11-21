# MADR-0029: Deny the bash wrapper family at the root permission tail

- **Status:** accepted
- **Date:** 2026-11-21
- **Deciders:** @architect, @cyber-security, @fpittelo

## Context

Issue #468 recorded a **live-verified permission bypass** of the bash ask tier and of the root deny tail on the installed engine (opencode **v2.3.2**). The v2 shell scanner resolves **each subcommand's own raw text** as the permission resource, and the rule list is **last-match-wins**: a wrapper prefix therefore matches the root `"*": allow` head and no later ask/deny pattern is ever consulted for the inner command.

Verified shapes on v2.3.2 (LIVE engine + source replay of the v2 matcher):

| Probe | Expected | Observed before this decision |
| :--- | :--- | :--- |
| `xargs pip install <pkg>` | ask | **allow** |
| `env pip install <pkg>` | ask | **allow** |
| `timeout 5 pip install <pkg>` | ask | **allow** |
| `xargs printenv --version` | deny (`printenv*`) | **allow → executed** |
| `xargs curl --version` | deny (`curl*`) | **allow → executed** |
| `xargs rm -rf /` | **deny** (`rm -rf /`) | **allow** |
| `nohup` / `setsid` / `command` / `xcrun` + `curl` | deny | **allow** |

Bare controls (unprefixed `pip install`, `printenv`, `curl`, `rm -rf /`) all resolve correctly — only the wrapper-prefix class is open. A secondary finding: on "Allow always" the engine saves the **wrapper prefix** (`xargs *`) as the grant, so an approval would widen the hole instead of closing it.

Constraints and forces:

- **Upstream position.** The maintainers designate **wrapper-scoped denies as the sanctioned workaround**: anomalyco/opencode#54008 (“bash permission patterns match only each command's own text, so a wrapper passes a deny rule written for the inner command”) is **closed as not planned**; #58775 is **open and reproduced** with no fix PR; #62513 (“bash deny rules don't apply through wrappers (time, env, bash -c) on v2”) is **closed as duplicate**. The same last-match-wins class was already accepted as residual for the recursive-read bypass (#362, upstream #56545) and the Podman `--secret` injection (#419, MADR-0024 D3/C8).
- **No delivery vehicle for an engine fix.** The engine is **unpinned** and there is no CI vehicle that could ship or regression-test an upstream scanner normalization — a repo-side fix cannot reach the runtime.
- **Prior state.** The class was recorded as an **accepted residual** in arc42 §3 and routed from MADR-0027 (#463 AC0 verdict) to #468, with the explicit follow-up options “deny the wrapper commands at the root tail, or re-model matching”.
- **Governance.** Decision class requires a MADR (MADR-0015/0024/0027 precedent). The @cyber-security MADR-0008 review returned **APPROVE-WITH-CONDITIONS**; conditions **C1–C8** are binding and were executed as the acceptance criteria of #475.

## Decision Drivers

- **Deny-tail guarantees must hold for wrapper-prefixed spellings** — `xargs rm -rf /` and `xargs curl …` executing while their direct forms are denied is a real guarantee gap, not a cosmetic one (single-user local blast radius, but a prompt-injected agent can reach deny-tail shapes).
- **KIS & YAGNI (#180) / MADR-0003 proportionate controls** — a config-side, deny-only, additions-only change with machine gates, instead of forking, pinning or re-implementing the engine (explicitly out of scope).
- **Root-tail discipline (#340/#350)** — the mitigation must live in the root `permission.bash` tail with **no agent-level carve-out of any kind**, because agent rules append after the tail and would defeat it.
- **Order is semantic** — last-match-wins and per-segment compound evaluation (`&&`, `;`, `|`) mean the deny must be appended **last** and the gates must *resolve*, not merely count.
- **Honesty of the residual** — the prefix space is unbounded; whatever cannot be enumerated must be recorded, monitored and re-evaluated upstream (#362 protocol), never silently widened.

## Considered Options

### Option 1: Root-tail wrapper deny family (CHOSEN)

Deny the curated bash wrapper/executor family at the **root deny tail** (appended after every existing entry, so it is the last match), and harden the gates: truth-table rows for every newly admitted head plus a compound form, a semantic canary forbidding any agent `allow`/`ask` rule whose executable head is a denied wrapper, and gate-20 resolution of representative wrapper commands against the **ordered** installed rules.

- Pros: closes the live-verified class for every enumerated head for every agent; deny-only, additions-only, reversible; single-sourced in `opencode.jsonc`; no engine dependency; machine-enforced (gate 14 pin/truth table/canary + gate 20 ordered resolve).
- Cons: the tail grows 73 → 86; legitimate wrapper usage becomes friction-free-impossible (`timeout`, `nice`, `watch`, `env`, `find -exec`, …); a residual remains (see Consequences).

### Option 2: Upstream scanner normalization

Fix the matcher upstream (normalize a wrapper's payload into a permission resource) and ship it through the installed engine.

- Pros: addresses the root cause for the whole unbounded class.
- Cons: **no delivery vehicle** — the engine is unpinned and no CI path can deliver or regression-test it; #54008 is closed not-planned and #58775 has no fix PR. Routed per the #362 protocol (passive re-evaluation on upstream movement); persists as residual class (d).

### Option 3: Formal residual without mitigation

Record the bypass as an accepted residual and rely on operator review.

- Pros: zero config churn, no false positives.
- Cons: **rejected while `xargs curl` executes a deny-tail command live** — it would accept a known, cheaply reachable destruction/execution path without even the friction gate.

## Decision Outcome

Chosen option: **"Option 1: Root-tail wrapper deny family"**, because it is the only lever with a delivery vehicle that closes the live-verified class for every enumerated head, and it satisfies the root-tail/ordering discipline while keeping the residual explicit.

### C1 — Curated family (13 root deny-tail entries, appended last)

`xargs *`, `env *`, `timeout *`, `nohup *`, `setsid *`, `stdbuf *`, `nice *`, `watch *`, `command *`, `exec *`, `time *`, `eval *`, `find * -exec*` — tail **73 → 86**, additions only, no removals, no reordering of existing entries. **No agent-level wrapper carve-out of any kind** (C4 canary enforces it).

### Dispositioned inventory of the remaining executors (C1)

Every other Linux command-executing wrapper is dispositioned here. None is denied in this delta; each is an explicit **residual** of class (c) "non-enumerated executors" — the prefix space is unbounded, so enumerating it is the mitigation ceiling, not a closure. One-line rationale each:

| Executor | Disposition | Rationale |
| :--- | :--- | :--- |
| `ionice` | residual | I/O-scheduling hint only; no privileged or destructive primitive of its own; executes whatever payload it is given. |
| `chrt` | residual | Sets real-time scheduling policy on **own** processes (host-starvation risk bounded to the user session); no privilege gain above uid 1000; payload executes. |
| `taskset` | residual | CPU-affinity hint only; payload executes. |
| `flock` | residual | Advisory lock wrapper used by legitimate script sequencing; payload executes. |
| `unshare` | residual | Unprivileged namespace creation is bounded to the user's own uid (same class as the accepted `podman unshare` residual, MADR-0024 D3/C1–C3); payload executes. |
| `nsenter` | residual | Requires an existing namespace/pid the caller can already reach as the same uid; no escalation above uid 1000. |
| `setpriv` | residual | Can only **drop** privileges; it cannot raise them without privilege already held. |
| `bwrap` | residual | bubblewrap relies on unprivileged user namespaces, bounded to uid 1000 — the same exposure class the rootless Podman migration accepted (MADR-0024). |
| `script` | residual | Records a session through a pty; payload executes as the same uid. |
| `unbuffer` | residual | `expect`-shipped pty wrapper; payload executes as the same uid. |
| `parallel` | residual | Functionally an `xargs` sibling (arbitrary payload launcher) and the highest-value follow-up; not part of the #475 AC1 inventory, so recorded here rather than silently added (KIS) — candidate for a later tightening. |

### C2 — Path qualification

The wrapper patterns are **bare-prefix** globs and therefore **path-insensitive** by construction: `xargs *` matches `xargs …`, not `/usr/bin/xargs …`. This is reviewed and accepted — false positives block in the safe direction (a `nice -n 5 …` invocation is denied). Path-qualified wrapper spellings (`/usr/bin/xargs …`) **and** path-qualified direct commands (`/usr/bin/curl …`, `/bin/sh -c …`) are recorded as **explicit residual** and pinned as truth-table **allows** so the limit stays legible instead of silently widening.

### C3 — Gate 20 resolves in order

`check_installed_posture_freshness.py` no longer only checks deny-set membership: it resolves `xargs pip install pkg`, `timeout 5 curl`, `env gh api` and the compound `true && xargs curl` against the **ordered** installed rules using gate 14's resolver and requires `deny` — membership alone is insufficient because the `"*": allow` head can sit after the denies in a drifted posture.

### C4 — Semantic canary

`check_bash_permission_tiers.py` gains `check_wrapper_carveout_canary`: every agent spec (inheritance and non-inheritance) is inspected and any `allow`/`ask` rule whose executable head is a denied wrapper fails the gate — including narrow (`xargs rm*`) and path-qualified (`/usr/bin/xargs *`) variants, plus a `find … -exec…` readmission (only that form of `find` is denied).

### C5 — Truth-table pins

`BASELINE_DENY_TAIL` gains the 13 patterns; truth rows cover every newly admitted head plus the #468 probe shapes (`xargs pip install …`, `env pip install …`, `timeout 5 pip install …`, `xargs rm -rf /`, `xargs curl --version`, `xargs printenv --version`, `exec`/`time`/`eval … curl …`, `find … -exec curl …`) and a compound form; the tail-order pin (`kill` entries no longer last — the wrapper block is) and the deny-count pin (73 → 86) are updated **deliberately** with justification comments.

### C6/C7 — Live evidence and saved-grant precedence (opencode v2.3.2)

Verified on the installed engine through the **permission decision layer only** (no destructive or network probe was executed):

| Probe (decision layer) | Result |
| :--- | :--- |
| `xargs curl --version` | `permission.rejected` (deny) |
| `xargs printenv --version` | `permission.rejected` (deny) |
| `env printenv --version` | `permission.rejected` (deny) |
| `stdbuf -oL printenv --version` | `permission.rejected` (deny) |
| `nice -n 5 printenv --version` | `permission.rejected` (deny) |
| `time printenv --version` / `eval …` / `command …` | `permission.rejected` (deny) |
| `find . -maxdepth 0 -exec printenv --version` | `permission.rejected` (deny) |
| `true && xargs curl --version` | `permission.rejected` (deny) |
| `xargs echo hi`, `timeout 5 echo hi` | `permission.rejected` (deny — wrapper-specific, inner command otherwise allowed) |
| `echo control-hi && uname -s` | allowed (control: normal commands are unaffected) |

**Saved-grant precedence (C7):** the project carries pre-existing saved `shell / timeout *` grants. `timeout 5 printenv --version` and `timeout 5 echo hi` now resolve **deny**, i.e. the **configured deny takes precedence over the saved grant** on v2.3.2. Live scoring is the runtime proof; CI (gates 14/20) is **configuration-intent enforcement, not runtime proof**.

## Consequences

- **Positive:** the live-verified #468 wrapper bypass is closed at the root tail for every enumerated head and every agent; the deny decision is verified through the engine's permission layer, including the configured-deny-over-saved-grant precedence the #468 approval path would otherwise have widened; the gates can no longer be satisfied by a deny set whose order defeats itself, and an agent-level wrapper carve-out is now a machine failure.
- **Negative:** the root tail grows **73 → 86** and every future tail edit must update the gate-14 pin, the tail-order pin and the gate-20 count/parity canary deliberately; legitimate wrapper invocations (`timeout`, `nice`, `watch`, `env`, `find -exec`, `parallel`-adjacent workflows) are now denied and must be spelled out directly — accepted friction, the deny blocks in the safe direction; `parallel`, a genuine `xargs` sibling, remains allowed until a later tightening.
- **Residual (PO-accepted, Medium — single-user local blast radius):** (a) env-var assignment prefixes (`VAR=x curl …`), (b) path-qualified wrapper **and** direct-command spellings (`/usr/bin/xargs …`, `/usr/bin/curl …`, `/bin/sh -c …`), (c) non-enumerated executors (the dispositioned inventory above — the prefix space is unbounded), (d) the unpinned engine (no CI vehicle for a runtime fix). The ask tier therefore remains a **friction boundary and defense-in-depth string filter, NOT a security boundary** against a determined agent.
- **Mitigations:** monitoring is passive re-evaluation on upstream movement (#58775 open/reproduced; #54008 closed not-planned; #62513 duplicate) per the #362 precedent and MADR-0024 D3/C8; the file-centric credential denies still bound the readable secret set (`*/.config/opencode*`, `*.env*`, `*.pem*`, `*.key*`); the canary keeps the tail root-only; upstream normalization stays routed per the #362 protocol rather than re-implemented locally.
