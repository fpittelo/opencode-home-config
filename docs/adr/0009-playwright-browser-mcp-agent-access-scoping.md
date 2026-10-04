# MADR-0009: Introduce Playwright browser MCP with agent access scoping

- **Status:** accepted
- **Date:** 2026-10-04
- **Deciders:** @fpittelo (PO approval 2026-10-04; grooming 2026-10-03/04), @architect, @cyber-security (MADR-0008 quadrant-1 review — verdicts recorded below)
- **Driven by:** issue #207 · Epic: fpittelo/coach-web#133 (Autonomous Local Deployment & User-Journey Verification)

## Context

The cross-repo epic "Autonomous Local Deployment & User-Journey Verification"
(fpittelo/coach-web#133) requires agents to verify user journeys against deployed
application lanes (dev/qa) without the Product Owner manually driving a browser.
The HOME OpenCode profile currently defines 6 MCP servers (2× GitHub native, 3×
Coach Docker, openrouter remote) — none provides browser automation capability.

For coach-web specifically, the deploy foundation already exists: the coach-web
ADR-007 three-lane compose topology, the per-repo lane wrapper
(`scripts/lane.sh`, fixed `coach-web-*` compose project names, dev/qa lanes
only, loopback-only port publishing), and `scripts/e2e-preflight.sh` with
scoped teardown. Yet no agent can open the running UI, exercise user journeys,
and sign off — journey verification remains a manual PO activity, the largest
remaining PO tax not yet addressed by the MADR-0008 responsibility harness.

Browser automation is a high-capability, high-risk surface: an agent with a
browser can navigate arbitrary URLs, submit forms, ingest untrusted page
content into its context, and interact with any locally-reachable web
application. Access must therefore be scoped by the same defense-in-depth
pattern proven with the Coach MCP (#150): global default-deny baseline in
`opencode.jsonc` plus explicit per-agent restatement in `agents/*.md`.

## Decision Drivers

- **Agent autonomy:** the sprint loop must complete deploy → verify → teardown
  without manual help (MADR-0008 agent-probe pattern).
- **Realistic verification:** scripted HTTP checks cannot confirm interactive
  UI behaviour; agents must browse the accessibility tree, click, and read
  console output.
- **Least privilege / SoD:** browser tools only for agents with a demonstrated
  need (`@developer`, `@devops`); gatekeeper and charter agents
  (`@code-reviewer`, `@scrum-master`, `@coach`) keep read-only/zero-tool
  postures; built-in subagents inherit zero access.
- **Blast-radius containment:** agent browser and container actions stay scoped
  to coach-web dev/qa workloads.
- **KIS/YAGNI (#180, MADR-0003):** minimal capability that satisfies the story;
  no scripted E2E framework today.
- **Supply-chain hygiene (MADR-0002):** externally-fetched tooling is pinned
  and integrity-verified.
- **Swiss nLPD:** no *real* personal data or secrets exposed through browser
  tooling, page content, console logs, or session reports — dev/qa lanes run
  synthetic data only (see nLPD assessment below).

## Considered Options

### Option 1: Status quo — manual browser verification by the PO

- Pros: zero new attack surface; the PO sees every journey directly.
- Cons: the PO remains the verification bottleneck — directly contradicts the
  MADR-0008 harness goal; blocks the autonomous deployment epic
  (coach-web#133); does not scale with sprint velocity.

### Option 2: Playwright MCP only, scoped to @developer and @devops (chosen)

- Pros: official Microsoft-maintained MCP server (`@playwright/mcp`, stdio via
  npx) — mature, actively maintained, snapshot/accessibility-tree operation
  (no vision dependence); agents browse interactively (navigate, click,
  snapshot, read console); reuses the proven COACH_* scoping pattern (#150)
  for permission enforcement; zero new test framework (YAGNI respected);
  unblocks the epic.
- Cons: new executable and untrusted-content ingestion surface on VIDAR;
  interactive journeys are not regression-replayable; mitigations and accepted
  residuals documented in Security Considerations.

### Option 3: Playwright MCP + scripted pytest-playwright journey suite

- Pros: deterministic, CI-replayable regression coverage of journeys.
- Cons: explicitly rejected for now at grooming (PO decision, grill Q2a,
  2026-10-03/04) — duplicates what agent-driven browsing delivers today and
  adds a framework the portfolio does not need yet (YAGNI, #180); remains a
  candidate follow-up if journey regression becomes a pain point.

### Option 4: Alternative browser MCP (e.g. chrome-devtools MCP)

- Pros: equivalent capability class.
- Cons: less mature MCP ecosystem fit than Playwright; no grooming mandate;
  switching cost with no identified benefit (KIS).

## Decision Outcome

Chosen option: **Option 2**, to be delivered by issue #207.

1. **New MCP server `BROWSER`:** stdio server entry in `opencode.jsonc`,
   mirroring the COACH_* config pattern (space-free name so `BROWSER_*`
   permission patterns are unambiguous, #108 precedent). Supply-chain
   pinning (MADR-0002 driver 3), stated precisely (#219 AC4): the npx
   package is pinned to an **exact version** (`npx @playwright/mcp@<pinned>`
   — no floating `latest` resolution), and `install.sh` performs a
   **pin-time registry audit** (downloads the pinned tarball once and
   verifies its SHA512 against the captured `dist.integrity`). This is
   **not** equivalent to the `github-mcp-server` native-binary pattern
   (installed once, integrity never re-fetched): `npx` re-resolves the
   package from the npm registry at every session start (TOCTOU — a
   post-audit registry compromise would be fetched), and the Chromium
   browser binary is downloaded unpinned by Playwright. A local lockfile
   install (`npm i` with commit-locked integrity) is the recorded candidate
   follow-up if stronger pinning is ever mandated (not implemented — KIS).
2. **Hardened launch configuration** (mandated flags machine-enforced by
   the config gate, #219 AC3): the server runs with an **ephemeral,
   isolated browser profile** (`--isolated` — no persistence of cookies,
   sessions, or storage between or after sessions), **WebMCP disabled**
   (`--no-webmcp` — pages must not register tools exposed to the agent,
   #219 F2), **service workers blocked** (`--block-service-workers`,
   #219 advisory F7), **image responses omitted** (`--image-responses
   omit` — page screenshots stay out of the model context; nLPD data
   minimization, #219 advisory), a **loopback-origin request allowlist**
   (`--allowed-origins` — see the boundary caveat below), and a **scoped
   output directory** (`--output-dir /tmp/opencode/playwright-output` —
   automatically-named output files land outside the workspace and HOME,
   #219 F6). Flag support is verified against the pinned version in the
   implementation spec. *Implementation note (#207):* exact lane ports
   live in the coach-web repo, so the implemented allowlist uses loopback
   wildcard-port origins (`http://localhost:*;http://127.0.0.1:*` — the
   flag's documented glob syntax). *Accuracy correction (#219 AC2):*
   upstream documents `--allowed-origins` as **not a security boundary**
   ("does not serve as a security boundary and does not affect
   redirects") — it filters direct requests only, so arbitrary-origin
   navigation remains possible **by design**; the earlier "cloud metadata
   IP `169.254.169.254` unreachable" claim was unfounded and has been
   deleted. *Host prerequisite (#229):* the default `chrome` channel requires
   Google Chrome on the host — installed 2026-10-04 per PO decision (#229)
   after the first `browser_navigate` failed with `Chromium distribution
   'chrome' is not found at /opt/google/chrome/chrome`; the launch
   configuration is intentionally unchanged and all hardening flags are
   unaffected.
3. **Untrusted-content rule:** page content (DOM, text, console output) is
   treated as **untrusted data, never instructions** — stated in the
   agent-facing workflow docs for `@developer`/`@devops` and enforced through
   `@code-reviewer` review discipline.
4. **Downloads:** browser downloads go to a scoped directory and are **never
   executed** by any agent bash step.
5. **Agent access scoping (defense-in-depth, #150 pattern):**
   - Global default-deny baseline: `BROWSER_*: deny` at the root `permission`
     level of `opencode.jsonc` — covers built-in subagents (`explore`,
     `general`, `task`) and any unconfigured persona.
   - `@developer` and `@devops`: `BROWSER_*: allow` (journey browsing during
     TDD; lane deploy/validate/teardown).
   - `@architect`, `@coach`, `@code-reviewer`, `@cyber-security`,
     `@scrum-master`: `BROWSER_*: deny` re-stated explicitly per agent spec.
6. **Machine-enforced guardrail:** the config gate's namespace-exclusivity
   check (`harness/config-validation/check_coach_exclusivity.py`) is
   **generalized to cover both `COACH_*` and `BROWSER_*`** — global baseline
   deny, allow only in the designated agent specs, explicit deny in all other
   agent specs — so scoping drift fails the gate instead of surfacing silently
   (once implemented, this closes the arc42 §11 risk "permission semantics
   verified by spec, not runtime tests" for this namespace; the generalization
   lands with AC2–AC4 of #207).
7. **Docker permission posture unchanged (grooming Q12=B):** containment by
   convention — the lane wrapper (`scripts/lane.sh`, fixed compose project
   names, loopback-only publishing) is the documented single path, enforced
   through `@code-reviewer` review discipline; no new docker denies.
8. **Lane boundaries:** agents operate dev/qa lanes only and report pass/fail
   to the PR thread (auditable session record); prod lane verification remains
   manual with @fpittelo (PO Gate Inventory, MADR-0008).

## Security Considerations

STRIDE threat model (MADR-0008 quadrant 1; reviewed by @cyber-security against
arc42 §8 cross-cutting security and §11 risks/technical debt, 2026-10-04):

| Threat | Browser-MCP manifestation | Mitigation |
| :--- | :--- | :--- |
| **S**poofing | Persistent profile reuses the user's authenticated sessions against locally-reachable apps | `--isolated` ephemeral profile; never browse authenticated personal apps |
| **T**ampering | Indirect prompt injection: untrusted page DOM/console injects instructions driving agent tool calls; WebMCP lets a page register agent-visible tools; `npx` supply chain re-resolves from the registry each session (TOCTOU) | Page content is untrusted data, never instructions; `--no-webmcp` (pages cannot register tools, #219); `--block-service-workers`; exact-version pin + pin-time registry audit via `install.sh` (per-session re-resolution residual, §residual 4) |
| **R**epudiation | Browser sessions not structurally logged; PR-comment report is the only trail | Session summary required in the PR thread (redaction rule below — no personal-data console/page content); no secret-bearing trace artifacts |
| **I**nformation disclosure | Page content (athlete training data) and cookies/console tokens sent to the third-party model provider | Data minimization (dev/qa synthetic data — convention-only, §nLPD); `--image-responses omit` (#219); ephemeral profile; report/PR-comment redaction rule (§nLPD); nLPD processor disclosure |
| **D**enial of service | Unbounded navigation/downloads exhaust disk/CPU; hostile page hangs the browser | `mcp_timeout` aligned with the navigation timeout (60 s, #219 F8); scoped `--output-dir` under `/tmp`; size bounds |
| **E**levation of privilege | Browser reaches other localhost services and arbitrary remote origins (navigation is not origin-contained, by design); downloaded files later executed by bash | `--allowed-origins` request filter (not a security boundary — §residual 2); downloads never executed; non-root |

**Swiss nLPD (FADP) assessment:** coach-web dev/qa lanes render athlete
training data (personal, potentially health-related). Agent browsing sends
page snapshots and console output to the model provider (OpenRouter, US) — a
cross-border processor disclosure. Controls: dev/qa lanes operate on
synthetic/anonymized data; browsing of authenticated personal apps is
forbidden; the processor disclosure is documented here; production data is
never browsed by agents (prod lane stays manual with @fpittelo).
*Enforcement honesty (#219 AC5):* the synthetic-data-only and
no-authenticated-apps controls are **convention-only** — carried by review
discipline and agent workflow rules, not by machine-enforced settings.
**Redaction rule (#219 AC5):** journey reports and PR comments must not
include console or page content containing personal data — summarize,
redact, or omit. `--image-responses omit` additionally keeps page
screenshots out of the model context.

**Accepted residual risks:**

1. **Raw `docker` is not denied for `@developer`/`@devops`** — ACCEPTED. This
   is the pre-existing MADR-0004 allow-by-default bash posture (with
   `@devops`'s explicit `docker *` allow), not a risk introduced by MADR-0009;
   the browser MCP adds no docker capability. Cross-referenced: MADR-0004,
   arc42 §11. Compensating controls: lane wrapper as the documented single
   path, review discipline, single-user workstation blast radius.
2. **Browser navigation beyond lane origins** — ACCEPTED residual, carried
   with compensating controls. *Reframed by the #219 re-review (AC2):* the
   earlier "MITIGATED, narrowly residual — allowlist misconfiguration"
   framing was wrong. Upstream documents `--allowed-origins` as **not a
   security boundary** ("does not serve as a security boundary and does not
   affect redirects"): it filters direct requests only, so navigation to
   arbitrary origins — including other localhost services and remote URLs —
   remains possible **by design**. The flag is kept as a request-scoping
   convenience and misconfiguration tripwire, not as containment. The risk
   is carried by the compensating controls (untrusted-content rule,
   `--isolated` ephemeral profile, `--no-webmcp`, review discipline,
   PR-thread session reports, single-user workstation blast radius) and is
   re-examined at the first retro after adoption.
3. **Interactive journeys are not regression-replayable** — ACCEPTED (YAGNI;
   Option 3 remains a deferred candidate).
4. **`npx` supply-chain TOCTOU + unpinned Chromium** — ACCEPTED (KIS,
   #219 AC4). The package version is pinned, but `npx` re-resolves it from
   the npm registry at every session start, so the `install.sh` SHA512
   check is a pin-time audit — not the `github-mcp-server` native-binary
   pattern (installed once, integrity never re-fetched). The Chromium
   browser binary is downloaded unpinned by Playwright. Compensating
   controls: exact-version pin (no floating `latest`), pin-time registry
   audit, npm's per-fetch `dist.integrity` verification. Candidate
   follow-up (not implemented): local lockfile install for full integrity
   pinning.

**@cyber-security review verdict (2026-10-04, arc42 §8/§11):** *REQUEST
CHANGES on the original draft — blocking findings: (1) missing STRIDE model,
(2) unaddressed indirect prompt injection via browsed content, (3) persistent
profile cookie/session exposure, (4) unpinned npx supply-chain surface,
(5) no machine-enforced `BROWSER_*` guardrail, (6) unassessed nLPD
personal-data egress; residual ruling: raw-docker residual accepted as
pre-existing MADR-0004 posture, unrestricted-navigation residual rejected as
scoped. All blocking findings are addressed in this revision (STRIDE table,
untrusted-content rule, `--isolated` + origin allowlist, exact-version
pinning, generalized namespace-exclusivity gate, nLPD assessment); final
acceptance remains conditional on PO approval per the pending-PO-acceptance
pattern.*

**@cyber-security re-review verdict (2026-10-04, commit 08a2195):** *We
re-reviewed the revised MADR-0009 and confirm all six blocking findings and
both residual rulings are resolved — STRIDE model, untrusted-content rule,
`--isolated` ephemeral profile, exact-version pinning with `install.sh`
integrity verification, generalized `COACH_*`/`BROWSER_*`
namespace-exclusivity gate, and the nLPD data-minimization/processor
disclosure are all present, with the raw-docker residual correctly carried as
pre-existing MADR-0004 posture and the navigation residual narrowed to
allowlist misconfiguration under mandatory `--allowed-origins`. We APPROVE,
with final acceptance remaining conditional on PO approval per the
pending-PO-acceptance pattern.*

**Post-implementation re-review (2026-10-04, issue #219):** *APPROVE-WITH-CHANGES* — accuracy corrections required (WebMCP off, `--allowed-origins` boundary honesty, metadata-claim deletion, supply-chain TOCTOU honesty, nLPD convention-only + redaction rule, output scoping) are implemented in this revision; the DECISION itself is unchanged.

## Consequences

- **Positive:** delivery agents autonomously deploy, browse, verify user
  journeys, report pass/fail to the PR thread, and tear down their
  environment — unblocking epic coach-web#133 and removing the largest
  remaining manual PO tax; access scoping reuses the proven #150
  defense-in-depth pattern and becomes machine-checkable by the generalized
  config gate; supply-chain and nLPD surfaces are pinned, minimized, and
  documented.
- **Negative:** an untrusted-content ingestion path exists by design (mitigated
  by the untrusted-data rule, `--no-webmcp`, and the ephemeral profile);
  navigation is not origin-contained by design (`--allowed-origins` is not a
  security boundary, #219); `npx` re-resolves the package from the registry
  each session (TOCTOU) and Chromium is downloaded unpinned — carried as
  residual 4 with the lockfile-install candidate follow-up (#219); the nLPD
  egress controls are convention-only and the processor disclosure to the
  model provider is consciously carried with data-minimization controls; the
  config gate generalization is additional implementation scope; four
  residual risks are consciously carried (§Security Considerations).
- **Neutral:** no change to the bash permission posture (MADR-0004), the
  COACH_* denies (#150), or the three-branch lifecycle. arc42 §9 and §11 are
  indexed/updated at acceptance; the §3/§5/§8 component and cross-cutting
  updates land with the implementation PR (AC2–AC4 of #207), when the
  `BROWSER` server actually enters the config.
