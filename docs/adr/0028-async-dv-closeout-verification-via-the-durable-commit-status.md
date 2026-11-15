# MADR-0028: Async DV closeout verification via the durable commit status

- **Status:** accepted-pending-PO
- **Date:** 2026-11-15
- **Deciders:** @architect (decision author, #464 dispatch), @fpittelo (PO — AC4 sign-off pending on #464), @devops (file work)

> **AC4 status gate (hard):** this record's status flips from
> `accepted-pending-PO` to `accepted` ONLY when @fpittelo posts an explicit
> sign-off comment on #464 approving the amended closeout semantics (the
> change modifies a #448-derived commitment — Rule-5-adjacent governance
> change). @scrum-master verifies the sign-off comment exists at closeout.
> This PR must not be merged before that comment exists.

## Context

Per-issue DoD closeout currently **waits for Deep Validation** (~2.5 min full-history run) on the trunk head before the next dispatch — throttling the sequential WIP=1 loop (audit #460 R1: loop latency). The audit's literal remedy — moving DV to a weekly cron + pre-release-only cadence — was **REJECTED at grooming (binding)**: it re-widens the detection window that incident #448's protective controls closed (#449: the durable deletion-evident `deep-validation` commit status + the DoD trunk-head verification requirement; the #448 incident rode a 22-day detection gap and 8 unescalated red DV heads).

Measured latency: DV full-history runs complete in ~2.5 min (run evidence: 43701320767 2m31s, 43703690037 2m30s, 43710215267) — per-issue, that is dead loop time inside WIP=1.

## Decision Drivers

- Detection latency must stay unchanged (every trunk push keeps its full DV run — #448 provenance).
- Loop throughput: WIP=1 + sequential dispatch means closeout wait time is pure throttle.
- Fail-closed posture: silence or red must never let the loop advance blindly.
- The strengthened #449 commitment is **amended, not silently weakened** — the change must be explicit and PO-signed.

## Considered Options

### Option 1: DV → weekly cron + pre-release only (the audit's literal remedy)

- Pros: removes the closeout wait entirely.
- Cons: re-widens the detection window on trunk pushes — the exact regression #448's controls exist to prevent. **Rejected at grooming (binding).**

### Option 2: Async closeout verification via the durable commit status (CHOSEN)

- Pros: detection latency unchanged (DV still runs on every trunk push); closeout verification reads the durable deletion-evident status instead of waiting for a fresh run; the next dispatch is unblocked; red DV pauses the loop (fail-closed).
- Cons: a trunk head whose DV status is momentarily *pending* is verified only before the sprint closeout/release gate at the latest — bounded residual (see Consequences).

## Decision Outcome

Chosen option: **"Option 2 — async closeout verification via the durable commit status"**, because it restores loop throughput while keeping detection latency and the fail-closed posture unchanged.

- **Decision:** keep DV on **every trunk push**; make closeout verification **ASYNC**. DoD's "Deep Validation green on the exact trunk head" is verified via the **durable deletion-evident `deep-validation` commit status** on the merge commit (posted minutes after merge by the DV workflow, #449 AC2b); **the next dispatch is NOT blocked on it**; **a RED DV on trunk PAUSES new dispatches (fail-closed)** until green.
- **What is preserved vs amended:**

| Aspect | State under MADR-0028 |
| :--- | :--- |
| DV on every trunk push | **PRESERVED verbatim** (detection latency unchanged) |
| The durable `deep-validation` commit status mechanism (#449 AC2b) | **PRESERVED verbatim** (it becomes the verification record) |
| DoD's "DV green on the exact trunk head" requirement | **PRESERVED** — the status is run-anchored to that exact sha |
| Closeout *blocking* semantics (wait for the DV run before the next dispatch) | **AMENDED** — verification is async via the status; the next dispatch is not blocked |
| RED DV on trunk | **NEW fail-closed rule** — pauses new dispatches until green |
| Release gate (Rule 5 pre-tag: DV green on the exact tagged sha) | **UNCHANGED** — the release prerequisite is unaffected |
| #440/#448/#449 provenance lineage | **CITED explicitly** (the strengthened commitment is amended, not silently weakened) |

## Consequences

- **Positive:** loop throughput restored (closeout no longer waits ~2.5 min per issue); detection latency unchanged; the verification record is the deletion-evident status (stronger against the #449 evidence-removal class than a transient run view).
- **Negative:** a trunk head whose DV status is momentarily *pending* is verified before the sprint closeout/release gate at the latest (bounded residual); scrum-master carries a new operational duty (red-DV-pauses-dispatch) from the moment this lands.
- **Mitigations:** the durable status is posted minutes after merge (DV runs ~2.5 min); red DV pauses the loop fail-closed; Rule-5 pre-tag verification is unchanged.

## References

- #464 (this change), #460 (audit R1), #448 (incident provenance), #449 (durable status + trunk-head requirement), #440 (Sprint 29 retro addendum lineage)
- `skills/home-governance/SKILL.md` §7 criterion 3, `skills/github-scrum-board/SKILL.md` §5 template, `docs/architecture/arc42/03-cross-cutting-and-security.md` §1.2 (the amended surfaces)
- AC4 sign-off: @fpittelo comment on #464 (required before merge; status flips to `accepted`)
