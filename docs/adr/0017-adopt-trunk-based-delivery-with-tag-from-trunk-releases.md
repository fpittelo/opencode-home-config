# MADR-0017: Adopt trunk-based delivery with tag-from-trunk releases

- **Status:** accepted
- **Date:** 2026-10-17
- **Deciders:** @fpittelo (PO approval 2026-10-17 — "yes, please … adopt a trunk+tag strategy"), @architect (author)

## Context

The portfolio delivery lifecycle (home-governance §5) mandates three persistent branches — `dev` (integration), `qa` (staging), `main` (production) — with feature branches squash-merging into `dev` and merge-commit promotions `dev → qa → main` (MADR-0012). The demand-driven sprint cadence (PO decision A, 2026-10-04, #216) makes releases frequent — three releases in six days at v1.20.0–v1.22.0 — so the per-release promotion ceremony recurs constantly.

MADR-0012 already removed the worst symptom (the reconcile-PR class) by mandating merge-commit promotions, but every release still costs **two mechanical promotion PRs** (branch, CI, review, merge, board hygiene) that add no decision: the only real gate is the single PO approval. The `qa` stage validates little for single-user repositories — for `opencode-home-config` the deployed artifact is a symlink farm into the PO's own workstation (VIDAR); the PO's machine *is* the staging environment (MADR-0012 §Context).

A portfolio study (2026-10-17, PO request) compared this 3-branch model against **trunk-based development (TBD)**: a single trunk (`main`) receiving small, frequent, gated changes; releases cut from the trunk as semantic tags + GitHub Releases; no long-lived integration or staging branches. TBD is the delivery model empirically correlated with high performance in the DORA/Accelerate research, and the squad already behaves trunk-like between releases — feature branches off `dev`, squash in, promote. The 3-branch model effectively appends two copy steps after the real integration point.

This decision supersedes the promotion protocol of MADR-0012 (promotions no longer exist) and requires a portfolio-standard update (`fpittelo/project-template` `STANDARD.md` §2, MADR-0007).

## Decision Drivers

- **PO friction (MADR-0008):** the PO is the bottleneck resource; mechanical promotion ceremony consumes the delivery loop without adding a decision.
- **KIS & YAGNI (home-governance §9):** the smallest mechanism satisfying the delivery fabric (isolation, zero-warning CI, review, traceability) wins; speculative machinery (release trains, parallel-version release branches) is rejected.
- **Demand-driven cadence (#216):** release cost must be near-zero so releases can happen on demand, same-day.
- **Single-PO reality:** no multi-tenant production surface; WIP=1; mandatory `@code-reviewer` approval + zero-warning CI already protect the integration point.
- **Traceability & rollback:** every release must remain fully auditable (PRs, CI runs, reviews, tags) and reversible.
- **Portfolio consistency:** `STANDARD.md` §2 codifies the 3-branch model as non-negotiable — adopting TBD requires a standard update, not a silent deviation.

## Considered Options

### Option 1: Trunk + tag-from-trunk releases (single trunk `main`, releases = tags)

- Pros: release ceremony drops from 2 PRs to **0 PRs** (approve + tag); the branch-divergence disease is eliminated by construction (squash-into-trunk can never diverge from itself); one integration point, one CI trigger surface, simpler branch protection; releases as cheap as the demand-driven cadence wants; every quality gate that matters (zero-warning CI, formal review, PO release approval) is retained.
- Cons: breaks the portfolio non-negotiable (`STANDARD.md` §2) — requires a standard update; loses the `qa` refuge (rollback weakens from "revert `qa`" to "revert commit / redeploy previous tag"); the PO approval gate needs a new anchor (the release action instead of promotion PRs); "broken trunk" risk, mitigated by the unchanged PR gate + revert-first policy.

### Option 2: Trunk + short-lived release branches (`release/x.y.z` cut at release time)

- Pros: stabilization isolated from trunk; supports parallel-version maintenance.
- Cons: earns its cost only when stabilization outlasts a PR cycle or multiple versions must be maintained in parallel — neither holds for a single-PO portfolio that patches forward within hours (YAGNI); reintroduces per-release branch ceremony.

### Option 3: Status quo — three persistent branches with merge-commit promotions (MADR-0012)

- Pros: zero governance change; proven (reconcile class retired, 2-PR ceremony).
- Cons: permanent 2-PR mechanical tax per release, recurring at demand-driven frequency forever; `qa` validates little for single-user repos; keeps two copy steps after the real integration point.

## Decision Outcome

Chosen option: **"Option 1 — Trunk + tag-from-trunk releases"**, because it deletes the entire promotion ceremony while retaining every quality gate that matters (zero-warning CI, formal `@code-reviewer` approval, single PO release approval), and the risks it introduces (broken trunk, weaker `qa` refuge) are already mitigated by the existing WIP=1, small-diff, gated-PR fabric. Options 2 and 3 pay ongoing ceremony for protection the portfolio does not need.

**PO decision (@fpittelo, 2026-10-17):** adopted — "yes, please. Do not forget to update the governance, the agents and their skill in the process to adopt a trunk+tag strategy."

**Normative lifecycle after this decision (SSOT: `home-governance` §5):**

1. **Single persistent trunk:** `main`. The `dev` and `qa` branches are retired at cutover (follow-up issue #332).
2. **Feature-branch isolation (unchanged):** all work on `feature|fix|chore/<issue-#>-<slug>` branches cut from `main`; direct pushes to `main` forbidden; PRs target `main` ONLY; squash merge (`merge_method: "squash"`).
3. **Zero-tolerance gate (unchanged):** 100% clean CI (0 warnings, 0 failures) + formal `@code-reviewer` approval on every PR into `main`.
4. **Release = tag-from-trunk:** one explicit `@fpittelo` approval per release; `@devops` then tags `vX.Y.Z` on `main` and publishes the GitHub Release via native `gh release create` (MADR-0020, superseding MADR-0016's server mechanism). No promotion PRs exist.
5. **Staging validation:** performed on the release candidate *before* tagging — PO's own machine for config repos; deploy-the-tagged-artifact for repos with real staging environments (deploy promotion replaces branch promotion).
6. **Rollback:** `git revert` the squash commit on trunk, or redeploy the previous tag. **Hotfix:** branch from the released tag → PR to `main` → patch tag.

**Implementation is out of scope for this ADR** — it lands via follow-up issues: cutover execution for this repository (#332: branch protection, `dev`/`qa` deletion, workflow triggers) and the portfolio-standard update (`fpittelo/project-template` #1: `STANDARD.md` §2).

## Consequences

- **Positive:** release cost collapses to "approve + tag"; the promotion-PR class and the branch-divergence disease are eliminated by construction; one CI trigger surface; lead time shrinks to the cadence the PO actually wants; DORA-aligned delivery model.
- **Negative:** `STANDARD.md` §2 must be rewritten (governance change, not a repo-local tweak); the `qa` staging refuge is lost (rollback now = revert-on-trunk or previous tag); the PO approval anchor moves from promotion PRs to the release action; a red trunk is momentarily public (mitigated by the unchanged PR gate).
- **Mitigations:** revert-first policy (never fix-forward on a red trunk); trunk branch protection identical to today's `dev` protection (PR + green CI + reviewer); release approval recorded on the sprint marker or release issue before `@devops` tags; repos with genuine external users may retain a documented 3-branch or release-branch exception via the updated standard.
