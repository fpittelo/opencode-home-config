# MADR-0026: Zero-lag github-mcp-server pin freshness (scheduled drift workflow)

- **Status:** accepted
- **Date:** 2026-11-15
- **Deciders:** @fpittelo (Product Owner — "go" on O3, 2026-10-25, issue #412), @architect; @cyber-security (MADR-0008 review — **APPROVE-WITH-CONDITIONS**, 2026-11-15; conditions C1–C12, attached as enforceable invariants below)

## Context

The `github-mcp-server` native binary is pinned in `install.sh` (`GITHUB_MCP_VERSION` + `GITHUB_MCP_TARBALL_SHA256`, MADR-0002 decision point 3): a supply-chain control with a fail-closed SHA256 double-verification path (upstream checksums file → pinned hash → downloaded artifact) and a single-pin invariant enforced by gate 13 (`test_pin_consistency.py`: exactly one `GITHUB_MCP_VERSION` assignment).

The PO directive (2026-10-25, issue #412): *"I want to make sure to always use the latest release of the GitHub MCP."* Today the version is bumped **by hand**, only when someone notices — that is the gap. Evidence of the lag cost:

| Fact | Evidence |
| :--- | :--- |
| Pin bumped manually, twice in three weeks | #310 (v1.12.2 → v2.0.2, with a pin-consistency regression), #434/#439 (v2.0.3 → v2.1.0) |
| Lag reached one minor release / 4 days before anyone noticed | #412 evidence table (2026-10-25) |
| Refresh automation: none | no `dependabot.yml`, no `renovate.json`, no scheduled freshness workflow |
| Upstream releases ship security-relevant fixes | v2.0.3 included a Go 1.27.3 upgrade for compromised-CA mitigation |

Design tension to resolve explicitly: *"always the latest release"* is **not** *"always `:latest`"*. The pin is a deliberate supply-chain control; an unreviewed binary swap would defeat the checksum gate. The directive is therefore read as **zero-lag, reviewed refresh**: detect a new upstream release within days, land the bump through the normal reviewed flow.

## Decision Drivers

- **Zero lag:** ≤ 7 days detection latency behind the upstream latest release (measured from upstream `published_at`).
- **Reviewed bumps only:** every bump stays a PR with a genuine Tier B `@devfpittelo` approval (MADR-0017 trunk+tag); no unreviewed binary swap, ever.
- **Signal integrity:** silence must never equal verified freshness; drift truth must be computable, not socially held in an issue's state.
- **Credential hygiene:** no new long-lived credential; the repo's credential-drift history (#423) rules out PAT proliferation.
- **KIS/YAGNI:** minimal new surface — one scheduled workflow + one issue template pattern; no bot framework.
- **Board SSOT (MADR-0013):** the workflow must not bypass grooming or inject `status::*` transitions.

## Considered Options

### Option 1: Resolve `releases/latest` at install time

- Pros: zero lag, zero new infrastructure.
- Cons: non-reproducible installs; silent unreviewed binary upgrades; breaks the single-pin gate (MADR-0002 D3). **Rejected** on MADR-0002 grounds.

### Option 2: Renovate / Dependabot PR on `install.sh`

- Pros: reviewable, existing bot ecosystem.
- Cons: **cannot compute `GITHUB_MCP_TARBALL_SHA256`** (no datasource for release-tarball hashes) — needs a custom manager/workflow anyway, i.e. the cost of O3 with less control. **Rejected**.

### Option 3: Scheduled freshness workflow → drift issue (CHOSEN)

- Pros: minimal new surface (one workflow, read-only over the pin and public release metadata); keeps human/agent review + checksum verification; reuses the issue-driven flow; no supply-chain weakening.
- Cons: a new workflow to maintain; signal depends on Actions being enabled (see C12 residual).

### Option 4: Manual discipline only

- Pros: nothing to build.
- Cons: already proven insufficient — this decision exists because of it. **Rejected**.

## Decision Outcome

Chosen option: **"Option 3 — scheduled pin-freshness workflow"**, because it delivers the PO's zero-lag directive while keeping every bump a reviewed, checksum-verified PR (decision drivers 1–2), at the smallest surface cost (driver 5). O1 is rejected on MADR-0002 supply-chain grounds; O2 cannot compute the tarball hash; O4 is empirically insufficient.

Mechanism:

- **Trigger:** weekly cron (Monday, staggered off the existing deep-validation cron) + on-demand `workflow_dispatch`.
- **Detection:** compare `semver(upstream latest release tag)` vs. the pin **read from `install.sh` at run time**; normalize the leading `v`; drift = upstream semver strictly greater than the pinned semver (a backport release never reads as drift).
- **Drift behavior:** open or update a single deterministic drift-tracking issue (label `agent::devops` + `type::task` only); **non-failing** — never breaks CI, never auto-installs, never mutates the pin.
- **Bump path:** unchanged manual reviewed checklist proven in #310/#439 — single pin change + `GITHUB_MCP_TARBALL_SHA256` taken from the official upstream `github-mcp-server_<ver>_checksums.txt` at bump time (never from the issue body) + version-spy stub + `opencode.jsonc` comment literal + docs claims, all through PR + genuine `@devfpittelo` review.
- **SLA:** ≤ 7 days detection latency.

Enforceable invariants (from the @cyber-security review, all mandatory for the implementation):

| # | Invariant |
| :--- | :--- |
| C1 | Workflow `permissions:` exactly `{contents: read, issues: write}` — never `contents: write`, `pull-requests: write`, `actions: write`, or `id-token`; checkout with `persist-credentials: false` |
| C2 | No new persisted version state (no cache, no "latest known tag" file, no second version literal) — `install.sh` remains the single pin; the drift issue is the only state |
| C3 | The workflow never computes/emits a SHA256 into `install.sh` or any persisted artifact; the bump hash comes from the upstream checksums file at bump time, never from the issue body |
| C4 | Built-in `GITHUB_TOKEN` (`${{ github.token }}`) only — no PAT (ephemeral, repo-scoped, audited in-repo; anti-recursion: token-created events don't trigger workflow runs) |
| C5 | Zero `secrets.*` references and zero PAT env vars in the workflow; it acts as `github-actions[bot]`, a third identity that neither consumes nor dilutes the two-identity SoD doctrine and cannot self-approve |
| C6 | A machine check (e.g. `harness/config-validation/check_pin_freshness_workflow.py`) asserts C1+C5 so they cannot regress silently on the next workflow edit |
| C7 | Drift truth = version comparison on every run (issue lifecycle — closed/relabelled/renamed — has zero influence; next run re-detects and re-opens/updates); `v` prefix normalized; semver compare |
| C8 | Deterministic idempotency: locate the existing drift issue by a stable hidden body marker + fixed label set; at most one open drift issue; a new upstream release **updates** it rather than spawning duplicates; re-open on persistent drift only when no bump PR referencing it exists |
| C9 | The issue body is a notification, never an authorization — it must state that the bump requires a PR reviewed by `@devfpittelo`; only semver-validated tag, ISO publish date, and constructed URLs may be interpolated — **never** upstream release body/changelog prose (indirect prompt-injection surface, and unnecessary nLPD exposure); the body names the exact asset to hash (`github-mcp-server_Linux_x86_64.tar.gz`) and the checksums URL |
| C10 | The workflow never sets `status::*` labels and never auto-closes the drift issue on merge — `@scrum-master` owns status transitions after grooming |
| C11 | Tri-state result — `fresh \| drift \| unknown`; any API/parse failure → `unknown` (never `fresh`), surfaced as a run annotation + job summary, and after two consecutive `unknown` runs as a tracked board item; authenticated `GITHUB_TOKEN` for the upstream read (rate-limit mitigation); `releases/latest` returns a single object (no pagination, excludes drafts/prereleases) |
| C12 | **Documented residual (also recorded in `arc42/03` §3 by the implementation PR):** GitHub auto-disables scheduled workflows after ~60 days of repository inactivity — mitigation: the repo is not idle in practice, `workflow_dispatch` remains available, and the last scheduled run date is checked during release hygiene |

## Consequences

- **Positive:** detection latency bounded at ≤ 7 days instead of "whenever someone notices"; every bump remains reviewed and checksum-verified (MADR-0002 D3 intact, gate 13 invariant intact); one read-only workflow instead of a bot framework; the bump checklist is now documented and reproducible (#310/#439 precedent).
- **Negative:** a new workflow to maintain; the signal can be suppressed by a repo-write principal (inside the existing trust boundary — review control is the instrument) or go blind via API failure / 60-day auto-disable; drift-issue hygiene becomes a recurring @scrum-master concern.
- **Mitigations:** C1–C6 make the workflow's blast radius machine-checkable (guardrails are gates, not prose — MADR-0008); C7–C11 make the signal structurally immune to issue-state tampering and rate-limit silence; C12 records the auto-disable residual with a hygiene-check mitigation; arc42 §1.2 records the workflow as a **signal** workflow — never a branch-protection required check.

## References

- #412 — the spike (PO decision 2026-10-25; SLA and cadence decisions)
- #310, #434/#439 — manual bump precedent and checksum-provenance flow
- MADR-0002 (pinned native transport, D3), MADR-0003 (proportionate gates), MADR-0013 (board SSOT), MADR-0017 (trunk+tag), MADR-0008 (security routing)
- `install.sh:19-61` (pin + verification), `harness/config-validation/test_pin_consistency.py` (gate 13)
- @cyber-security review 2026-11-15: APPROVE-WITH-CONDITIONS (C1–C12) — recorded in the Deciders line and inlined above
