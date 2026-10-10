# MADR-0012: Promotion topology — eliminate per-release reconcile PRs

- **Status:** accepted
- **Date:** 2026-10-10
- **Deciders:** @fpittelo (PO approval 2026-10-10 — Option 2), @architect (author)

## Context

Every release of this repository currently costs **four pull requests** instead of two:
a reconcile PR (`qa ← dev`), the staging promotion (`dev → qa`), a second reconcile PR
(`main ← qa`), and the production promotion (`qa → main`). The last three releases each
paid this tax — v1.20.0 (#238–#241), v1.21.0 (#246–#249), v1.22.0 (#267–#270) — and the
reconcile PRs exist purely to repair branch topology: because feature work lands in `dev`
via **squash merges**, the `dev` history is a chain of squash commits while `qa`/`main`
carry their own merge history. The trees diverge, the promotion PRs cannot merge cleanly,
and an "AI-1 Option A" reconcile PR (byte-identical tree restore) must land first.

The friction is amplified by the demand-driven sprint cadence (#216): three releases in
six days (2026-10-04 → 2026-10-10) means the four-PR ceremony runs constantly, and each
reconcile PR is a zero-thought mechanical PR that still consumes the full loop (branch,
CI, review, merge, board hygiene).

This is a **single-PO configuration repository**: the deployed artifact is a symlink farm
into `~/.config/opencode/` on the PO's own workstation (VIDAR), the only consumer of `qa`
is the PO's own staging check, and there is no multi-tenant production surface.

## Decision Drivers

- **PO friction (MADR-0008):** the PO is the bottleneck resource; mechanical reconcile
  ceremony consumes the delivery loop without adding a decision.
- **KIS & YAGNI (home-governance §9):** the smallest mechanism that satisfies the
  delivery fabric (3-branch isolation, zero-warning CI, review, traceability) wins.
- **Portfolio consistency:** `fpittelo/project-template` `STANDARD.md` §2 codifies the
  3-branch model as **non-negotiable** for every project; a deviation for this repo would
  require a template-standard update (flagged per AC2 if chosen).
- **Rollback & staging validation:** `qa` remains the pre-production refuge; losing it
  must be justified by what it actually validates for a config repo.
- **Traceability:** every release must remain fully auditable (PRs, CI runs, reviews).

## Considered Options

### Option 1: Drop `qa` for this repo (two-branch `dev → main` + tag)

- Pros: halves the promotion ceremony (2 PRs → 1 per release); eliminates the `qa ← dev`
  reconcile class entirely; the live `~/.config/opencode` profile is de-facto staging —
  the PO validates on his own machine before tagging; CI runs on the `main` promotion PR
  exactly as it does on `qa` today.
- Cons: **contradicts `STANDARD.md` §2 ("exactly three persistent branches",
  non-negotiable)** — requires a portfolio-standard update and a documented exception for
  this repo; loses the formal `qa` CI gate before `main` (mitigated: the `main` PR runs
  the identical gate); rollback story weakens from "revert `qa`" to "git revert / previous
  tag on `main`"; sets a precedent that other portfolio repos may cite to drop `qa` even
  where staging genuinely matters.

### Option 2: Retain three branches — promote with merge commits, never squash

- Pros: **eliminates the reconcile-PR class by construction** — a `dev → qa` merge commit
  makes the `qa` tree byte-identical to `dev` (and `qa → main` likewise), so the next
  promotion merges cleanly with zero conflicts; ceremony drops from 4 PRs to 2 per
  release; **no change to the portfolio standard** (STANDARD.md §2 constrains merge
  *destinations*, not promotion *merge method*); `qa`-stage validation and the rollback
  refuge are retained; traceability unchanged (promotion PRs + CI runs still exist).
- Cons: promotion merges add merge commits to `qa`/`main` history (cosmetic noise);
  branch protection on `qa`/`main` must allow merge commits (already the case — the
  reconcile PRs merged as squashes, but merge is not blocked); saves one fewer PR than
  Option 1.

### Option 3: Status quo (squash promotions + per-release reconcile PRs)

- Pros: zero change; topology repairs are proven (three releases' worth of AI-1 Option A
  evidence).
- Cons: permanent 4-PR ceremony per release; every reconcile PR is mechanical, unskilled
  work that still pays the full loop tax (branch, CI, review, merge); scales badly with
  the demand-driven cadence (#216) — the tax recurs at every release, forever.

## Decision Outcome

Chosen option: "Option 2 — Retain three branches, promote with merge commits, never
squash", because it eliminates the actual pain (the reconcile-PR class) by construction
while preserving the portfolio-standard 3-branch model, `qa`-stage validation, and the
rollback refuge — the maximum friction removal for the minimum governance change
(KIS & YAGNI). Option 1 saves one additional PR but breaks a portfolio-non-negotiable
standard for a single-user config repo; that trade is not worth a standard divergence.

**PO decision (@fpittelo, 2026-10-10):** Option 2 approved — "Of course I will follow
your recommendation. So, option 2."

**Promotion protocol after this decision:** feature work continues to squash-merge into
`dev` (unchanged); promotions `dev → qa` and `qa → main` are executed as **merge-commit
PRs (never squash)**, under the single PO release approval (home-governance Rule 5);
reconcile PRs become unnecessary and are retired.

**Implementation is out of scope for this spike** — it lands via a separate follow-up
issue (branch-protection/merge-method verification + governance wording updates).

## Consequences

- **Positive:** release ceremony drops from 4 PRs to 2; the reconcile-PR class
  (AI-1 Option A) is retired; `qa`/`main` trees stay byte-identical to their source by
  construction; zero portfolio-standard impact; PO approval protocol unchanged (one
  approval per release, Rule 5).
- **Negative:** `qa`/`main` histories accumulate merge commits (cosmetic); the promotion
  merge method is now a governed invariant that must be respected by every promoting
  agent — a squash promotion would reintroduce the divergence.
- **Mitigations:** codify "promotions merge, never squash" in `home-governance` §5,
  `github-scrum-board`, and `release-automation` (follow-up issue per AC5); verify
  branch-protection merge-method settings during implementation; the zero-warning CI gate
  continues to run on every promotion PR, so a bad merge method fails visibly in review.
