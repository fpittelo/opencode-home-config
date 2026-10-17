# MADR-0019: Root-inheritance bash permission baseline retires five-file mirroring

- **Status:** accepted
- **Date:** 2026-10-17
- **Deciders:** @fpittelo (PO directive "go" executing audit recommendation #340, 2026-10-17), @architect (author), @cyber-security (verdict APPROVE-WITH-CONDITIONS, PR #349 comment 6238290878 — MADR-0015 condition 4 superseded)

## Context

MADR-0004 introduced the three-tier bash permission posture duplicated verbatim across the root `opencode.jsonc` `permission.bash` block and four allow-default agent specs; MADR-0015 hardened this into a formal **five-file mirroring** requirement with an order-sensitive CI drift guard (its condition 4, from the @cyber-security approval). The 2026-10-17 architecture audit identified the mirroring as the largest maintenance tax in the harness: ~85 duplicated lines per agent file (~360 lines total), a 5-file identical edit for every posture change, and ~1,000 wasted prompt tokens per subagent spawn.

Empirical verification (issue #340 AC1, `opencode debug agent` probes on opencode 1.19.0, independently corroborated by @code-reviewer and @cyber-security) established OpenCode's actual semantics:

1. An agent spec that **omits `bash:`** inherits the full root `permission.bash` rule list — omission is safe.
2. A **partial bash map in an agent spec is appended AFTER all config-level rules** (last-match-wins) — a partial map can therefore WIDEN the posture (e.g. a `docker *: allow` re-statement would override the root `*.env*: deny` for `docker run --env-file x.env`).
3. Posture-equivalence probes over 398–448 resolved commands per agent: **0 diffs** pre vs post change.

## Decision Drivers

- **KIS & YAGNI:** ~360 duplicated lines and a 5-file edit ceremony serve no security purpose once inheritance semantics are proven.
- **Security equivalence (non-negotiable):** the effective posture must be byte-identical; the refactored gate must pin the root baseline as the single SSOT.
- **MADR-0015 condition 4:** five-file mirroring was a security-approval condition — superseding it requires an explicit @cyber-security verdict (MADR-0008 §2 routing), delivered before merge.
- **Single source of truth:** one ordered rule list, machine-pinned, beats five mirrors plus a drift guard.

## Considered Options

### Option 1: Root inheritance — agents omit `bash:` (chosen)

- Pros: −360 lines; one SSOT pinned by the refactored Gate 16; posture byte-equivalent (proven); role deviations become explicit, minimal, and documented.
- Cons: supersedes MADR-0015's mirroring condition (requires this record + security verdict); role-signature allows (devops `docker *`, cyber-security audit tools) disappear from the agent files — accepted because they were redundant under root `"*": allow` and a partial-map re-statement would actively widen the posture.

### Option 2: Keep five-file mirroring (status quo)

- Pros: zero governance change.
- Cons: permanent 5-file edit tax and drift-guard complexity for zero security benefit; contradicts the audit's KIS findings.

### Option 3: Partial maps per agent (root baseline + role deltas re-stated)

- Pros: role signatures stay legible in agent files.
- Cons: **rejected on security grounds** — append-after-deny-tail semantics flip root denies to allows for overlapping patterns (`docker run --env-file x.env`, `gitleaks detect --source x.env`); byte-equivalence impossible without re-stating the full tail, which is Option 2.

## Decision Outcome

Chosen option: **"Option 1 — Root inheritance"**. The root `opencode.jsonc` `permission.bash` block (allow head + 17-pattern ask tier + 59-pattern frozen deny tail, order-sensitive) is the **single SSOT** for the four allow-default agents (`@architect`, `@developer`, `@devops`, `@cyber-security`), which omit `bash:` entirely. Gate 16 (`harness/config-validation/check_bash_permission_tiers.py`) is refactored: it now pins the root baseline (order-sensitive), asserts each agent omits `bash:` or carries only documented deviation patterns, treats root-pattern re-statements in agent files as failures, and retains the 17-case last-match-wins truth table against the root config.

**Supersession:** this decision supersedes MADR-0015's five-file mirroring mechanism (condition 4 of its security approval) and amends MADR-0004's "per-agent, role-tailored" duplication. MADR-0015's ask-tier slimming decisions and frozen deny tail remain fully in force — at the root layer. `@scrum-master` (scoped allowlist, #347), `@code-reviewer` (read-only allowlist), and `@coach` (scalar deny) keep their distinct postures, which are outside the four-agent inheritance group.

**Security verdict (@cyber-security, PR #349 comment 6238290878): APPROVE-WITH-CONDITIONS** — byte-equivalence independently reproduced (409-command corpus, 0 diffs); conditions: this record lands in the same merge (condition 6 precedent: indexed with the config change), Gate 16 stays CI-wired with the root pin, CI green on the merge commit.

## Consequences

- **Positive:** −360 lines of duplication; posture changes are single-file edits; the drift guard now enforces the actually-desired invariant (no duplication) instead of mandating it; subagent prompts shed ~1,000 tokens each.
- **Negative:** MADR-0004/0015 narration of per-agent mirroring is historical; agent files no longer self-describe their full bash posture (mitigated by inline inheritance notes); role-signature allows are implicit in root `"*": allow`.
- **Mitigations:** Gate 16 CI pin (order-sensitive root baseline + clean-inheritance assertions + truth table); the empirical semantics are documented here and in the PR #349 evidence; residual risks R1 (scrum-master `gh pr *` append-override of root `*.env*` deny — pre-existing from #347) and R2 (Gate 16 flow-style `bash:` parsing gap) routed to follow-up issues.
