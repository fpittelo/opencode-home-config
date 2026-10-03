# MADR-0007: Portfolio standardization — FPITTELO PROJECT TEMPLATE (portfolio standard v1)

- **Status:** accepted
- **Date:** 2026-10-03
- **Deciders:** @fpittelo (PO directive, Sprint 10 priority 1)

## Context

The PO is alone across the repositories under https://github.com/fpittelo/, and governance is
heterogeneous: a 2026-10-03 survey found only `opencode-home-config` fully mature (3-branch
lifecycle, zero-warning CI, SCRUM board, MADR workflow, harness gates), `coach` partially
governed, and the remaining repositories pre-governance. Every project currently re-derives its
scaffold, pipeline, and process ad hoc, and agents working across repositories have no portable
statement of the standard to apply.

The HOME SCRUM governance itself is codified in this repository (home-governance skill,
MADR-0003 proportionate gates, #180 KIS & YAGNI standing principles), but nothing makes it
portable to the rest of the portfolio.

## Decision Drivers

- **Single-PO scalability:** one person cannot maintain 11 bespoke governance models; the
  standard must be defined once and applied everywhere.
- **Agent portability:** all agents must be able to discover and apply the same standard in any
  fpittelo repository — the standard must live where agents read it.
- **Reuse the proven reference:** `opencode-home-config` is the mature implementation; the
  standard should distill it, not reinvent it (KIS).
- **KIS/YAGNI (MADR-0003, #180):** minimal mechanism — a template repository and a normative
  standard document; no automation scripts, no universal CI matrix (explicitly out of scope).

## Considered Options

### Option 1: Status quo — per-project governance

- Pros: zero migration effort; each project stays as it is.
- Cons: heterogeneity persists; agents must re-learn governance per repository; the PO cannot
  enforce a consistent baseline across the portfolio.

### Option 2: GitHub template repository + FPITTELO PROJECT STANDARD v1 (chosen)

- Pros: new projects scaffold from `fpittelo/project-template` with the standard built in
  (structure, 3-branch lifecycle, zero-warning CI with diff-scoped gitleaks, SCRUM label
  taxonomy, MADR workflow, KIS & YAGNI, security baseline); `STANDARD.md` is the portfolio
  SSOT; the home-governance skill references it so agents apply it everywhere; existing
  projects retrofit incrementally (pilot = `coach`).
- Cons: existing repositories need a retrofit backlog (incremental, not big-bang); the
  template-repository flag must be set manually (MCP gap — PO one-click step).

### Option 3: Central governance repo referenced by link only (no template scaffold)

- Pros: no per-project scaffold churn.
- Cons: projects still start from empty repositories and drift immediately; the GitHub-native
  "Use this template" onboarding mechanism goes unused; agents still lack a concrete scaffold
  to copy.

## Decision Outcome

Chosen option: **Option 2**, delivered by issue #190:

1. **Mechanism:** `fpittelo/project-template` (private GitHub template repository) carries the
   scaffold: lean README pattern (presentation + one mermaid schema, all docs in `docs/`),
   `STANDARD.md` (FPITTELO PROJECT STANDARD v1 — 7 normative areas: repo structure, 3-branch
   lifecycle, proportionate zero-warning CI with diff-scoped gitleaks, SCRUM label taxonomy,
   MADR ADR workflow, KIS & YAGNI, security baseline), arc42 skeleton, CHANGELOG /
   CONTRIBUTING / LICENSE, generic `ci.yml`, PR template, and the ported docs-validation
   harness.
2. **Adoption path:** new projects scaffold from the template; existing projects retrofit
   incrementally — pilot = `coach` (separate issue).
3. **Agent wiring:** `skills/home-governance/SKILL.md` gains a "Portfolio Standard" section
   pointing at `fpittelo/project-template` / `STANDARD.md` as the portfolio SSOT.

## Consequences

- **Positive:** a single SSOT for project governance across the portfolio; every new project
  starts conforming by construction; agents apply one standard everywhere; the proven
  home-config harness and CI pattern propagate as-is.
- **Negative:** a retrofit backlog exists for the non-reference repositories (incremental
  adoption, pilot `coach`); the template-repository flag is a manual PO step (GitHub MCP
  cannot set it).
- **Neutral:** the template repository itself is main-only (meta-repo bootstrap exception,
  documented in its README); projects created from it follow the full 3-branch lifecycle.
