# Decision Log

One-line record for **reversible, low-blast-radius** decisions that do not warrant a MADR. The log right-sizes decision recording: it keeps the MADR index for decisions that are hard to reverse, cross-repo, or security-impacting, and gives everything else a cheap, greppable record.

## Decision-class rubric

| Class | Recorded where |
| :--- | :--- |
| Model roster assignment changes; permission-line tweaks without security impact; image/pin bumps; workflow-cosmetic changes; doc structure moves | **Decision log** — one line: `YYYY-MM-DD — <title> — <one-sentence rationale> — <ref>` |
| Hard to reverse, cross-repo, security impact (MADR-0008 routing: new MCP tools, API integrations, permission changes, auth flows), lifecycle/policy changes | **MADR** — unchanged bar, unchanged `madr-adr` workflow |

Security-impact decisions always take the MADR path (MADR-0008 routing unchanged): the log never weakens that bar.

## Entry format

`YYYY-MM-DD — <title> — <one-sentence rationale> — <ref>`

## Entries

- 2026-11-21 — Introduce the one-line decision log — Reversible documentation-structure change that right-sizes decision recording without touching the security-impact MADR bar — #480
- 2026-11-22 — Bump Rust harness runner to rust:1.100.0-slim-bookworm and pin cargo-audit@0.23.0 / cargo-deny@0.22.0 — Resolves cargo-deny 0.22.0 MSRV >= 1.95.0 build failure and eliminates unpinned crates.io drift in Dockerfile.rust — #477
- 2026-11-22 — Bump pinned github-mcp-server native binary v2.1.0 -> v2.2.0 — Adopts upstream v2.2.0 (completion/validation bugfixes and secret-scanning hide_secret option; opt-in skills and copilot_automations remain inactive) under MADR-0002 D3 / MADR-0026 — #495
