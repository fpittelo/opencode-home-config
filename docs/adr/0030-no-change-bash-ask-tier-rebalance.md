# MADR-0030: No relaxation of the bash ask tier — kill per-pid set not approved

- **Status:** accepted
- **Date:** 2026-11-21
- **Deciders:** @cyber-security, @architect, @fpittelo

## Context

Issue #482 (configuration audit finding F5 / recommendation R6) re-opened the bash **ask tier** as the main source of mid-sprint PO interruption prompts, under the MADR-0027 evidence-first doctrine: no relaxation without per-pattern evidence and a per-pattern `@cyber-security` decision. AC2's direct-observation source was satisfied at creation (PO record, [#482 c.7060745400](https://github.com/fpittelo/opencode-home-config/issues/482#issuecomment-7060745400)); AC1's tally was completed in phase 1 ([#482 c.7061012090](https://github.com/fpittelo/opencode-home-config/issues/482#issuecomment-7061012090)); a single candidate diff — the AC0-endorsed `kill` per-pid digit classes (MADR-0027 C4(b) deferral) — was proposed ([#482 c.7061015915](https://github.com/fpittelo/opencode-home-config/issues/482#issuecomment-7061015915)) and gated on the AC7 per-pattern decision ([#482 c.7061055404](https://github.com/fpittelo/opencode-home-config/issues/482#issuecomment-7061055404)). AC10 defines the no-change outcome: tally plus a short MADR, with **no** `opencode.jsonc`, baseline-pin, truth-table or `arc42/03` diff.

### AC1 tally (observation window: Sprint 30 → 35, 2026-11-15 → 2026-11-21)

Grades: `F` = family-level observation (family observed firing, exact form not recalled); `n/a` = allow-tier entry, cannot prompt. No pattern reached form-level grade `D` — ask prompts are answered in-session and leave no thread trace. Counts are `≥1 (not recalled)` per the PO record: a bounded sample, not a measurement.

