---
name: kis-yagni
description: "Use on every task start — mandatory for all HOME agents. Enforces Keep-It-Simple (KIS) and You-Aren't-Gonna-Need-It (YAGNI) delivery discipline: minimal diffs, brief evidence, over-delivery is a review finding. Triggers: any design, implementation, review, backlog grooming, or board decision in an @fpittelo repository."
---

# KIS & YAGNI Delivery Discipline

Operational playbook for the delivery principle defined in `home-governance` §9 — **policy SSOT**. This skill makes the discipline actionable; it does not redefine it.

## The Three Tenets

1. **Minimal diffs:** deliver the smallest change that satisfies the issue's acceptance criteria — no speculative scope, no unrequested refactors or embellishments.
2. **Brief evidence:** report gate results and proof concisely; evidence serves verification, not volume.
3. **Over-delivery is a review finding:** scope beyond the issue's acceptance criteria is formally flagged by `@code-reviewer`, even when technically correct.

## Per-Role Application

| Role | Apply KIS & YAGNI by... |
| :--- | :--- |
| `@architect` | Grooming the minimal scope that satisfies the ACs; no speculative components, no premature ArchiMate detail. |
| `@scrum-master` | Minimal issue structure and board writes; no ceremony beyond the DoD/DoR gates. |
| `@developer` | The smallest implementation that turns tests green; no unrequested refactors, abstractions, or "while I'm here" fixes. |
| `@code-reviewer` | Formally flagging scope beyond the issue's ACs — even when technically correct — and approving minimal diffs without demanding embellishment. |
| `@devops` | Minimal pipeline/infra changes; no speculative stages, images, or tooling. |
| `@cyber-security` | Proportionate security controls — threat-model-driven, not maximalist. |
| `@coach` | Minimal workout data/tooling changes serving the athlete's actual training need. |

## Pre-Delivery Checklist

Before opening a PR or posting a deliverable, verify:

- [ ] Every changed file maps to an acceptance criterion in the issue.
- [ ] No drive-by refactors, renames, or formatting changes outside the ACs.
- [ ] Evidence reported is concise (gate command + outcome, not full logs).
- [ ] Anything discovered beyond scope is **routed** (new issue or explicit triage note), never silently included.

## Non-Scope: What KIS Never Excuses

KIS & YAGNI constrain **scope**, never **quality**. They do not excuse skipping:

- Security controls (secrets hygiene, dependency audits, threat-model requirements).
- Tests required by the TDD mandate or the issue's ACs.
- The zero-warning quality gate or any DoD criterion.
- Governance recording duties (MADR, arc42 triggers) when a decision class requires them.

## Provenance

- Policy SSOT: `home-governance` §9 — KIS & YAGNI Delivery Principle.
- Provenance: PO directive 2026-10-03 (Sprint 08, #167); standing policy since #180; extends MADR-0003 D5 (Proportionate Quality Gates).
- Mandatory activation for all agents: PO directive 2026-10-13 (#306).
