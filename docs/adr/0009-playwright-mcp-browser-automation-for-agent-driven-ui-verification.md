# MADR-0009: Playwright MCP browser automation for agent-driven UI verification

- **Status:** proposed
- **Date:** 2026-10-04
- **Deciders:** @fpittelo, @architect, @cyber-security (review pending per MADR-0008)

## Context

Agent delivery in the HOME portfolio is autonomous up to code production and review, but verifying that a web application actually runs and behaves correctly from a user's perspective still requires manual deployment and manual browsing. For coach-web specifically, the deploy foundation already exists (coach-web ADR-007 three-lane compose topology, `scripts/e2e-preflight.sh` with scoped teardown), yet no agent can open the running UI, exercise user journeys, and sign off. The Product Owner requested dedicated browser-based verification capability for the delivery agents (coach-web epic #133, grilled 2026-10-03/04).

## Decision Drivers

- **Agent autonomy:** the sprint loop must complete deploy → verify → teardown without manual help.
- **Realistic verification:** scripted HTTP checks cannot confirm interactive UI behaviour.
- **Targeted delegation:** only delivery agents (`@developer`, `@devops`) get browser access; gatekeeper and charter agents (`@code-reviewer`, `@scrum-master`, `@coach`) keep read-only/zero-tool postures.
- **Blast-radius containment:** agent container actions must stay scoped to coach-web workloads.
- **KIS/YAGNI (MADR-0003):** minimal capability that satisfies the story; no speculative scope.
- **Swiss nLPD:** no secrets exposed through browser tooling or logs.

## Considered Options

### Option 1: Interactive browser MCP (@playwright/mcp), stdio via npx

- Pros: agents browse interactively (navigate, click, snapshot accessibility tree, read console); snapshot-based operation avoids vision dependence; official Microsoft maintenance; one-time chromium install; directly satisfies the user story.
- Cons: new MCP attack surface (a browser that can reach any URL); interactive sessions are not regression-replayable.

### Option 2: Scripted E2E suite (pytest + Playwright, headless)

- Pros: deterministic, CI-replayable journeys; no new MCP surface.
- Cons: agents never "browse" — does not satisfy the requested interactive verification; framework + test authoring cost up front.

### Option 3: Both, phased

- Pros: autonomy now + regression safety later.
- Cons: exceeds the grilled scope; Phase 2 deferred by PO decision (YAGNI).

## Decision Outcome

Chosen option: **"Option 1 — `@playwright/mcp` as the `BROWSER` MCP server (stdio, npx), enabled, with `BROWSER_*` tools allowed only for `@developer` and `@devops` and denied for all other agents (global baseline + per-agent re-statement, COACH_* defense-in-depth pattern)."** Option 2 was explicitly rejected for now by the Product Owner (grill Q2a); it remains a candidate follow-up if journey regression becomes a pain point.

Container containment is enforced **by convention, not permission rules** (PO decision Q12=B): agents use the per-repo lane wrapper (coach-web `scripts/lane.sh`, fixed `coach-web-*` compose project names, dev/qa lanes only) and existing docker permissions remain unchanged. The lane scope rule is stated in agent-facing workflow docs and enforced through `@code-reviewer` review discipline.

## Consequences

- **Positive:** delivery agents autonomously deploy, browse, verify user journeys, report pass/fail to the PR thread, and tear down their environment; zero new docker permission surface; gatekeeper SoD postures untouched.
- **Negative:** accepted residual risks — (1) nothing technically prevents an agent from issuing raw docker commands against non-coach-web resources (convention-only containment, Q12=B); (2) the Playwright browser can navigate to any URL, not only lane URLs (no origin restriction); (3) interactive journeys are not automatically replayable as regressions.
- **Mitigations:** lane wrapper + preflight scoped teardown as the documented single path; `@code-reviewer` review discipline on PRs touching agent workflows; PR-comment reports make every browser session auditable; human promotion gates (dev → qa → main) unchanged; single-user workstation blast radius (MADR-0004 compensating-control pattern).

## Security Considerations

- **MADR-0008 gate:** new MCP tool integration → `@cyber-security` review against arc42 §8/§11 required BEFORE spec finalization. Verdict: _pending_.
- Expected review focus: unrestricted navigation surface, console/log data exposure (nLPD), interaction between browser session and auth-disabled dev/qa lanes (loopback-only publishing is the primary boundary), and the convention-only docker containment.
