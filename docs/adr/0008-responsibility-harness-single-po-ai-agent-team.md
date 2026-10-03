# MADR-0008: Responsibility harness — single PO, AI-agent SCRUM team

- **Status:** accepted
- **Date:** 2026-10-03
- **Deciders:** @fpittelo (PO directive, Sprint 11 priority 1)

## Context

The HOME SCRUM Team is a **single Product Owner (@fpittelo) leading a SCRUM team composed
entirely of AI agents** (@architect, @scrum-master, @developer, @code-reviewer, @devops,
@cyber-security). Delivery into `dev` is already autonomous (3-branch lifecycle, zero-warning
CI, MADR workflow), but the PO still absorbs friction that does not genuinely need him:

- **PO spot-checks:** runtime acceptance criteria are verified by the PO re-opening fresh
  sessions to spot-check agent work — manual, repetitive, and the largest recurring tax.
- **Per-leg approvals:** promotion approvals are requested separately for `dev` → `qa` and
  `qa` → `main`, doubling what is in practice one decision per release.
- **Ad-hoc security engagement:** security review depends on informal routing; designs with
  security impact can reach review without a threat-model pass, and guardrails are written as
  prose rather than as implementable CI requirements.

The collaboration duties that would remove this friction exist in the agent specs only
implicitly. They must be made explicit, symmetric, and PO-free.

## Decision Drivers

- **Single-PO scalability:** the PO is the bottleneck resource; every gate that does not
  genuinely require him must be removed from his loop.
- **Security chain strength:** removing PO friction must not weaken security — the four
  quadrants route security duties agent-to-agent so the chain gets stronger, not thinner.
- **Sensible enforcement:** practices follow the artifact (TDD for code, not for config/docs);
  no blanket rules, no new ceremony (KIS/YAGNI, MADR-0003, #180).
- **Verifiable autonomy:** autonomy is verified by evidence agents post themselves, not by PO
  presence (precedent: Sprint 09 model probe).

## Considered Options

### Option 1: Status quo — PO in every loop

- Pros: the PO sees everything directly.
- Cons: the PO is the throughput bottleneck; fresh-session spot-checks do not scale; security
  routing stays ad hoc; per-leg approvals double a single decision.

### Option 2: Four-quadrant responsibility harness + PO Gate Inventory (chosen)

- Pros: every collaboration arrow is agent-to-agent (the PO is in none of the four quadrants);
  the PO's remaining gates are explicit and closed (the inventory); runtime acceptance criteria
  are verified by agent probes posting evidence, with PO intervention only on failure.
- Cons: one-shot documentation cost (duty blocks in four agent specs, harness documented as a
  cross-cutting concept); trust shifts from PO presence to posted evidence.

### Option 3: Add a PO approval gate to each quadrant

- Pros: maximum PO oversight.
- Cons: directly contradicts the goal — reintroduces the bottleneck the harness exists to
  remove; violates KIS/YAGNI (#180).

## Decision Outcome

Chosen option: **Option 2**, delivered by issue #194.

### 1. The four-quadrant responsibility harness

```
┌────────────────┐    Review Security Impact     ┌────────────────┐
│   Architect    │ ◄───────────────────────────► │ Cyber-Security │
│                │    arc42 Sec 8 & Sec 11       │                │
└───────┬────────┘                               └───────┬────────┘
        │                                                │
        │ MADRs & Specs                                  │ STRIDE & Guardrails
        ▼                                                ▼
┌────────────────┐    Static/Diff Audits         ┌────────────────┐
│ Code-Reviewer  │ ◄───────────────────────────► │ DevOps / CI-CD │
│                │    CVE & Secret Gates         │                │
└────────────────┘                               └────────────────┘
```

Every arrow is an **agent-to-agent handoff** — the PO is in the loop for none of the four
quadrants:

- **Architect ↔ Cyber-Security:** designs with security impact (new MCP tools, API
  integrations, permission changes, auth flows) are reviewed by @cyber-security against
  arc42 §8 (cross-cutting security) and §11 (technical risks) **before spec finalization**.
- **Architect → Code-Reviewer:** MADRs and specifications are handed to @code-reviewer as the
  review baseline.
- **Cyber-Security → DevOps:** STRIDE threat models and guardrail specifications are delivered
  to @devops as **implementable CI requirements** (gates, not prose).
- **Code-Reviewer ↔ DevOps:** every review verifies static/diff audit results — CVE and secret
  gate evidence; gate gaps are coordinated with @devops.

### 2. Sensible-enforcement mapping

| Practice | Scope |
| :--- | :--- |
| TDD (proportionate) | Mandatory for code projects (coach, kratos, Tyche, future template scaffolds); N/A for config/docs repos (no production code) — the practice follows the artifact, not a blanket rule |
| arc42 §8/§11 security routing | Mandatory for new MCP tools, API integrations, permission changes, auth flows |
| KIS & YAGNI | Universal (#180) |
| SCRUM / MADR / arc42 | Enforced by the existing loop + gates — no new ceremony |

### 3. PO Gate Inventory (closed list)

The explicit, closed list of what still requires @fpittelo — **everything else is autonomous**:

- **(a) Promotion approvals** `dev` → `qa` → `main` — **one approval per release covers both
  legs** (codifies the "please, full promotion" practice).
- **(b) Release publication.**
- **(c) Milestone lifecycle** (upstream-blocked).
- **(d) Ask-tier bash checkpoints** (MADR-0004).
- **(e) Reviewer access on new private repos:** grant @devfpittelo read access (or make the
  repository public) at creation time — the SoD reviewer otherwise gets 404 (Sprint 10 finding).

### 4. Agent-probe verification pattern

Runtime acceptance criteria are verified by **agent probes** posting evidence to the issue
(precedent: Sprint 09 model probe — @scrum-master/@devops quoted their own environment blocks);
the PO intervenes only on failure. This **replaces "PO fresh-session spot-check" as the default
AC pattern**.

## Consequences

- **Positive:** a stronger security chain (architect↔cyber-security routing, CVE/secret gate
  ownership) without PO bottlenecks; the PO's remaining gates are explicit and closed; runtime
  verification scales with the team instead of with the PO's availability.
- **Negative:** trust shifts from PO presence to posted evidence — a failed probe surfaces only
  after the fact (mitigated by the PO-intervenes-on-failure rule); the harness must be kept in
  sync across the four agent specs, arc42 §8, and the home-governance skill.
- **Neutral:** upstream candidates noted, no code changes in this decision — the GitHub MCP
  comment-tool quirk and the label-create tooling gap are recorded as upstream candidates for
  https://github.com/github/github-mcp-server. Closeout precedent: the pending-PO acceptance
  pattern (an issue stays open until the PO confirms acceptance) is standard and unaffected by
  this harness.
