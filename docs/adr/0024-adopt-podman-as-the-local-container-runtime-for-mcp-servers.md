# MADR-0024: Adopt Podman as the local container runtime for MCP servers

- **Status:** proposed
- **Date:** 2026-11-13
- **Deciders:** @fpittelo (Product Owner), @architect; @cyber-security (MADR-0008 review — pending)

## Context

The HOME profile assumes a local container runtime without owning or verifying it. On the host it targets (VIDAR, WSL2, uid 1000) **no container runtime is installed at all** — no `docker`, `podman`, or `nerdctl` binary on `PATH` or in `/usr/bin`. Two consequences follow, both verified:

| Fact | Evidence |
| :--- | :--- |
| `COACH_DEV` is declared `"enabled": true` with `command: ["docker", "run", "-i", "--rm", …]` | `opencode.jsonc:113–127` |
| `COACH_QA` / `COACH_MAIN` use the same pattern (toggle pattern, one enabled at a time) | `opencode.jsonc:129–159` |
| `install.sh` runs under `set -euo pipefail` and calls `docker pull` **unguarded** | `install.sh:2`, `install.sh:132–139` |
| No runtime presence check anywhere in `install.sh` (contrast: the `openssl` guard) | `install.sh:118–121` |
| Docker is listed as an external assumption, not an owned prerequisite | `docs/Admin-and-User-Guide.md:58` |

So the "idempotent Linux/WSL2 bootstrap" **hard-aborts on its own target host**, and the Coach MCP cannot spawn. The failure is undiagnosable from the docs, which treat the runtime as a given.

The blast radius is narrower than the request's wording suggests. In the MCP layer only the three `COACH_*` servers use containers; `GITHUB` / `GITHUB_CODE_REVIEWER` / `GITHUB_SECURITY` are pinned native binaries (MADR-0002 decision point 3), `BROWSER` is `npx @playwright/mcp` (MADR-0009), and `openrouter` is a remote streamable-HTTP endpoint. Two further surfaces touch the runtime: the `harness/run.sh` container fallback (four `docker run` call sites, reachable only when the host has neither `uv` nor a project `.venv` — MADR-0003/#256), and the permission deviation registry, which still asserts a `docker *` allow for `@devops` that `agents/devops.md` itself documents as **redundant** under root inheritance (MADR-0019).

Prior decisions in force: MADR-0002 D3 (pinned native transport for GitHub; install-time pre-pull for Coach so *"session start never waits on a registry fetch"*), MADR-0003 (proportionate gates — the per-PR pipeline is deliberately zero-Docker), MADR-0004 (allow-by-default bash posture with a catastrophic deny tail), MADR-0019 (root-inheritance bash baseline). The Product Owner's directive (2026-11-13) is to run the MCP servers on **Podman instead of Docker**, and to include the harness fallback and the permission reconciliation in scope.

## Decision Drivers

