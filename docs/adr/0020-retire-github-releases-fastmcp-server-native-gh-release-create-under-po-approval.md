# MADR-0020: Retire GITHUB_RELEASES FastMCP server — native gh release create under PO approval

- **Status:** accepted
- **Date:** 2026-10-17
- **Deciders:** @fpittelo (PO directive executing the 2026-10-17 architecture audit, issue #341), @architect (author), @devops (implementer)

## Context

MADR-0016 built a home-grown Python FastMCP server (`tools/github-releases-mcp/`) to make the release-object step of the promotion flow agent-executable under the single PO release approval. The server exposed exactly two tools (`GITHUB_RELEASES_create_release`, `GITHUB_RELEASES_update_release`) against `api.github.com`, with the account hard-pinned to `@fpittelo`, a dedicated `GITHUB_TOKEN_RELEASES` credential, a `uv.lock`-pinned dependency set, and a dedicated CI gate (config gate 17: `uv sync --locked`, ruff, `mypy --strict`, `pytest -W error` at ≥ 80% coverage, `pip-audit --strict`).

The 2026-10-17 architecture audit found the cost disproportionate to the risk: the server's entire functional surface is **two REST calls** (`POST /repos/{owner}/{repo}/releases`, `PATCH /repos/{owner}/{repo}/releases/{id}`). That surface was carried by an entire Python package, a project `.venv`, a lockfile, a dedicated CI gate, a whole MCP namespace with a global default-deny baseline plus seven per-agent restatements, and a separate credential name. The `gh` CLI — already pinned and managed by the OS on VIDAR — performs the same two operations natively (`gh release create`, `gh release edit`) under the same `@fpittelo` identity.

The PO release approval gate is unchanged by this decision: `home-governance` Rule 5 remains the SSOT (one explicit `@fpittelo` approval per release, before tagging).

## Decision Drivers

- **KIS & YAGNI (`home-governance` §9):** two REST calls do not justify a Python package + `.venv` + lockfile + CI gate + MCP namespace + credential name.
- **Proportionate quality gates (MADR-0003):** a dedicated supply-chain gate for a two-call wrapper is a control whose cost exceeds the risk it mitigates.
- **Posture simplification:** removing a namespace and its denies is a net reduction in attack surface and configuration — no new grants.
- **Governance continuity:** the PO release approval gate (Rule 5) and the `@devops` sole release authority (release-automation §4 SoD) are unaffected.

## Considered Options

### Option 1: Native `gh release create` under the PO approval (chosen)

- Pros: −1 Python package, −1 `.venv`/lockfile, −1 CI gate, −1 MCP namespace (and its 8 permission restatements), −1 credential name; `gh` is already pinned/managed by the OS; `gh release edit` covers follow-up edits; the PO approval gate is unchanged.
- Cons: release publishing returns to CLI transport with the token injected via environment (`GH_TOKEN="${GITHUB_PERSONAL_ACCESS_TOKEN}"` inline, per the #304 shell-assignment pattern); `gh` has `gh release delete`, which the old server intentionally lacked.

### Option 2: Keep the home-grown server (status quo)

- Pros: zero governance change; the no-delete capability is structural.
- Cons: permanent maintenance tax (package, lockfile, gate, namespace, credential) for two REST calls; contradicts the audit's KIS findings.

### Option 3: Keep the server but drop the dedicated CI gate

- Pros: removes the gate cost.
- Cons: leaves the package, `.venv`, namespace, and credential — the bulk of the tax — in place; a half-measure that keeps the complexity without the gate's (marginal) benefit.

## Decision Outcome

Chosen option: **"Option 1 — Native `gh release create`"**. `@devops` publishes the GitHub Release object with `gh release create` under the single PO release approval, injecting the token inline as `GH_TOKEN="${GITHUB_PERSONAL_ACCESS_TOKEN}"` (the #304 shell-assignment pattern — not the `env` command). `gh release edit` covers follow-up edits. The `GITHUB_RELEASES` MCP server, its namespace, its per-agent permission lines, its credential (`GITHUB_TOKEN_RELEASES`), its package (`tools/github-releases-mcp/`), and its CI gate (config gate 17) are removed.

**Supersession:** this decision supersedes MADR-0016's mechanism (the home-grown server). MADR-0016's *goal* — agent-executable release publishing under the PO approval — is retained and now served by the `gh` CLI. The PO release approval gate is unchanged: `home-governance` Rule 5 remains the SSOT.

**Guardrail (no-delete parity):** the retired server intentionally had no delete capability; `gh` does (`gh release delete`). Agents MUST NOT use `gh release delete`. This is recorded as a bash deny candidate should the PO want machine-enforced parity; absent that, it is an accepted residual mitigated by the approval gate and the `@devops`-only release authority.

## Consequences

- **Positive:** −1 MCP process, −1 namespace (with its global default-deny baseline and seven per-agent restatements), −1 CI gate, −1 credential name, −1 Python package with its `.venv`/lockfile; the release path is a single native CLI call.
- **Negative:** release publishing returns to CLI transport with the token injected via environment; the structural no-delete guarantee is replaced by a documented guardrail.
- **Mitigations:** `gh` is pinned and managed by the OS; the PO approval gate (Rule 5) is unchanged; `gh release edit` covers follow-up edits; the no-delete guardrail is stated here and in `release-automation` §3, with `gh release delete` recorded as a bash deny candidate if the PO wants parity.
