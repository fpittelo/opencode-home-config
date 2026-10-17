# MADR-0016: Home-grown GITHUB_RELEASES Python FastMCP server for agent-side release publishing

- **Status:** superseded (superseded by MADR-0020)
- **Date:** 2026-10-17
- **Deciders:** @fpittelo (PO — Option A selection), @architect (spec), @cyber-security (MADR-0008 security approval with 11 conditions)

## Context

The HOME promotion flow (release-automation) ends with publishing the GitHub Release object — the one step no agent can perform: the pinned official `github/github-mcp-server` v2.0.2 exposes only three read-only release tools (`list_releases`, `get_latest_release`, `get_release_by_tag`), verified by live MCP enumeration and a 91-tool `--toolsets=all` probe of the pinned binary. Upstream has an open feature request (`github/github-mcp-server#2853`) and an unmerged closed PR (#2854, author deleted).

The remediation was initially groomed as implementing those tools in Go and contributing them upstream (#319). **The PO ruled the HOME stack Python-only (2026-10-17): no Go toolchain, no Go code — #319 closed as not_planned.** Three Python-compatible architectures were then evaluated.

## Decision Drivers

- PO friction: release publishing is the last manual step in the autonomous promotion loop (issue #308's original thesis).
- **Stack constraint (PO, binding): Python-only** — no Go toolchain or code is to be introduced, executed, or maintained.
- Governance: new MCP server = MADR-0008 Tier-1 security-impact routing (@cyber-security review blocks spec finalization); namespaced-server pattern per MADR-0011/0014 (root default-deny, sole-agent allow, exclusivity-checker enforcement).
- SoD (release-automation §4): publishing authority is `@devops`; `@architect`/`@developer` hold none.
- KIS/YAGNI (#180): smallest server that satisfies the ACs; no destructive capability that has never been used.
- Baseline reality checked by @cyber-security: there is **no existing in-process Python MCP server** in this repo (five GITHUB servers are the pinned upstream binary; coach runs Docker) — the new server is a **new artifact class** with its own supply chain (`uv` lockfile, `pip-audit` gate), and CI currently has no Python project gate for this repo (`run.sh python` skips; stdlib-only harness conventions).

## Considered Options

### Option 1: Upstream Go contribution (closed #319 path)

- Pros: fixes the gap for everyone; no home-maintained server.
- Cons: requires Go ≥ 1.26.8 + golangci-lint toolchain — **violates the PO's binding Python-only constraint**; upstream merge timeline uncontrollable; the machine lacks the toolchain (verified).
- Outcome: rejected 2026-10-17 (#319 closed not_planned; recon preserved in the issue).

### Option 2: `gh` CLI automation

- Pros: near-zero build effort after one `gh auth login`.
- Cons: stores its OAuth token on disk (`~/.config/gh/hosts.yml`) — readable by today's granted `cat *` rule, so it requires another permission change (new deny patterns) AND hands agents a fully-general network-capable credentialed binary with no namespace isolation. Weaker than a scoped MCP server on every security axis at comparable effort. Rejected by the security posture.

### Option 3: Home-grown `GITHUB_RELEASES` Python FastMCP server (chosen)

- Pros: inside the blessed stack (FastMCP patterns, Pydantic v2, httpx); fixes the gap permanently for HOME releases; fits the namespaced-server governance suite out of the box (MADR-0011 precedent); reuses an already-scoped credential via a separately-named env var seam; STRIDE surface is small and testable (two tools, one fixed host, pinned methods).
- Cons: a new home-maintained artifact (first Python MCP server in the portfolio) with its own dependency-audit and pin story; release authority still scoped to one agent (`@devops`); draft-release visibility and identity footguns documented but not eliminable.

### Option 4: Accept the manual click permanently (status quo)

- Pros: zero work.
- Cons: does not address the PO driver; the friction anniversary recurs every release. Rejected as non-responsive.

## Decision Outcome

Chosen option: **"Home-grown `GITHUB_RELEASES` Python FastMCP server"**, because it is the only option that satisfies the binding Python-only constraint while closing the last manual promotion step within the established namespaced-server governance pattern.

The server (`tools/github-releases-mcp/`, stdio, Python 3.12, FastMCP):

- **Exactly two tools** (flat names): `create_release` (POST `/repos/{owner}/{repo}/releases`) and `update_release` (PATCH by `release_id`, only-send-provided-fields). Separate tools, not a consolidated writer (per-tool audit granularity, hint annotations, no method-enum smuggling surface). **No `delete_release`** (destructive + never used), **no** asset upload — both out of scope by YAGNI.
- **Owner hard-pinned to `fpittelo`** (no `owner` input exists on any tool); client pinned to `https://api.github.com` with `follow_redirects=False`, `trust_env=False`, timeout 30 s; bounded retry (≤ 2, exponential backoff, 5xx/429 only, honors `Retry-After`).
- **Credential:** separate env var `GITHUB_TOKEN_RELEASES` via `{env:...}` only, `SecretStr`-wrapped, never logged; errors return sanitized `{status, github_message}` only. Honest caveat: while the value initially duplicates the existing host PAT (`Contents:write` demonstrated by PR merging), the separate name is a **rotation seam, not isolation** — the ideal end-state is a dedicated release-scoped PAT.
- **Permission matrix:** root `"GITHUB_RELEASES_*": "deny"`; `agents/devops.md` alone gets allow (SoD); the six other agent specs gain the deny line; `check_coach_exclusivity.py` + its unittest extended (`NAMESPACE_POLICIES`/`NAMESPACE_CASES`).
- **Supply chain:** `pyproject.toml` + committed `uv.lock`; gate = `uv sync --locked` + `ruff` + `mypy --strict` + `pytest -W error` (coverage ≥ 80%) + **`pip-audit --strict`**, wired as a new numbered config-gate step (17/17) and CI port — without repointing `run.sh`.

## Consequences

- **Positive:** the promotion flow's release step becomes agent-executable by `@devops` end-to-end; gap-to-upstream becomes irrelevant (if upstream ships release-write tools in a future pin, adoption is optional); the first Python-server pattern (lockfile + audit gate + exclusivity wiring) is reusable for future home MCP tools.
- **Negative:** one more home artifact to maintain (pin/lock/audit surface); friction reduction scoped to releases only (no delete capability — mis-published releases still need PO action); `@devops` publishes under the `@fpittelo` identity (author = token owner).
- **Mitigations:** 11 testable security conditions (below) enforced by tests and gate 17; structured tool-call logging (tool, repo, tag, release id, outcome — never token/body) addresses repudiation; draft-release non-world-readability documented as an agent-convention control; GO-lint upstream recon (#2853/#2854 shape) retained as reference for a future upstream-first re-attempt should the PO ever lift the Python-only constraint.

**@cyber-security conditions (2026-10-17, APPROVED — binding, test-enforced):**
(1) owner hard-pinned, no `owner` input; (2) `release_id` `^\d+$`; (3) `tag_name`/`target_commitish` git-ref-safe charset; (4) `repo` `^[A-Za-z0-9._-]{1,100}$` sans `..`; (5) `body` ≤ 125 000 / `name` ≤ 256, control chars rejected, `make_latest` enum; (6) httpx client pinned (base URL, no redirects, no env proxies, no URL/header args); (7) separate token var, `SecretStr`, never logged, sanitized errors; (8) exactly two tools, fixed POST/PATCH; (9) complete permission matrix + exclusivity checker extension; (10) `uv.lock` committed + `pip-audit --strict` + ruff/mypy/pytest green via new gate step; (11) bounded retry. Implementation in #323 (Slice B); this record satisfies the "MADR before implementation" ordering.
