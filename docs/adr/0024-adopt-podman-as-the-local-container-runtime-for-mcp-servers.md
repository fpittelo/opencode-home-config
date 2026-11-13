# MADR-0024: Adopt Podman as the local container runtime for MCP servers

- **Status:** proposed
- **Date:** 2026-11-13
- **Deciders:** @fpittelo (Product Owner), @architect; @cyber-security (MADR-0008 review — **APPROVE-WITH-CONDITIONS**, 2026-11-13; conditions C1–C8)

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
- **Least privilege:** prefer a runtime without a root-equivalent daemon socket; rootless Podman maps container root to the invoking uid and exposes no `docker.sock` analogue **by default** — an opt-in API socket exists (`podman system service`), which D3 addresses rather than ignores.
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
- Cons: a new runtime to install and maintain on the host; rootless operation under WSL2 needs cgroup v2 plus a user systemd session (or an explicit cgroup manager) and is **unproven on VIDAR** until probed; **identical flags are not identical guarantees** — under rootless mode `--memory`/`--cpus` are enforced only with delegated cgroup controllers (otherwise silently ignored) and `--user 1000:1000` maps to a host *subuid*, changing bind-mount ownership (C6); two runtimes coexist in the ecosystem (Podman locally, Docker in CI), a documentation-divergence risk; operator muscle memory changes.

### Option 4: Podman for everything, including CI runner images and workflows

- Pros: one runtime everywhere; conceptual purity.
- Cons: GitHub-hosted runners are Docker-native and the workflows depend on `docker/setup-buildx-action`, `docker/login-action`, `docker/metadata-action` and `docker/build-push-action`. Rewriting that pipeline is high cost for zero functional benefit, and touches the release path. Rejected as over-delivery.

### Option 5: Drop containers for the Coach MCP (native install from source)

- Pros: eliminates the runtime dependency entirely for the MCP layer.
- Cons: the Coach server is a separate repository shipping container images on its own promotion tags (`dev`/`qa`/`latest`); a native install would duplicate that release path, add a build toolchain to the host, and relocate the freshness problem rather than solve it. Out of scope for this decision.

## Decision Outcome

Chosen option: **Option 3 — rootless Podman for the local container surfaces, CI unchanged.** It removes an unowned prerequisite, improves the privilege boundary, and satisfies the directive while keeping the diff proportional.

**D1 — Runtime.** Podman (rootless, daemonless) is the local container runtime for the three `COACH_*` MCP servers and for the `harness/run.sh` container fallback. The GitHub servers stay on the pinned native binary (MADR-0002 D3), `BROWSER` stays on pinned `npx` (MADR-0009), and `openrouter` stays remote. CI workflows and the images under `harness/docker/**` remain Docker-based — explicitly out of scope.

**D2 — Image freshness (PO decision, 2026-11-13).** The Coach servers use **`--pull=missing`**. This is Podman's **default** policy for `run`; stating it explicitly keeps the intent legible instead of resting on an implicit default. It preserves MADR-0002 D3's property that session start never waits on a registry fetch, and matches today's effective behaviour. Image freshness remains owned by #412/#413, not by this record.

Rejected alternative, recorded for auditability: **`--pull=newer`** would fix staleness at the runtime level and is a capability Docker does not have — but it adds a registry round-trip to every session start plus a new offline failure mode for the Coach MCP, knowingly breaking the D3 baseline. `--pull=always` and floating tags are rejected outright: both defeat the supply-chain posture of a pinned, verified image reference. If #412 concludes that runtime-level freshness is worth the latency, `--pull=newer` is the mechanism to revisit — this record deliberately leaves that door documented rather than closed.

**D3 — Permission posture.** Two distinct command surfaces must not be conflated: `permission.bash` governs **agent-issued bash segments**, whereas the MCP `command` arrays are spawned by opencode **directly**, not through bash — so no bash rule governs the Coach spawns at all. Everything below concerns only the agent-command surface.

No blanket `podman *` allow is introduced, and — corrected after review (C3) — **a scoped *allow* set cannot tighten anything either**: the root `"*": allow` head already permits every `podman` sub-command, and a partial agent bash map appends *after* the root deny tail, so writing `podman run*: allow` into `agents/devops.md` would be a no-op that trips the #340 duplicate-root defect the gate rejects. The only tightening mechanism is the MADR-0022 pattern: a **root-level deny** plus **scoped allow carve-outs**. Any future narrowing of this family must therefore be expressed as `podman *: deny` in the root tail with an explicit carve-out list — or, if the family allow is retained, recorded as an **accepted residual with PO sign-off**. There is no third option.

