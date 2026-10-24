# MADR-0022: Consolidate GitHub MCP topology to three servers

- **Status:** proposed
- **Date:** 2026-10-24
- **Deciders:** @fpittelo (Product Owner), @architect; @cyber-security (security review pending, MADR-0008)

## Context

`opencode.jsonc` currently declares **five** `github-mcp-server` instances (all the same pinned v2.0.2 native binary, launched with different tokens/toolsets):

| Server | Token identity | Tools | Schema | Role |
| :--- | :--- | ---: | ---: | :--- |
| `GITHUB` | `@fpittelo` | 46 | 123.6 KB | Core board work (5 agents) |
| `GITHUB_CODE_REVIEWER` | **`@devfpittelo`** | 33 | 80.9 KB | PR review under separation of duties (#83) |
| `GITHUB_ACTIONS` | `@fpittelo` (same PAT) | 4 | 11.7 KB | CI run/step-log triage |
| `GITHUB_SECURITY` | `@fpittelo` (same PAT), `--read-only` | 6 | 15.1 KB | Dependabot / secret-scanning / CodeQL alerts |
| `GITHUB_PROJECTS` | `@fpittelo` (distinct `project`-scope PAT) | 3 | 14.5 KB | Projects v2 roadmap view |

The Product Owner observed (2026-10-24) that the GitHub MCP surface looks bloated with little value returned. A live `tools/list` audit of the pinned binary (this record's evidence) establishes three facts:

1. **Only one extra server carries a distinct identity.** `GITHUB_CODE_REVIEWER` authenticates as `@devfpittelo` for separation of duties. `GITHUB_ACTIONS`, `GITHUB_SECURITY`, and `GITHUB_PROJECTS` all act as `@fpittelo`, so a leak of that PAT reaches all of them regardless of process count — they provide **no credential containment**.
2. **Server count does not drive per-agent context cost.** MADR-0002 (#106) proved `permission: deny` removes denied MCP schemas from the prompt. Folding every server into one would yield 56 tools / 150.5 KB on a single process, but each agent would still see only the schemas it is allowed. The real cost of extra servers is **configuration surface, credential surface, and process count** — not tokens.
3. **Two servers have non-identity justification, one has none.** `GITHUB_SECURITY` runs `--read-only` at process start — a token-independent boundary on the only surface that can read raw secret material (MADR-0011 finding 4). `GITHUB_ACTIONS` is fail-closed namespace scoping over the destructive monolithic `actions_run_trigger`. `GITHUB_PROJECTS` serves a feature already demoted to an optional view (MADR-0018, #339) and depends on a broad `project`-scope PAT — the one instance that is pure liability.

Prior decisions in force: MADR-0011 provisioned `GITHUB_ACTIONS`/`GITHUB_SECURITY` and rejected `projects` (YAGNI); MADR-0014 introduced `GITHUB_PROJECTS` and its credential; MADR-0018 superseded MADR-0014's planning-SSOT claim while leaving its server/credential decisions in force; MADR-0020 retired the `GITHUB_RELEASES` FastMCP server on the rationale that a small server surface reachable by the pinned `gh` CLI under the same identity is not worth its carriage cost.

## Decision Drivers

- **KIS / YAGNI (#180):** retire MCP servers whose functional surface is unused or already reachable by a cheaper mechanism.
- **Least privilege and separation of duties:** preserve the single genuine identity boundary (`GITHUB_CODE_REVIEWER`) and the single process-level control (`--read-only`).
- **Credential minimization (Swiss nLPD):** eliminate the broad `project`-scope PAT carried for an optional, non-blocking feature.
- **Precedent (MADR-0020):** a small MCP surface performed by the pinned `gh` CLI under the same identity should not be carried as a server.
- **MADR-0008 security routing:** permission- and credential-affecting changes require `@cyber-security` review before spec finalization.

## Considered Options

### Option 1: Status quo (five servers)

- Pros: zero work; architecture unchanged.
- Cons: retains a broad-scope PAT for a demoted feature; retains fail-closed scoping achievable another way; leaves the perceived bloat unaddressed.

### Option 2: Retire `GITHUB_PROJECTS` only (four servers)

- Pros: removes the clearest liability (unused feature + `project` PAT); minimal blast radius.
- Cons: leaves `GITHUB_ACTIONS` as a shared-identity server whose containment benefit is zero; does not reach the Product Owner's ask.

### Option 3: Retire `GITHUB_PROJECTS` and `GITHUB_ACTIONS`; retain `GITHUB_SECURITY` (three servers)

- Pros: removes the dead feature and its PAT; removes a shared-identity server whose only value is fail-closed scoping (recreatable with explicit denies); preserves the one real process-level boundary (`--read-only`) and both identity boundaries; CI triage is already available via the pinned `gh` CLI under `@fpittelo`, matching the MADR-0020 pattern.
- Cons: CI triage loses MCP structured schemas and moves to a gated bash command surface, requiring allowlist and gate updates.

### Option 4: Fold all extended toolsets into one `@fpittelo` server (two servers)

- Pros: fewest processes.
- Cons: loses the `--read-only` process-level guarantee on the secret-exposing surface; makes the destructive `actions_run_trigger` fail-open under the shared `GITHUB_*` allow unless every agent adds explicit denies. Rejected on least-privilege drivers.

## Decision Outcome

Chosen option: **Option 3 — three servers**, because it removes every server that is not load-bearing while preserving both identity boundaries and the one remaining process-level control:

1. **Retire `GITHUB_PROJECTS`.** Remove the server, the `GITHUB_PROJECTS_*` root baseline and per-agent rules, and revoke or downgrade the `project`-scope PAT (`GITHUB_TOKEN_PROJECTS`). Supersedes MADR-0014's server/credential decisions; the roadmap view retires entirely (its execution role was already removed by MADR-0018).
2. **Retire `GITHUB_ACTIONS`.** Remove the server, the `GITHUB_ACTIONS_*` baseline and per-agent rules; serve CI triage via the pinned `gh` CLI (`gh run list`, `gh run view --log`, `gh workflow run`) under `@devops`'s scoped bash allowlist, with `@developer` retaining read-only triage. Supersedes MADR-0011's `GITHUB_ACTIONS` server decision.
3. **Retain `GITHUB_SECURITY`.** `--read-only` remains the only token-independent guard on the surface that reads raw secret material; MADR-0011's `GITHUB_SECURITY` decision stays in force.
4. **Retain `GITHUB` and `GITHUB_CODE_REVIEWER`** unchanged — the base server and the separation-of-duties identity.
5. **Same-change updates (implementation issues):** `opencode.jsonc` MCP block and baselines; `agents/*.md` per-agent rules; `harness/config-validation/check_coach_exclusivity.py` + tests (the machine control); `docs/architecture/arc42/01-context-and-building-blocks.md` §1.1 namespace enumeration and §5 building blocks; the `github-scrum-board` skill; and the `install.sh` secrets template (`GITHUB_TOKEN_PROJECTS` removal).

## Consequences

- **Positive:** five MCP processes become three; one broad-scope PAT and one namespace are retired; two large agent-spec rule sets and their gate entries disappear; the remaining topology maps one-to-one to genuine boundaries (identity SoD, process-level read-only).
- **Negative:** CI triage loses MCP structured schemas and moves to a `gh` bash surface, which is a broader command family than four typed tools; the optional roadmap view is gone entirely; per-agent context size is essentially unchanged (deny-filtering already removed the schemas), so this is a simplification, not a latency win.
- **Mitigations:** `@cyber-security` reviews this design and the resulting specs under MADR-0008 before they finalize — specifically the PAT revocation path and the new `gh run`/`gh workflow` bash surface; the bash allowlist is deny-guarded in the MADR-0020 style (destructive sub-commands such as `gh run delete` machine-denied); `check_coach_exclusivity.py` and its test are updated in the same change so a regression fails CI.
- **Residual risks (to be recorded at acceptance):** the retired `actions_run_trigger` mono-tool residual (MADR-0011) disappears with the server, but the replacement `gh` command surface must be scoped as tightly as the tools it replaces.
