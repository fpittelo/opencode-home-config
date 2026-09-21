# MADR-0003: Proportionate quality gates — CI and harness simplification (KIS/YAGNI)

- **Status:** accepted
- **Date:** 2026-09-21
- **Deciders:** @fpittelo, @architect

## Context

This repository is a **configuration/docs repository** (markdown agents and skills, one JSONC file, `install.sh`, architecture documentation) with no application code and no third-party dependencies. Nevertheless, successive hardening sprints (#86, #89, #61, #107, #110) accreted a delivery pipeline gated like a multi-tenant SaaS product. The Product Owner judged the autonomous delivery loop **impaired by pipeline slowness and disproportionate security ceremony**, violating KIS and YAGNI, and mandated a return to simplicity, performance, speed and efficiency ("Simplicity & Velocity", 2026-09-21).

Measured evidence (2026-09-21, `dev` @ 3fb0c94):

| Cost driver | Per-PR cost | Notes |
| :--- | :--- | :--- |
| `docs-quality-gate` job | Docker pull of ~1.5 GB image (Python 3.12 + Node 22 + Debian Chromium + mermaid-cli) + hardened container boot, to render 158 Mermaid blocks headless | `check_links.py` and `check_madr.py` run natively in **0.035 s / 0.019 s** — only the render check needs the image |
| `secret-scan` job | Docker pull of **unpinned** `zricethezav/gitleaks:latest` + `fetch-depth: 0` → full history re-scan on every PR | Unpinned `:latest` contradicts the repo's own pinning policy (#107) |
| Job fan-out | 4 jobs → 4 × runner bootstrap + checkout | Wall time = slowest job |
| `harness-image-build.yml` | Builds 3 images on every push touching `harness/docker/**` | Runner images serve *other* repositories and change rarely |
| Local pre-flight (`harness/run.sh`) | Container cold start + image pull + volume warm-up | For this repo the **deps** phase SKIPs (no `pyproject.toml`/`Cargo.toml`) but the **gate** phase still pulls and boots the runner image — pure ceremony |

Two observations sharpened the diagnosis: (1) the Docker security flags themselves cost ~zero runtime — the real costs are image pulls, job fan-out and full-history scans; (2) the pipeline was security-*oriented* but not consistently secure (unpinned gitleaks), while the two real open security risks (#122 coach secret-read, #123 blanket bash allows) sat unstarted in the backlog.

Non-goals: abandoning the zero-warning merge gate, the 3-branch lifecycle, PR review or the DoD — these are the delivery fabric, not the bottleneck.

## Decision Drivers

- **Delivery velocity:** the autonomous sprint loop must not wait minutes per PR on ceremony.
- **KIS / YAGNI (codified):** cost of a control must be proportional to the risk it mitigates; do not build machinery for needs that do not exist (no deps → no dependency audits; render-level validation not needed at every-PR cadence).
- **No reduction in effective security coverage:** secrets are still scanned on every PR (diff-scoped); full-history and render-level checks move to a slower cadence, not to the trash.
- **Reproducibility retained where it matters:** pinned tools everywhere (the unpinned `gitleaks:latest` is fixed by this decision).

## Considered Options

### Option 1: Status quo (4 jobs, Docker in per-PR path, full-history scan per PR)

- Pros: zero work; no behavior change.
- Cons: minutes of wall time per PR across ~10 issues per sprint; 1.5 GB image pulls; full-history rescans of an unchanged past; explicitly rejected by the Product Owner.

### Option 2: Tune the existing pipeline (caching, pinning, smarter image tags)

- Pros: incremental; keeps the current architecture.
- Cons: keeps Docker in the per-PR path; image-tag derivation logic (#118) is new machinery to solve a problem that only exists because the image is pulled per PR; complexity budget spent on optimizing ceremony.

### Option 3: Proportionate gates — single native per-PR job + scheduled/pre-release deep validation

- Pros: per-PR pipeline is one job, zero Docker, < 90 s; deep checks (full-history secrets, Chromium render validation, image builds) run where their latency is irrelevant (weekly cron + qa → main promotion); removes moving parts instead of adding them.
- Cons: a render-level Mermaid defect or a pre-existing secret can land on `dev` undetected up to the next deep run; the native Mermaid check must be syntax-level, not render-level.

### Option 4: Remove the docs and secret gates entirely

- Pros: fastest possible pipeline.
- Cons: gives up real, cheap protections (diff-scoped gitleaks is seconds; the stdlib validators are 0.05 s); violates the no-coverage-reduction driver.

## Decision Outcome

Chosen option: **Option 3 — Proportionate gates**, approved by the Product Owner as decisions D1–D5 on 2026-09-21:

1. **D1 — Slim per-PR pipeline:** collapse the 4 CI jobs into a **single native job** (zero Docker, target < 90 s): JSONC validation, agent/skill presence, `install.sh` syntax, **diff-scoped gitleaks via a pinned action** (no `fetch-depth: 0`), native `check_links.py` + `check_madr.py`, a new **native Mermaid syntax check** (`check_mermaid.py --syntax`, no Chromium), and the label-conditional architecture gate merged in.
2. **D2 — Deep validation on a deep cadence:** a new scheduled workflow runs full-history gitleaks, full Chromium render validation (existing docs-validator image) and image-build verification **weekly and on every qa → main promotion**.
3. **D3 — Retire the per-PR docs-validator image pull:** the image survives only in the deep-validation workflow, where a stale tag is harmless by construction (supersedes #118).
4. **D4 — Image builds on demand:** `harness-image-build.yml` triggers on `workflow_dispatch` and `harness-v*` version tags only, not on every `harness/docker/**` change.
5. **D5 — Proportionate Quality Gates principle** (added to governance): *the cost of a control must be proportional to the risk it mitigates. Every-PR gates run natively in < 90 s. Deep checks run weekly and pre-release. Adding a gate requires stating what it catches that existing gates don't (YAGNI); each governance review must identify at least one candidate for removal (KIS).*

Additionally: the local pre-flight harness gains a **native fast path** (host toolchain first, container fallback for reproducibility, security flags preserved in the fallback), and this repository gets a trivial `harness/run-config-gate.sh` (~10 lines) so local pre-flight stops being container ceremony for a repo with no code.

Backlog alignment (Product Owner directive, 2026-09-21): issues not advancing simplicity or speed were closed (#116, #117, #118, #124, #125, #126, #130); retained: #115 (stale config removal), #119 (worktrees), #122 and #123 (uniform, least-privilege permission patterns — consistency is simplicity). Implementation issues: **#132** (this ADR), **#134** (D1 — slim per-PR CI), **#133** (D2–D4 — deep validation + on-demand image builds), **#131** (harness native fast path).

## Consequences

- **Positive:** per-PR wall clock from ~4–6 min to < 90 s; local pre-flight from minutes to seconds; CI moving parts from 4 jobs + 2 image-building workflows to 1 job + 1 scheduled workflow; gitleaks becomes pinned; delivery loop unblocked; the two real security items (#122, #123) move to the front of Sprint 06.
- **Negative:** per-PR Chromium render validation is lost — a Mermaid diagram that is syntactically valid but fails to render can land on `dev`; a secret introduced and *reverted within the same week* could evade the diff scan if the deep run falls between; `check_mermaid.py --syntax` is a new (small) code surface.
- **Mitigations:** (a) the deep-validation gate runs at **every qa → main promotion**, so nothing reaches production without full-history secret scanning and render-level Mermaid validation; (b) weekly cron bounds worst-case detection latency on `dev`; (c) the diff-scoped gitleaks still runs on every PR, so newly *introduced* secrets are caught immediately; (d) the syntax-check mode is stdlib-only and shares the block-extraction code with the render path.

## Follow-up Notes

**2026-09-21 — Backlog triage executed on Product Owner order:** #116, #117, #125, #126 closed as not advancing simplicity/speed; #118 closed as superseded by this ADR; #124 absorbed into #123 (same files); #130 closed with action items triaged (AI-1 dropped — platform squash-only enforcement already mitigates; AI-2 absorbed into #134; AI-3 handled by @scrum-master hygiene). Sprint 06 theme: **Simplicity & Velocity**.
