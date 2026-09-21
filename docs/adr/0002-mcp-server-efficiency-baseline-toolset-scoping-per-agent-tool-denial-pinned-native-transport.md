# MADR-0002: MCP server efficiency baseline: toolset scoping, per-agent tool denial, pinned native transport

- **Status:** accepted
- **Date:** 2026-09-21
- **Deciders:** @architect, @fpittelo

## Context

The HOME OpenCode configuration (`opencode.jsonc` + 7 agents + 12 skills) produces quality output but feels slow. The architecture review requested under #56 identified four latency sources, two of which are architectural and MCP-related:

1. **Per-turn tool-schema bloat.** Every enabled MCP server advertises its full tool catalog into the system prompt of every agent on every turn. The config currently enables four servers: `GITHUB` (~50 tools), `GITHUB_CODE_REVIEWER` (~50 tools), `COACH DEV` (~15 tools), and the remote `openrouter` server (~25 tools). Most agents need only a fraction of these: e.g. `@developer` never queries the OpenRouter model catalog, and no SCRUM agent ever calls Coach fitness tools. Prompt size directly drives time-to-first-token, per-turn latency, and token cost.
2. **Session-start container cold starts.** Three MCP servers are spawned via `docker run -i --rm` on every session (two `ghcr.io/github/github-mcp-server:latest` instances, one `ghcr.io/fpittelo/coach:dev`), adding seconds before the first prompt is usable. The `:latest` tag is additionally a moving, non-reproducible target.

Two further constraints shape the decision:

- The Coach MCP server names contain a space (`COACH DEV`, `COACH QA`, `COACH MAIN`). Permission patterns are matched against namespaced tool names; a space in the server prefix makes per-agent allow/deny patterns fragile and hard to validate. The Product Owner has additionally mandated that **Coach MCP tools must be available to the `@coach` agent only**.
- Whether opencode's `permission: deny` on an MCP tool pattern merely blocks execution or also removes the schema from the prompt is not yet empirically verified on this installation. Plan-mode behavior (denied `edit` is not offered to the model) suggests schemas are removed, but this MUST be confirmed as part of implementation (see Consequences / Mitigations).

