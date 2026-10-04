# MADR-0009: Introduce Playwright browser MCP with agent access scoping

- **Status:** proposed
- **Date:** 2026-10-04
- **Deciders:** @fpittelo (PO-approved grooming, 2026-10-03)
- **Driven by:** issue #207 · Epic: fpittelo/coach-web#133 (Autonomous Local Deployment & User-Journey Verification)

## Context

The cross-repo epic "Autonomous Local Deployment & User-Journey Verification"
(fpittelo/coach-web#133) requires agents to verify user journeys against deployed
application lanes (dev/qa) without the Product Owner manually driving a browser.
The HOME OpenCode profile currently defines 6 MCP servers (2× GitHub native, 3×
Coach Docker, openrouter remote) — none provides browser automation capability.
Today, journey verification is a manual PO activity: it is the largest remaining
PO tax not yet addressed by the MADR-0008 responsibility harness, and it blocks
the autonomous deployment loop the epic targets.

Browser automation is a high-capability, high-risk surface: an agent with a
browser can navigate arbitrary URLs, submit forms, and interact with any
locally-reachable web application. Access must therefore be scoped by the same
defense-in-depth pattern proven with the Coach MCP (#150): global default-deny
baseline in `opencode.jsonc` plus explicit per-agent restatement in `agents/*.md`.

## Decision Drivers

- **Autonomous journey verification:** agents must browse deployed lanes
  (dev/qa) during TDD and lane validation, end-to-end without PO presence
  (MADR-0008 agent-probe pattern).
- **Least privilege / SoD:** browser tools must be available only to agents with
  a demonstrated need; all other personas — including built-in subagents —
  inherit zero access.
- **KIS/YAGNI (#180):** no scripted end-to-end test suite alongside the MCP;
  the browser is a tool for agents, not a new test framework.
- **Containment proportionality (MADR-0003):** guardrails must be real but
  proportionate; no speculative sandboxing beyond the groomed decision.
- **Supply-chain hygiene (MADR-0002):** externally-fetched tooling follows the
  pinned-version pattern where practical.

## Considered Options

### Option 1: Status quo — manual browser verification by the PO

- Pros: zero new attack surface; the PO sees every journey directly.
- Cons: the PO remains the verification bottleneck — directly contradicts the
  MADR-0008 harness goal; blocks the autonomous deployment epic
  (coach-web#133); does not scale with sprint velocity.

### Option 2: Playwright MCP only, scoped to @developer and @devops (chosen)

- Pros: official Microsoft-maintained MCP server (`@playwright/mcp`, stdio via
  npx) — mature, actively maintained, structured accessibility-tree access
  (no screenshot-only scraping); reuses the proven COACH_* scoping pattern
  (#150) for permission enforcement; zero new test framework (YAGNI respected);
  unblocks the epic.
- Cons: new executable surface on VIDAR (npx fetch at first run); two accepted
  residual risks (see Security Considerations): raw `docker` is not denied for
  @developer/@devops (containment by convention), and browser navigation is not
  origin-restricted.

### Option 3: Playwright MCP + scripted pytest-playwright journey suite

- Pros: deterministic regression coverage of journeys in CI.
- Cons: explicitly rejected at grooming (PO-approved, 2026-10-03) — duplicates
  what agent-driven browsing delivers, adds a framework the portfolio does not
  need today (YAGNI, #180); deferred until a concrete need materializes.

### Option 4: Alternative browser MCP (e.g. chrome-devtools MCP)

- Pros: equivalent capability class.
- Cons: less mature MCP ecosystem fit than Playwright; no grooming mandate;
  switching cost with no identified benefit (KIS).

## Decision Outcome

Chosen option: **Option 2**, to be delivered by issue #207.

1. **New MCP server `BROWSER`:** stdio server entry in `opencode.jsonc` running
   `npx @playwright/mcp` (enabled), mirroring the COACH_* config pattern
   (space-free name so `BROWSER_*` permission patterns are unambiguous, #108
   precedent). Version pinning of the npx package follows the MADR-0002
   supply-chain pattern and is finalized in the implementation spec.
2. **Agent access scoping (defense-in-depth, #150 pattern):**
   - Global default-deny baseline: `BROWSER_*: deny` at the root `permission`
     level of `opencode.jsonc` — covers built-in subagents (`explore`,
     `general`, `task`) and any unconfigured persona.
   - `@developer` and `@devops`: `BROWSER_*: allow` (journey browsing during
     TDD; lane deploy/validate/teardown).
   - `@architect`, `@coach`, `@code-reviewer`, `@cyber-security`,
     `@scrum-master`: `BROWSER_*: deny` re-stated explicitly per agent spec.
3. **Docker permission posture unchanged (grooming Q12=B):** containment by
   convention — lane wrapper + review discipline; no new docker denies.
4. **Lane boundaries:** agents operate dev/qa lanes only; prod lane verification
   remains manual with @fpittelo (PO Gate Inventory item, MADR-0008).

## Security Considerations

STRIDE pass (to be confirmed by @cyber-security review against arc42 §8/§11
**before spec finalization**, per MADR-0008 quadrant 1):

| Threat | Assessment | Mitigation |
| :--- | :--- | :--- |
| **S**poofing | Low — stdio local process, no auth surface | n/a |
| **T**ampering | Medium — browser session can mutate state of locally-reachable apps | Scoped to dev/qa lanes only; prod lane stays manual (PO gate) |
| **R**epudiation | Low — agent actions are logged in session transcripts | Existing session logging |
| **I**nformation disclosure | Medium — browser can navigate arbitrary URLs, including network-reachable ones | **Accepted residual risk:** navigation is not origin-restricted; compensating control = review discipline + lane scoping |
| **D**enial of service | Low — local single-user workload | n/a |
| **E**levation of privilege | Medium — `npx` executes fetched code at first run | Version pinning (MADR-0002 pattern); **accepted residual risk:** raw `docker` is not denied for @developer/@devops (containment by convention, grooming Q12=B) |

- **Zero secrets logged or hardcoded:** the BROWSER server requires no
  credentials; gitleaks stays clean.
- **@cyber-security review verdict:** *pending — this ADR must not advance to
  `accepted` before the verdict is recorded here (MADR-0008 blocking gate).*

## Consequences

- **Positive:** autonomous user-journey verification on dev/qa lanes unblocks
  epic coach-web#133 and removes the largest remaining manual PO tax; access
  scoping reuses the proven #150 defense-in-depth pattern (global baseline +
  per-agent restatement), keeping the permission model uniform and
  machine-checkable by the config gate.
- **Negative:** two accepted residual risks (raw docker not denied; browser
  navigation not origin-restricted) are consciously carried and documented;
  `npx` introduces a supply-chain fetch surface (mitigated by version pinning);
  the config gate (`harness/config-validation/`) must be extended to enforce
  the BROWSER_* baseline the same way it enforces COACH_* exclusivity.
- **Neutral:** no change to the bash permission posture (MADR-0004), the
  COACH_* denies (#150), or the three-branch lifecycle; arc42 §3/§5/§8/§9
  updates follow at acceptance per the arc42 update triggers.