Two sub-commands are **denied now** rather than deferred (C1/C2, implemented in #419): `podman system service*` — which re-creates a Docker-API-compatible socket, the long-lived daemon pattern this migration exists to remove — and `podman machine*`, which spawns a VM and can yield guest root while sharing the host home. Neither is privilege escalation *above uid 1000* under rootless mode; both are **persistence and API-surface** controls, and both are currently agent-issuable **unprompted** under the root head. A "flagged for review" entry with an acceptance fallback is not a control. `podman unshare` (user-namespace mapping with chown to arbitrary UIDs) is lower severity and remains a noted residual.

The `--env-file` parity claim is **form-dependent, not mechanism-dependent** (C8). `podman run --env-file x.env` *is* denied — because the `.env` filename appears in the command **text**, not because the mechanism is constrained. The deny is a command-string glob, so Podman-only equivalents evade it: `podman run --secret=<name>,type=env` (run-time secret injection, with **no Docker `run` analogue** — genuinely new surface introduced by this migration), `--env` with a substituted value (no filename), `podman create` + `start` with a non-`.env` path, and `podman-compose` reading an `env_file` internally. That gap is recorded as a residual in `arc42/03-cross-cutting-and-security.md` §3, in the same class as the accepted recursive-read bypass (#362).

**D4 — Runtime ownership: verify, do not provision.** `install.sh` **verifies** the runtime with a fail-closed check that resolves to **`podman` specifically** (or a documented fixed `OC_CONTAINER_RUNTIME` default) — a generic "is any container runtime present" guard would let a stray `docker` on another host satisfy the check while the migrated config demands `podman`, and would diverge from the pre-pull below (C7). The guard sits **before** the pre-pull and exits non-zero with the remediation command, in the style of the existing `openssl` guard. It does **not** install the runtime: package installation requires root, the profile's bash posture denies `sudo*`, and package-manager variance across hosts would turn a config bootstrap into a system-provisioning script. Provisioning remains a documented manual prerequisite (Admin guide) with probe evidence recorded on #416. The install-time pre-pull from MADR-0002 D3 is retained, re-expressed for the chosen runtime and bound to the same fixed name.

## Consequences

- **Positive:** the bootstrap stops aborting on its target host and fails legibly when the runtime is absent; the local container surface loses its root-equivalent daemon socket; the local MCP and harness fallback share one runtime; the CI pipeline and release path are untouched; the freshness question is separated from the substrate question instead of being settled by a flag.
- **Negative:** two runtimes coexist (Podman locally, Docker in CI), creating a standing documentation-divergence risk; the host gains a prerequisite to install and keep working; rootless-under-WSL2 is assumed rather than proven until #416's probe lands; operator habits and the `docker-expert` vocabulary drift from the actual local command.
- **Mitigations:** #416 must paste probe evidence (`podman info` rootless, cgroup manager, a container run) before D1 is relied upon; documentation parity travels in the same PR as each change (#417, #418); `harness/run.sh` resolves the runtime from a single overridable variable so Docker-based hosts and CI keep working; #419 reconciles the permission registry under `@cyber-security` review; the arc42 deployment and cross-cutting views carry this record's status so the documentation never claims more than is merged.
- **Residual risks:**
  1. **Rootless is not a defense against same-uid attack.** An escape from a rootless container yields uid 1000. This is a genuine improvement over container-root escalation, but it does not touch the same-uid exposure classes already accepted and recorded in MADR-0010 (RR1) and `arc42/03` §3 (#362) — those remain bounded by the filename denies, and are cross-referenced here rather than re-described.
  2. **`podman system service` is a persistence/API-surface control, not a privilege boundary.** It re-creates the long-lived Docker-API socket pattern. It does not raise a process above uid 1000 under rootless mode, so the deny (C1) is about keeping the migration's own premise true, not about blocking escalation. Severity: medium.
  3. **Image freshness stays unaddressed here** by construction (D2); stale `:latest` Coach images remain possible until #412/#413 lands, and this record does not pretend otherwise.
  4. **The harness fallback is rarely exercised** (native-first path dominates), so the migrated container path may be under-verified; #418 must keep its regression suite meaningful rather than merely adapted — and must probe the cgroup/ownership semantics flagged in C6 instead of assuming flag parity.

## Security Review (MADR-0008)

`@cyber-security` verdict **APPROVE-WITH-CONDITIONS** (2026-11-13). The substrate change is a net improvement and the scope is proportionate: rootless, daemonless Podman removes the root-equivalent daemon socket that Options 1 and 2 retain; the migration touches only the container-bearing surfaces (`COACH_*`, the `harness/run.sh` fallback — MADR-0003/#256); the Coach spawn is a fixed stdio invocation with no `-v`/`-p`/`-t` and no `--privileged`, so no host filesystem or network surface is added; and D2's rejection of `--pull=newer` / `--pull=always` / floating tags preserves the pinned-reference supply-chain posture of MADR-0002 D3. Three findings gate acceptance. First, **D3's tightening mechanism is unsound**: under the root `"*": allow` head a scoped *allow* set tightens nothing — a partial agent bash map appends after the root deny tail, so the only tightening lever is a root deny plus scoped allow carve-outs (the MADR-0022 pattern). Second, **D3's parity claim is form-dependent, not mechanism-dependent**: the `*.env*` deny matches the command string, so `podman run --env-file x.env` is indeed denied, but Podman's run-time `--secret` and any secret injection whose command text does not name a `.env`/`.pem`/`.key` file evade the deny — and MCP `command` arrays are spawned by opencode, not via bash, so no bash rule governs the Coach spawn at all. Third, **the record defers a named escalation path**: `podman system service` and `podman machine` are today fully allowed under the root head, and D3 pre-authorizes the outcome "recorded accepted residual" for them. A fourth, previously absent exposure — the GHCR credential file — is named as a driver but not constrained. Eight conditions gate spec finalization:

- **#416 (provisioning/probe):** **C7** the fail-closed guard must name `podman` specifically (or a documented fixed `OC_CONTAINER_RUNTIME`), sit before the re-expressed pre-pull, and exit non-zero with the remediation command in the `openssl`-guard style (`install.sh:118–121`).
- **#417 (MCP migration):** **C5** the GHCR credential file must be constrained — prefer **public** `ghcr.io/fpittelo/coach` images (no credential file written); if private is unavoidable, a read-only package-scoped token, a mode-600 `REGISTRY_AUTH_FILE` outside agent reach, and root bash denies for `*containers/auth.json*` / `*docker/config.json*` (the file-centric #167 pattern). This is a **new** exposure: `podman login` creates a credential file that the bash deny tail does not currently match.
- **#418 (harness fallback):** **C6** the "same security flags" claim must be probed, not assumed — rootless `--memory`/`--cpus` are enforced only with cgroup v2 delegation (the bound is otherwise cosmetic), and `--user 1000:1000` maps to a host **subuid** under the user namespace, changing bind-mount ownership semantics.
- **#419 (permission reconciliation):** **C1** deny `podman system service*` in the root deny tail **and** `BASELINE_DENY_TAIL` now (a flag is not a control; the deferral's stated fallback is acceptance); **C2** deny `podman machine*` likewise; **C3** rewrite D3 so tightening is expressed as a root deny + scoped carve-out, never as a scoped allow set; **C4** record the `docker *` reconciliation as **posture-neutral** — `AGENT_DEVIATIONS["devops.md"]` lists `docker *` while `agents/devops.md` carries none, so deleting it changes nothing and must not be reported as a tightening; **C8** correct the parity claim (form-dependent) and the bash/MCP surface conflation, and record the `--secret`/non-`.env` gap as a residual.

Residual risks recorded for `arc42/03-cross-cutting-and-security.md` §3: the Podman-only run-time secret-injection bypass of the command-string secret denies; unenforced rootless resource bounds; the GHCR credential file if a private image forces `podman login`; subuid-owned bind-mount writes in the harness fallback; and the silently inherited `podman` sub-command family (`system service`, `unshare`, `machine`, `kube play`, `--connection`, `generate`). Full rows appended to §3 with #417/#418/#419 as tracking issues.

### Condition → issue map

| Condition | Substance | Implementing issue | Evidence required |
| :--- | :--- | :--- | :--- |
| **C1** | Deny `podman system service*` in root tail + `BASELINE_DENY_TAIL` + truth-table row, now | #419 | Gate 16 green; deny verified live |
| **C2** | Deny `podman machine*` likewise | #419 | Gate 16 green |
| **C3** | Tightening = root deny + scoped carve-outs; a scoped allow set is a no-op | #419 | Amended MADR text; gate constant if exercised |
| **C4** | `docker *` reconciliation is posture-neutral; delete the dead `AGENT_DEVIATIONS` row | #419 | `AGENT_DEVIATIONS` diff; posture explicitly unchanged |
| **C5** | Constrain the GHCR credential file (prefer public images) | #417 | Anonymous-pull evidence, or token scope + `REGISTRY_AUTH_FILE` + bash denies |
| **C6** | Probe rootless cgroup enforcement and subuid bind-mount ownership | #418 (+ #416) | Probe transcript: OOM-kill under `--memory`, host ownership of a written file |
| **C7** | Guard names `podman` specifically, before the pre-pull, fail-closed | #416 | `install.sh` diff + abort run on a runtime-less host |
| **C8** | Correct parity claim + surface conflation, record `--secret` residual | #419 (+ this record) | Amended MADR text; §3 residual row |