- **Owned prerequisite (fail-closed bootstrap):** `install.sh` must detect the runtime it depends on and fail with an actionable message — never abort on an unexplained `docker: command not found`.
- **Least privilege:** prefer a runtime without a root-equivalent daemon socket; rootless Podman maps container root to the invoking uid and exposes no `docker.sock` analogue.
- **No regression of MADR-0002 D3:** session start must not gain a registry round-trip or a new offline failure mode. Image freshness stays a separate, owned concern (#412/#413).
- **KIS / YAGNI (#180):** migrate only what actually runs containers locally. CI runner images and workflows are Docker-native and gain nothing.
- **Swiss nLPD / credential minimization:** any registry authentication must not introduce a credential file readable by agents (MADR-0010 posture).
- **MADR-0008 security routing:** an execution-substrate change plus a permission-surface change requires `@cyber-security` review against `arc42/03-cross-cutting-and-security.md` §1 and §3 **before** spec finalization.

## Considered Options

### Option 1: Status quo — Docker as an unverified assumption

- Pros: zero work; no new decisions.
- Cons: the bootstrap aborts on VIDAR; the documented prerequisite is unenforced, so the failure surfaces far from its cause; retains a root-equivalent daemon socket; ignores the PO directive.

### Option 2: Keep Docker, add only the presence guard

- Pros: minimal diff; fixes the abort and the Coach spawn failure; zero migration risk; keeps operator muscle memory.
- Cons: keeps the root daemon and its root-equivalent socket on a workspace that already holds profile secrets; requires the daemon to be running as a service under WSL2; does not satisfy the PO directive.

### Option 3: Rootless Podman for the local container surfaces (MCP layer + harness fallback); CI stays Docker

- Pros: daemonless and rootless — no root-equivalent socket, container root maps to uid 1000; the invocation is a **drop-in** for our exact usage (`podman run -i --rm -e VAR <image>`, stdio only — no `-t`, no ports, no volumes), so the migration is a token change; `--pull=newer` exists as a future runtime-level freshness lever that Docker lacks (held back by D2); one verified prerequisite replaces an unverified assumption; CI keeps its Docker-native tooling unchanged.
- Cons: a new runtime to install and maintain on the host; rootless operation under WSL2 needs cgroup v2 plus a user systemd session (or an explicit cgroup manager) and is **unproven on VIDAR** until probed; two runtimes coexist in the ecosystem (Podman locally, Docker in CI), a documentation-divergence risk; operator muscle memory changes.

### Option 4: Podman for everything, including CI runner images and workflows

- Pros: one runtime everywhere; conceptual purity.
- Cons: GitHub-hosted runners are Docker-native and the workflows depend on `docker/setup-buildx-action`, `docker/login-action`, `docker/metadata-action` and `docker/build-push-action`. Rewriting that pipeline is high cost for zero functional benefit, and touches the release path. Rejected as over-delivery.

### Option 5: Drop containers for the Coach MCP (native install from source)

- Pros: eliminates the runtime dependency entirely for the MCP layer.
- Cons: the Coach server is a separate repository shipping container images on its own promotion tags (`dev`/`qa`/`latest`); a native install would duplicate that release path, add a build toolchain to the host, and relocate the freshness problem rather than solve it. Out of scope for this decision.

## Decision Outcome

Chosen option: **Option 3 — rootless Podman for the local container surfaces, CI unchanged.** It removes an unowned prerequisite, improves the privilege boundary, and satisfies the directive while keeping the diff proportional.

**D1 — Runtime.** Podman (rootless, daemonless) is the local container runtime for the three `COACH_*` MCP servers and for the `harness/run.sh` container fallback. The GitHub servers stay on the pinned native binary (MADR-0002 D3), `BROWSER` stays on pinned `npx` (MADR-0009), and `openrouter` stays remote. CI workflows and the images under `harness/docker/**` remain Docker-based — explicitly out of scope.

**D2 — Image freshness (PO decision, 2026-11-13).** The Coach servers use **`--pull=missing`**. This preserves MADR-0002 D3's property that session start never waits on a registry fetch, and matches today's effective behaviour. Image freshness remains owned by #412/#413, not by this record.

Rejected alternative, recorded for auditability: **`--pull=newer`** would fix staleness at the runtime level and is a capability Docker does not have — but it adds a registry round-trip to every session start plus a new offline failure mode for the Coach MCP, knowingly breaking the D3 baseline. `--pull=always` and floating tags are rejected outright: both defeat the supply-chain posture of a pinned, verified image reference. If #412 concludes that runtime-level freshness is worth the latency, `--pull=newer` is the mechanism to revisit — this record deliberately leaves that door documented rather than closed.

**D3 — Permission posture.** No blanket `podman *` allow is introduced. The root `"*": allow` baseline already covers the invocation, as it does for `docker` today. Any future tightening must be a **scoped** set (`podman run*`, `podman pull*`, `podman ps*`, `podman logs*`), never a blanket allow. Container runtimes carry sub-command surface that a *command-family* allow silently inherits, and three are explicitly in scope for review: `podman system service` (recreates a Docker-API-compatible socket — the exact escalation path rootless mode is meant to remove), `podman unshare` (user-namespace mapping with chown to arbitrary UIDs), and `podman machine` (spawns a VM). Parity must hold for `podman run --env-file x.env` against the root `*.env*` deny (the previously documented `docker run --env-file` case). The stale `docker *` deviation, `AGENT_DEVIATIONS` and the gate-16 regression suite are reconciled in #419 under `@cyber-security` review; if that review finds the root baseline sufficient, the correct outcome is a recorded accepted residual — not invented rules.

**D4 — Runtime ownership: verify, do not provision.** `install.sh` **verifies** the runtime with a fail-closed `command -v` check and an actionable message naming the expected runtime and the remediation command, in the style of the existing `openssl` guard. It does **not** install it: package installation requires root, the profile's bash posture denies `sudo*`, and package-manager variance across hosts would turn a config bootstrap into a system-provisioning script. Provisioning remains a documented manual prerequisite (Admin guide) with probe evidence recorded on #416. The install-time pre-pull from MADR-0002 D3 is retained, re-expressed for the chosen runtime.

## Consequences

- **Positive:** the bootstrap stops aborting on its target host and fails legibly when the runtime is absent; the local container surface loses its root-equivalent daemon socket; the local MCP and harness fallback share one runtime; the CI pipeline and release path are untouched; the freshness question is separated from the substrate question instead of being settled by a flag.
- **Negative:** two runtimes coexist (Podman locally, Docker in CI), creating a standing documentation-divergence risk; the host gains a prerequisite to install and keep working; rootless-under-WSL2 is assumed rather than proven until #416's probe lands; operator habits and the `docker-expert` vocabulary drift from the actual local command.
- **Mitigations:** #416 must paste probe evidence (`podman info` rootless, cgroup manager, a container run) before D1 is relied upon; documentation parity travels in the same PR as each change (#417, #418); `harness/run.sh` resolves the runtime from a single overridable variable so Docker-based hosts and CI keep working; #419 reconciles the permission registry under `@cyber-security` review; the arc42 deployment and cross-cutting views carry this record's status so the documentation never claims more than is merged.
- **Residual risks:**
  1. **Rootless is not a defense against same-uid attack.** An escape from a rootless container yields uid 1000 — which owns the profile secrets files. This improves on container-root escalation but does not change the same-uid exposure already accepted in MADR-0010 (RR1).
  2. **`podman system service` remains a latent escalation path** if ever allowed: it re-creates the Docker-API socket pattern. Hence D3's prohibition on blanketing the runtime family.
  3. **Image freshness stays unaddressed here** by construction (D2); stale `:latest` Coach images remain possible until #412/#413 lands, and this record does not pretend otherwise.
  4. **The harness fallback is rarely exercised** (native-first path dominates), so the migrated container path may be under-verified; #418 must keep its regression suite meaningful rather than merely adapted.

## Security Review (MADR-0008)

Review by `@cyber-security` against `arc42/03-cross-cutting-and-security.md` §1 (cross-cutting security) and §3 (risks & technical debt) is **required before spec finalization** and is **pending** at the time this record is proposed. Scope of the review: the execution-substrate change (D1), the freshness policy's negative consequences (D2), the container-runtime permission posture and the `podman system service` / `podman unshare` / `podman machine` surface (D3), and the verify-not-provision decision's root boundary (D4). The verdict and any conditions must be recorded in this section before the record moves to `accepted`.
