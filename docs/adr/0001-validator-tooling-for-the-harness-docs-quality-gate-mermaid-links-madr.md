# MADR-0001: Validator tooling for the harness docs quality gate (mermaid, links, MADR)

- **Status:** accepted
- **Date:** 2026-09-20
- **Deciders:** @architect, @fpittelo

## Context

STORY-04 (#61) requires deterministic documentation validation — Mermaid syntax, relative markdown links, and MADR header schema — executed inside the hardened harness (non-root UID 1000, dropped capabilities, read-only root, bounded resources, `--network=none` at validation runtime) before any PR merges to `dev`. The tooling strategy had to be fixed before the validator implementation (this decision is the designated first MADR per arc42 §9 back-index, and the story dogfoods the workflow delivered by STORY-03 #60).

## Decision Drivers

- **KIS:** least custom code — prefer standard, pinned tooling over hand-rolled parsing.
- **Determinism:** the zero-tolerance CI gate (0 warnings / 0 failures) requires reproducible validator results.
- **Harness security flags:** validators must run non-root, read-only root FS, and **without network egress** at validation time (Swiss nLPD posture).
- **CI runtime and image weight:** gate must be fast enough for every PR; image size is a secondary, tolerated cost.

## Considered Options

### Option 1: mermaid-cli (`mmdc`) + Python-stdlib link/MADR checks in a single docs-validator image

- Pros: reference validator (catches syntax and render-level errors); no custom parser code; pinned Docker image = reproducible; chromium downloaded at image build time, validation runs offline; link + MADR checks need only the Python stdlib (zero dependencies).
- Cons: heavy image (Node 22 + chromium, ~700 MB–1 GB); mmdc requires the container to run chromium (mitigated by harness flags).

### Option 2: `mermaid.parse()` via Node with a jsdom shim

- Pros: much lighter than chromium; no browser dependency.
- Cons: non-standard usage — mermaid is browser-oriented; shim code is custom maintenance surface (anti-KIS); syntax-level only (weaker than render validation).

### Option 3: Regex/structural linting of Mermaid blocks

- Pros: trivial, tiny image.
- Cons: too weak — false positives/negatives; does not satisfy AC1's "invalid block" detection meaningfully.

### Option 4: External/SaaS validation services

- Pros: zero local tooling.
- Cons: network egress at validation time (violates harness security flags and privacy posture); non-deterministic availability; Swiss nLPD data-boundary risk.

## Decision Outcome

Chosen option: **"Option 1 — mermaid-cli + Python-stdlib checks in a single `harness/docker/Dockerfile.docs-validator` image"**, because it uses standard, pinned tooling (KIS), validates at render level deterministically, and respects the harness security flags: all network use is confined to image build time; validation runtime is fully offline. Relative-link checking (not external URLs) is deliberate — external URL checks would require egress, which the security flags forbid.

## Consequences

- **Positive:** one image, three validators, zero custom parser code; AC1/AC2/AC3 of #61 map 1:1 to three small entry scripts; reproducible in CI and locally.
- **Negative:** image weight (chromium) and build-time network requirement; external-URL link rot is NOT detected (out of scope by design).
- **Mitigations:** image built rarely and cached (GHCR, same pattern as the existing harness runners); link checking limited to repository-relative targets, which cover the governance need (internal docs consistency); revisit external-URL checking only if a concrete need emerges.