Non-goals (YAGNI): changing per-agent model assignments, rewriting agent prompts, altering the SoD two-identity GitHub design (#83), or touching the harness quality gates.

## Decision Drivers

- **Responsiveness without quality regression:** the Product Owner is satisfied with output quality; only latency and efficiency may change.
- **KIS / YAGNI:** prefer configuration levers over new machinery; one variable at a time, measured.
- **Reproducibility:** pinned, verifiable dependency versions (same supply-chain posture as the harness images).
- **Local isolation posture:** MCP servers handling GitHub tokens run locally under our control; secrets must not transit third-party hosted MCP endpoints unnecessarily (Swiss nLPD-aligned data minimization).
- **Least privilege per agent:** each agent sees only the tools its role requires (extends the SoD pattern of #83).

## Considered Options

### Option 1: Status quo (Docker `:latest`, full tool catalogs, all tools advertised to all agents)

- Pros: zero work; known-good behavior.
- Cons: maximal per-turn token overhead on every agent; ~2–6 s session-start penalty; non-reproducible `:latest` images; Coach tools visible to all agents contrary to the new Product Owner mandate.

### Option 2: Configuration-only baseline (toolset restriction + per-agent denial + pinning, Docker retained)

- Pros: no new install machinery; cuts the majority of schema bloat via `GITHUB_TOOLSETS` on the upstream server and per-agent `permission` denies; pinning + `install.sh` pre-pull removes registry drift.
- Cons: retains Docker cold-start latency at session open; does not fully address startup cost.

### Option 3: Full baseline — Option 2 plus native binary transport for github-mcp-server

- Pros: eliminates both container cold starts for the two GitHub MCP servers (binary startup is milliseconds); pinned version + SHA256 checksum verification in `install.sh` preserves supply-chain hygiene; keeps tokens local; toolset restriction and per-agent denial still apply.
- Cons: `install.sh` gains a version-pinned binary install step (new maintenance surface); upgrades become deliberate (which is also a pro).

### Option 4: Hosted remote GitHub MCP endpoint (`type: remote` with PAT header)

- Pros: zero local processes; always up to date.
- Cons: PAT transits to a hosted endpoint (data-minimization concern); hard network dependency for all SCRUM board operations; less control over version and toolset behavior. Rejected on driver 4.

### Option 5: Dynamic toolsets (`GITHUB_DYNAMIC_TOOLSETS=1`)

- Pros: smallest possible schema surface (~3 meta-tools); model enables toolsets on demand.
- Cons: adds discovery round-trips inside autonomous sprint loops (latency moved, not removed); behavior less predictable for unattended agents; immature operational track record. Rejected for now; revisitable later.

## Decision Outcome

Chosen option: "Option 3 — Full baseline", because it is the only option that addresses both architectural latency sources (schema bloat and cold starts) while preserving local isolation, reproducibility, and output quality:

1. **Toolset restriction at the source.** `GITHUB` exposes only the toolsets the SCRUM workflow uses (candidate set: `context,repos,issues,pull_requests,labels,search,actions`); `GITHUB_CODE_REVIEWER` exposes only `context,repos,pull_requests`. Exact toolset names are verified against the upstream `github-mcp-server` documentation during implementation.
2. **Per-agent tool denial.** `openrouter_*` is denied for all agents except `@architect` (and any agent with a demonstrated need); all `COACH_*` tools are denied for every agent except `@coach`. Coach MCP servers are renamed `COACH DEV/QA/MAIN` → `COACH_DEV/COACH_QA/COACH_MAIN` so permission patterns are unambiguous.
3. **Pinned, pre-pulled, verified transport.** `github-mcp-server` runs as a native binary installed by `install.sh` at a pinned version with SHA256 checksum verification; the Coach server remains Dockerized but pinned to an immutable tag and pre-pulled by `install.sh`.
4. **Measured rollout.** A baseline measurement (session-start time, per-turn prompt token counts) is captured before the first change lands; each subsequent change is validated against it.

## Consequences

- **Positive:** materially smaller system prompts (estimated −40–60 % MCP schema tokens on SCRUM agents); near-instant GitHub MCP startup; reproducible MCP versions; Coach and OpenRouter tools visible only where needed (least privilege); quality behavior unchanged.
- **Negative:** `install.sh` becomes more complex (binary fetch + checksum + pre-pull); toolset lists and deny patterns are a new config surface that can silently drift from workflow needs; upgrades of `github-mcp-server` require a deliberate version bump PR.
- **Mitigations:** (a) implementation begins with an empirical check that `permission: deny` removes MCP schemas from the prompt — if it does not, per-agent denial is dropped and toolset restriction remains the lever (recorded as a follow-up note on this ADR); (b) a single issue owns the baseline measurement so each subsequent PR demonstrates its delta; (c) toolset/deny config is reviewed in the same PR flow as all config changes (zero-warning CI + `@code-reviewer` approval); (d) if a denied tool is later needed by an agent, the fix is a one-line permission change — deliberately cheap to reverse.

## Follow-up Notes

**2026-09-21 — Baseline measurement (#106) empirical findings:**

1. **Mitigation (a) resolved: `permission: deny` DOES remove MCP tool schemas from the prompt.** Controlled comparison: the built-in `build` agent (no denies) receives all `COACH_DEV_*` tools; the `@architect` session (denies `GITHUB_CODE_REVIEWER_*`) receives zero tools from that server while retaining all 45 `GITHUB_*` tools. Per-agent denial is therefore a valid schema-reduction lever.
2. **Toolset-restriction scope corrected.** The upstream default toolsets are already `context,repos,issues,pull_requests,labels` (45 tools, 127 KB schema) — approximately the SCRUM set assumed in this ADR. The toolset lever therefore applies mainly to `GITHUB_CODE_REVIEWER` (`context,repos,pull_requests` → 32 tools, 82 KB). The dominant per-agent wins are denying Coach (23 tools, 41 KB) and OpenRouter (~22 tools) schemas for agents that never use them.
3. **Measured anchors (opencode 1.18.31):** trivial first turn = 35,289 tokens total, of which ~33.6 K is fixed system+schema overhead; session start 12.0 s cold / 7.3–7.8 s warm; container spawns ~0.6 s per `github-mcp-server` and ~1.5 s for `coach:dev` (Python). Full report: comment on #106.
