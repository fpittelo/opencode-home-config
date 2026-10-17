# arc42 Architecture Documentation — HOME OpenCode Profile

Architecture documentation for the **HOME OpenCode configuration** (`opencode-home-config`), following the **arc42** template (v8.0) as operationalized by the `arc42-documentation` skill — consolidated into **3 cohesive views** (#342).

**Document status:** active — 3-view layout (consolidation #342). MADR decisions are indexed in the single authoritative index [`docs/adr/README.md`](../../adr/README.md): 21 ADRs total, **19 accepted** (MADR-0012 and MADR-0016 superseded).

## Index

| View | File | Contents | Status |
| :--- | :--- | :--- | :--- |
| 1. Context & Building Blocks | [01-context-and-building-blocks.md](01-context-and-building-blocks.md) | §1 Introduction & Goals · §2 Architecture Constraints · §3 System Context & Scope (C4 Context) · §4 Solution Strategy · §5 Building Block View (C4 Container) | consolidated |
| 2. Runtime & Delivery | [02-runtime-and-delivery.md](02-runtime-and-delivery.md) | §1 Runtime View (sprint loop) · §2 Deployment View | consolidated |
| 3. Cross-cutting & Security | [03-cross-cutting-and-security.md](03-cross-cutting-and-security.md) | §1 Cross-cutting Concepts · §2 Quality Requirements · §3 Risks & Technical Debt · §4 Glossary · §5 Architecture Decisions (MADR pointer) | consolidated |

## Maintenance Rules

- Update triggers per view/section: see the `arc42-documentation` skill §4.
- An architectural change and its arc42 update travel in the **same PR**.
- A MADR that changes an operational mechanism MUST update arc42 + README in the same PR (#264).
- Governance SSOT remains the `home-governance` skill; this documentation describes, it does not govern.