| # | `BASELINE_ASK_TIER` pattern | Tier | Observed | Grade | Citation |
| :-- | :--- | :--- | :--- | :--- | :--- |
| 1 | `rm *` | ask | yes | F | #463 c.6894366944; audit #460 §5 |
| 2 | `rm /tmp/opencode/*` | allow | n/a | n/a | MADR-0015 (#320) |
| 3 | `rm -r /tmp/opencode/*` | allow | n/a | n/a | MADR-0015 (#320) |
| 4 | `rm -rf .venv` | allow | n/a | n/a | MADR-0027 (#463) |
| 5 | `rm -rf */.venv` | allow | n/a | n/a | MADR-0027 |
| 6 | `rm -rf __pycache__` | allow | n/a | n/a | MADR-0027 |
| 7 | `rm -rf */__pycache__` | allow | n/a | n/a | MADR-0027 |
| 8 | `rm -rf .pytest_cache` | allow | n/a | n/a | MADR-0027 |
| 9 | `rm -rf */.pytest_cache` | allow | n/a | n/a | MADR-0027 |
| 10 | `pip install*` | ask | yes | F | PO record c.7060745400; #463 c.6894366944 |
| 11 | `pip3 install*` | ask | yes (family) | F | PO record c.7060745400; #308 c.6232755800 |
| 12 | `uv pip install*` | ask | yes | F | #463 c.6894366944; PO record c.7060745400 |
| 13 | `*-m pip install*` | ask | yes (family) | F | #308 c.6232755800; PO record c.7060745400 |
| 14 | `npm install -g*` | ask | yes | F | PO record c.7060745400 only |
| 15 | `npm i -g*` | ask | yes (family) | F | PO record c.7060745400 only |
| 16 | `kill*` | ask | yes | F | #463 c.6894366944; PO record c.7060745400 |
| 17 | `pkill*` | ask | yes (family) | F | PO record c.7060745400; AC0 c.6894867168 |
| 18 | `killall*` | ask | yes (family) | F | PO record c.7060745400; AC0 c.6894867168 |
| 19 | `chmod *` | ask | yes | F | PO record c.7060745400 only |
| 20 | `chmod 600 *` | allow | n/a | n/a | MADR-0015 (#320) |
| 21 | `chmod 700 *` | allow | n/a | n/a | MADR-0015 (#320) |
| 22 | `chown *` | ask | yes (family) | F | PO record c.7060745400 only |
| 23 | `systemctl*` | ask | yes | F | PO record c.7060745400 only |

All 23 pinned entries accounted for; 0 `unevidenced`. The tally supplies **family-level** evidence only: it does not identify the exact command shape behind any prompt.

## Decision Drivers

- **Evidence-first relaxation (MADR-0027 C4(b)).** A deferral recorded as form-level may only be lifted by form-level evidence; a family-level observation is the same grade already deemed insufficient.
- **Reachability of the proposed classes.** On the reference host PIDs 1–99 are system-owned; the lowest user-owned PID measured is 358, so the 1- and 2-digit classes grant zero legitimate relief and add pure attack surface.
- **Exposure is unconditional, relief is not.** An unprompted SIGTERM to a user-owned PID is available to every execution regardless of whether the prompt that motivated the change would have been suppressed.
- **KIS & YAGNI (#180, AC10).** An unproven-benefit change dragging config + baseline pins + truth table + canary + `arc42` churn is exactly the cost AC10 exists to avoid.
- **Additions-only deny doctrine (MADR-0024/0029).** Ask-tier relaxation cannot touch the deny tail; the over-broad `kill -1*` deny is therefore out of scope here.

## Considered Options

### Option 1: Relax the AC0-endorsed `kill` per-pid digit classes (P1–P7)

- Pros: the pattern set was already reviewed verbatim (AC0 C2) and is mechanically correct (anchored digit classes; broadcast forms stay denied); it is the only candidate with zero review delta.
- Cons: the evidence does not discriminate which `kill` sub-form fired; if the prompts were `kill -9 <pid>`, `kill -s TERM <pid>`, `pkill -f …` or `killall …`, no class matches and the prompts persist unchanged while exposure grows; P1/P2 are unreachable for a uid-1000 agent.

### Option 2: No configuration change — AC10 outcome

- Pros: zero unproven surface; no pin/truth-table/canary/doc churn; keeps the ask tier honest as a friction boundary; preserves the re-submission path at the cost of one citation.
- Cons: the `kill` prompt friction persists until form-level evidence is recorded (residual R-3).

### Option 3: Relax `chmod` / `chown` / `systemctl` subsets instead

- Pros: these families also fired.
- Cons: no form-level evidence, and each has a recorded prior rejection (`chmod +x *`, `chmod 755 *` — MADR-0015; `chown`/`systemctl` "privilege-adjacent — stay ask" — AC0 c.6894867168). Proposing them on a form guess is speculative scope and contradicts a recorded decision without new rationale.

## Decision Outcome

Chosen option: **"No configuration change — AC10 outcome"**, because the AC7 per-pattern ruling yields **zero approvable lines**: only `APPROVE` admits a line, and `REJECT` and `no-evidence` both exclude it.

### Per-pattern decision table (AC7, recorded at [#482 c.7061055404](https://github.com/fpittelo/opencode-home-config/issues/482#issuecomment-7061055404))

| # | Pattern | Decision | Basis |
| :-- | :--- | :--- | :--- |
| P1 | `kill [0-9]` | **REJECT — drop** | PIDs 1–9 system-owned → EPERM for uid 1000; lowest user-owned PID 358 |
| P2 | `kill [0-9][0-9]` | **REJECT — drop** | PIDs 10–99 entirely system-owned; re-proposable only with a named 2-digit user-owned target |
| P3–P7 | `kill [0-9]{3..7}` | **no-evidence → not approved** | Shape pre-endorsed (AC0 C2) but the tally grades `kill*` `F`; the PO row covers `kill*`/`pkill*`/`killall*` as one family, so the observation cannot discriminate the sub-form |
| P8a | pointer comment line | **REJECT — drop** | Conditioned on a changed pattern block; under AC10 the MADR index entry carries the record |
| P8b | pip/pip3/`-m pip`/uv-pip, `npm -g`, `chmod *`, `chown *`, `systemctl*`, `pkill*`, `killall*`, `kill*` ask line, `rm *` + carve-outs, deny tail (86) | **APPROVE — no change** | Recorded rejections stand (MADR-0015/0027, AC0); deny tail byte-identical, last-and-winning |

### Q1 ruling — family-level evidence is not sufficient

Family-level observation cannot discriminate among the three `kill` sub-forms; two of the three (`pkill`, `killall`) stay ask under any proposal, so the same observation is equally consistent with those firing alone. Exposure is unconditional, relief unproven. MADR-0027 C4(b)'s deferral was form-level, and grade-`F` evidence is the same grade already deemed insufficient. **The unlock is cheap:** one form-level citation naming the fired prompt as plain single-PID `kill <digits>` flips P3–P7 to APPROVE-WITH-CONDITIONS on re-submission (P1/P2 stay dropped), per conditions **C-9** (form-level citation recorded on the issue before dispatch) and **C-10** (re-submitted diff contains only P3–P7, no other family relaxed on family-level evidence) at #482.

**Decision statement: no configuration change.** `opencode.jsonc` is untouched; `BASELINE_*` pins, the truth table, the placement canary and `arc42/03` are untouched (AC10 no-churn clause). The deliverable is this record plus the AC1 tally.

## Consequences

- **Positive:** the ask tier stays a single, coherent guard with no unproven relaxation; zero config/pin/test/doc churn; the reviewable path to the `kill` relief is preserved and now cheaper to trigger (one citation).
- **Negative — R-1 (severity::medium):** the `kill`-family checkpoint is **path-bypassable** — `/usr/bin/kill 754` and `/bin/kill -9 1234` resolve **allow** on today's trunk (bare-prefix patterns; the `*` head catches path-qualified spellings). This is the `kill`-specific instance of the MADR-0029 residual (b) class and a **pre-existing** condition, not introduced here.
- **Negative — R-2 (severity::low):** the deny tail over-matches signal-number forms — `kill -1*` matches `kill -15 <pid>` and `kill * -1*` matches `kill <pid> -15`, so SIGTERM-by-number is hard-denied while `kill <pid>` is only ask. Friction in the safe direction; the fix is a deny-tail edit, which AC3 forbids in #482.
- **Negative — R-3 (severity::low):** the form-level evidence gap persists for all ask families; future proposals must not treat family-level observation as form-level evidence.
- **Mitigations:** R-1 and R-2 are owned by follow-up issue **#485** (which also owns the `arc42/03` §3 residual row — no `arc42` diff here per AC10). Re-submission of P3–P7 is available at any time under C-9/C-10 without a new design; if it lands, the accepted residuals R-4 (daemon self-kill, framed as a checkpoint-surface change — never a capability increase) and R-5 (flag/multi-target forms remain ask) become due.
