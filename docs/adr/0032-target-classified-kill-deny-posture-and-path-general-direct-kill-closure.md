# MADR-0032: Target-classified kill deny posture and path-general direct-kill closure

- **Status:** accepted
- **Date:** 2026-11-22
- **Deciders:** @cyber-security (APPROVE-WITH-CONDITIONS C1–C5, 2026-11-22 — binding; PR-stage corpus verification + C3/C4/C5 fix-up review on PR #492), @architect (spec + grooming), @fpittelo (PO — Sprint 36 dispatch #490; Option-A amendment for ambiguous single-hyphen negative numeric targets, recorded on #485, 2026-11-22)

## Context

The #482 AC7 configuration audit (independent resolver replay at `93198e7`) surfaced two **pre-existing** kill-family posture findings, and MADR-0030 routed both here rather than fixing them inside a no-change decision:

- **R-1 (severity::medium) — the `kill*` ask checkpoint was path-bypassable.** The ask tier pins the bare prefix `kill*`, so path-qualified spellings fell through to the root `"*": allow` head: `/usr/bin/kill 754` and `/bin/kill -9 1234` resolved **allow** and executed unprompted. This is the kill-specific instance of the MADR-0029 accepted residual class (b) (path-qualified direct-command spellings).
- **R-2 (severity::low) — the deny tail over-matched signal numbers.** MADR-0027 shipped three *signal-prefix* patterns — `kill 0*`, `kill -1*`, `kill * -1*` — so `kill -1*` matched `kill -15 <pid>` and `kill * -1*` matched `kill <pid> -15`: SIGTERM-by-number was hard-**DENIED** while `kill <pid>` / `kill -9 <pid>` (the same operation) were only ask. Friction in the safe direction, but incoherent.

Both fixes are deny-side edits to the frozen root deny tail, which the MADR-0027/MADR-0024 additions-only doctrine forbids by default. This MADR exists to take that doctrine decision explicitly, with a security verdict, instead of letting a "small" tail edit ride in as a chore.

## Decision Drivers

- Security: the kill checkpoint must not be bypassable by spelling the same binary with a path — the R-1 class is already accepted for the *wrapper* family (MADR-0029) but a **direct** `kill` bypass of the checkpoint is strictly worse than a wrapper bypass because it needs no wrapper at all.
- Coherence: a deny tail must deny the **destructive target classes** (own process group `0`, all-user broadcast `-1`, negative process groups), not the **signal spelling** (`-15`, `-s TERM`, `--signal TERM`).
- Governance: MADR-0027's additions-only/frozen-tail rule, MADR-0030's C-9/C-10 gating of any per-PID kill relaxation (which stays in force), and the MADR-0008 routing rule that security-impacting permission changes take the MADR path.
- Minimality (KIS/YAGNI, `home-governance` §9): the smallest change that satisfies the #485 AC corpus — no new ask-tier entries, no kill allow, no wrapper scope creep.

## Considered Options

### Option 1: Enumerated path list (`/usr/bin/kill *`, `/bin/kill *`, `/usr/local/bin/kill *`)

- Pros: no false positives outside the listed absolute paths; trivially reviewable.
- Cons: fails the path-general requirement (C1) — any other prefix (`/sbin/kill`, `busybox kill`, a Nix store path, `/usr/bin/./kill`) stays bypassable, so the fix is cosmetic against an unbounded prefix space; it re-creates the enumeration treadmill MADR-0029 rejected for wrappers.

### Option 2: Path-general whole-value deny `*/kill *` (chosen for R-1)

- Pros: matches every path-qualified spelling in one rule because OpenCode's whole-value wildcard `*` includes `/`; leaves bare `kill <pid>` on the ask tier untouched (no leading `/`), so the checkpoint itself is preserved; deny-only, so any false positive falls in the safe direction.
- Cons: a string-matching control, not a parser — it also matches an unrelated command whose text contains `/kill ` (e.g. reading a file literally named `kill`); path-qualified **wrapper**-to-kill (`/usr/bin/env kill 754`) is not matched, so R-1 is only closed for the direct form.

### Option 3: Keep the signal-prefix deny patterns and document the R-2 friction

- Pros: zero config churn.
- Cons: leaves a hard deny on the *safe* SIGTERM spelling while the equivalent `kill -9 <pid>` merely asks — it teaches users/agents to reach for SIGKILL, which is the opposite of the intended posture, and it contradicts the ask tier's stated purpose (destructive-but-recoverable operations checkpoint).

### Option 4: Target-classified deny block with a signal-range classifier (chosen for R-2)

- Pros: preserves every destructive target class (target `0`, target `-1`, negative process groups, multi-target permutations) and removes the signal-number false positives; expressible in whole-value globs only (no bracket/regex syntax the engine may not support).
- Cons: token-length classification is not available in glob syntax, so one ambiguous shape remains (see the recorded limitation below).

## Decision Outcome

Chosen options: **Option 2 for R-1** and **Option 4 for R-2**, implemented as one deny-tail block replacement in `opencode.jsonc` (tail **86 → 93**): the three MADR-0027 signal-prefix patterns are removed and ten target-classified/path-general patterns land —

`kill 0`, `kill 0 *`, `kill * 0`, `kill * 0 *` (target `0`), `kill -1`, `kill -1 *`, `kill * -1`, `kill * -1 *` (target `-1`), `kill -* -*` (negative process-group targets), `*/kill *` (path-qualified direct kill).

The AC2 corpus is satisfied verbatim for all **31 explicitly enumerated forms** (25 must-DENY, 6 must-ASK): target-`0` and target-`-1` forms (including `kill -- 0`, `kill -- -1`, `kill <pid> -1`, multi-target permutations) and negative process-group targets (`kill -TERM -12345`, `kill -- -12345`) stay **DENY**; single-PID signal forms (`kill <pid>`, `kill -15 <pid>`, `kill <pid> -15`, `kill -s TERM <pid>`, `kill --signal 1 <pid>`, `kill -0 <pid>`) resolve **ASK**. Per the **PO Option-A amendment recorded on #485 (2026-11-22)**, ambiguous single-hyphen negative numeric forms (`kill -12345`, `kill 1234 -12345`) resolve the **conservative ASK checkpoint — never ALLOW** — because whole-value glob syntax cannot express a token-length/range classifier (no regex or quantifier support in the engine matcher); the limitation is explicit and machine-pinned, not a residual deny.

**Doctrine narrowing (C4).** This MADR narrows the MADR-0027/MADR-0024 additions-only/frozen-tail doctrine **solely** for the removal of the two kill false-positive patterns (`kill -1*` signal-prefix over-match and `kill * -1*`); every destructive broadcast/process-group deny is preserved, no existing entry is reordered, and the net posture change is **negative** (a deny surface narrowed toward ASK, plus a new path-general deny). Any future tail removal needs its own MADR on the same footing.

**Preserved invariants (AC6).** No kill allow exists anywhere; bare `kill*` stays the ask-tier checkpoint; no per-PID relaxation is introduced (MADR-0030 C-9/C-10 gating stands, re-submission still requires a form-level PO citation on #482); no agent-level kill rule exists in any spec and the gate-14 canary now makes one a machine failure.

**Machine gates (C3).** Gate 14 (`check_bash_permission_tiers.py`) pins the full AC2 corpus in `TRUTH_TABLE`, the compound controls `true && /usr/bin/kill 754` → deny and `true && kill -15 1234` → ask in `COMPOUND_TRUTH_TABLE`, the `KILL_DENY_PATTERNS` block and its tail position, and a `check_kill_carveout_canary` that rejects any agent allow/ask rule whose `*`-stripped executable head is `kill` (narrow `kill 1234`, globbed `kill*` / `/usr/bin/kill*` / `*/kill*` / `*kill*`, and path-qualified `/usr/bin/kill *` variants included). Agent front-matter is parsed **structurally** as YAML (PyYAML, duplicate keys rejected), so unquoted or single-quoted `permission.bash` keys cannot hide a rule from the canary or from the duplicate-root / undocumented-deviation checks (C3 fix-up, PR #492). Gate 20 (`check_installed_posture_freshness.py`) resolves the shared `KILL_ORDERED_PROBES` (`/usr/bin/kill 754`, `/bin/kill -9 1234`, `kill 0`, `kill -TERM -12345`) against the **ordered** installed rules and requires `deny`, and its deny-count parity pin moves 86 → 93. Only whole-value glob semantics are used — no bracket/regex syntax.

**Live evidence (non-executing).** Installed-engine permission-decision probe on opencode v2.3.2 (installed config = symlink to this tree): `/usr/bin/kill 999999` → `permission.rejected` (deny decision, command never executed), with `curl --version` → `permission.rejected` as the control that the decision layer is active. Static gates prove configuration intent; this probe is the runtime witness.

## Consequences

- **Positive:** the R-1 path-qualified **direct** kill bypass is closed for every prefix in one rule (`/usr/bin/kill 754`, `/bin/kill -9 1234` now deny); the R-2 false positives are removed (`kill -15 <pid>` asks instead of hard-denying); the destructive target classes stay denied and are now pinned per shape, so a future edit that drops a broadcast deny fails the gate; the kill family is covered by the same ordered-resolution and no-agent-carve-out machine controls as the wrapper family.
- **Negative:** the deny tail is **no longer strictly additions-only** — the first removal in its history, justified and bounded to the two false-positive patterns; the tail grows 86 → 93 and every future tail edit must update the gate-14 position/count pin, the truth table and the gate-20 parity canary deliberately; deny-only string matching can produce safe-direction false positives (a command text containing `/kill `).
- **Residual (accepted, Medium — single-user local blast radius; R-1 NOT fully closed):** (a) path-qualified **wrapper**-to-kill (`/usr/bin/env kill 754`), env-var assignment prefixes (`VAR=1 kill 754`) and **non-enumerated executors** remain in the MADR-0029 residual set and are pinned as truth-table **allows** so the limit stays legible; (b) a negative numeric target written as the only hyphen token (`kill 1234 -12345`, `kill -12345`) is textually indistinguishable from a signal number without regex/quantifier support and resolves the **conservative ASK checkpoint — never ALLOW**, per the PO Option-A amendment recorded on #485 (2026-11-22); (c) the unpinned engine (no CI vehicle for a runtime fix). The kill checkpoint therefore remains a **friction boundary and defense-in-depth string filter, NOT a security boundary** against a determined agent.
- **Mitigations:** gate-14 corpus + compound controls + kill carve-out canary; gate-20 ordered resolution and deny-count parity; the non-executing engine probe recorded above; passive re-evaluation on upstream movement per the #362 precedent; any relaxation of the remaining ask friction stays gated on the #482 C-9/C-10 form-level citation (MADR-0030).

## References

- #485 (this change), #482 (audit + security verdict C-9/C-10 gating), #490 (Sprint 36 dispatch marker)
- @cyber-security APPROVE-WITH-CONDITIONS C1–C5, 2026-11-22 (recorded on #485); PR-stage corpus verification + C3/C4/C5 fix-up review on PR #492 (2026-11-22)
- **PO Option-A amendment, 2026-11-22** (recorded on #485): ambiguous single-hyphen negative numeric targets keep the conservative ASK checkpoint — never ALLOW — with the whole-value-glob inexpressibility limitation documented (AC2 amended accordingly; zero `opencode.jsonc` pattern change)
- MADR-0027 (kill-broadcast deny additions, tail 70 → 73), MADR-0029 (wrapper family + path-qualified residual class (b), tail 73 → 86), MADR-0030 (no ask-tier relaxation; C-9/C-10 gating), MADR-0008 (security routing), MADR-0017 (trunk delivery)
- `harness/config-validation/check_bash_permission_tiers.py` (`KILL_DENY_PATTERNS`, `KILL_ORDERED_PROBES`, truth tables, `check_kill_carveout_canary`), `harness/config-validation/check_installed_posture_freshness.py` (gate 20)
