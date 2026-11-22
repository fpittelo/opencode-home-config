# Harness Engineering — Container Image Strategy

This directory implements the **sandboxed execution harness** base images for the HOME ecosystem, as defined in [GitHub issue #35](https://github.com/fpittelo/opencode-home-config/issues/35).

The harness shifts agent evaluation from prompt-based trust to deterministic, closed-loop verification: every build, lint, and test command runs inside an isolated container before any GitHub branch or pull request is updated.

---

## 1. Image Design: Two Separate Images

We provide **two dedicated runner images** rather than a single polyglot image:

| Image | Stack | Pre-installed Tools |
| :--- | :--- | :--- |
| `ghcr.io/fpittelo/harness-runner-python` | Python 3.12 | `uv`, `ruff`, `black`, `isort`, `mypy`, `pytest`, `pytest-cov` |
| `ghcr.io/fpittelo/harness-runner-rust` | Rust stable | `cargo`, `rustfmt`, `clippy`, `cargo-audit`, `cargo-deny` |

### Rationale

- **Minimal attack surface:** each image contains only one toolchain.
- **Faster pulls and builds:** agents working on Python repos do not download the Rust toolchain and vice versa.
- **Independent versioning:** Python and Rust release cycles are decoupled.
- **Alignment with HOME architecture:** the ecosystem explicitly separates Python MCP servers / coaches from the Rust Kratos control plane.
- **Simpler debugging:** toolchain-specific failures are isolated.

A future thin orchestrator image may detect `pyproject.toml` vs `Cargo.toml` and dispatch to the correct runner, but the execution images themselves remain separate.

---

## 2. Volume Mount Strategy

### Recommended Approach: Bind Mount + Named Cache Volumes

```bash
# Python project
podman run --rm \
  --read-only \
  --userns=keep-id \
  --memory=4g --memory-swap=4g \
  --cpus=2.0 \
  --network=none \
  --tmpfs /tmp:noexec,nosuid,size=1g \
  -v "$PWD:/workspace:rw" \
  -v harness-uv-cache:/home/harness/.cache/uv \
  -v harness-pip-cache:/home/harness/.cache/pip \
  -w /workspace \
  ghcr.io/fpittelo/harness-runner-python:latest \
  bash -c "uv sync --frozen && uv run pytest -W error --cov=."
```

```bash
# Rust project
podman run --rm \
  --read-only \
  --userns=keep-id \
  --memory=4g --memory-swap=4g \
  --cpus=2.0 \
  --network=none \
  --tmpfs /tmp:noexec,nosuid,size=1g \
  -v "$PWD:/workspace:rw" \
  -v harness-cargo-registry:/home/harness/.cargo/registry \
  -v harness-cargo-git:/home/harness/.cargo/git \
  -v harness-cargo-target:/workspace/target \
  -w /workspace \
  ghcr.io/fpittelo/harness-runner-rust:latest \
  bash -c "cargo fmt --check && cargo clippy -- -D warnings && cargo test"
```

These examples use the **local runtime** — rootless Podman ([MADR-0024](../docs/adr/0024-adopt-podman-as-the-local-container-runtime-for-mcp-servers.md)) — with the rootless-correct non-root bound `--userns=keep-id` (§5). `harness/run.sh` resolves the same runtime from a single `CONTAINER_RUNTIME` token (default `podman`, env-overridable on Docker-based hosts and CI). The **CI-side runner images and the workflow that publishes them stay Docker-based** (§4) — only the local surfaces moved to Podman.

### Trade-off Analysis

| Option | Security | Caching | Speed | Correctness | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A: Bind mount `$PWD:/workspace`** | Good with `--read-only` root + writable workspace + non-root user | Excellent via named cache volumes | Fastest: uses host git state | High: runs against exact working tree | **Adopted** |
| **B: `git clone` inside container** | Excellent isolation | Poor: clone and dependency fetch every run | Slow: full clone + fetch | High: clean state, but diverges from dirty working tree | Rejected for iteration speed |
| **C: `COPY` in Dockerfile** | Excellent | None: rebuild per commit | Very slow: rebuild image every change | Low: cannot test uncommitted changes | Rejected for agent workflow |

### Why Option A is Best for the Harness

- The agent iterates up to three times on a fix; rebuilding or recloning on every iteration is unacceptable.
- The working tree on the host contains the agent's uncommitted changes; a `git clone` would lose them.
- `--read-only` root filesystem plus a non-root user provides strong isolation while preserving performance.
- Named cache volumes keep dependency caches warm across runs.

---

## 3. Dependency Caching Strategy

### Runtime Caching: Named Volumes

| Language | Volume | Mounted To | Purpose |
| :--- | :--- | :--- | :--- |
| Python | `harness-uv-cache` | `/home/harness/.cache/uv` | uv package cache |
| Python | `harness-pip-cache` | `/home/harness/.cache/pip` | pip wheel cache (fallback) |
| Rust | `harness-cargo-registry` | `/home/harness/.cargo/registry` | crates.io registry index and crates |
| Rust | `harness-cargo-git` | `/home/harness/.cargo/git` | Git dependencies |
| Rust | `harness-cargo-target` | `/workspace/target` | Incremental build artifacts |

### Image Build Caching: BuildKit Cache Mounts

Both Dockerfiles use `RUN --mount=type=cache,target=...` during tool installation:

- Python: `/root/.cache/uv` is cached while installing `ruff`, `black`, etc.
- Rust: `/usr/local/cargo/registry` and `/usr/local/cargo/git` are cached while building `cargo-audit` and `cargo-deny`.

This keeps CI build times low and avoids re-downloading the same crates/packages on every workflow run.

### Why Not Only Named Volumes?

Named volumes are ideal for **runtime** harness execution because they persist across container `run` invocations. BuildKit cache mounts are ideal for **image build time** because they are scoped to the build and do not bloat the final image. We use both at the appropriate layer.

---

## 4. CI Integration

The workflow `.github/workflows/harness-image-build.yml` builds and publishes both images on every push to `main` (the trunk — MADR-0017) and on PRs affecting the harness Dockerfiles. This workflow and these images **stay Docker-based** by design (MADR-0024 D1): GitHub-hosted runners are Docker-native and the pipeline depends on `docker/setup-buildx-action`, `docker/login-action`, `docker/metadata-action` and `docker/build-push-action`. Only the local surfaces (MCP servers, the `run.sh` fallback) moved to Podman.

### Tagging Strategy

| Ref | Image Tag | Meaning |
| :--- | :--- | :--- |
| `main` (trunk) | `:latest` | Trunk build; `:latest` points to the last stable build |
| Release tag `vX.Y.Z` | `:vX.Y.Z` | Pinned harness runner for a released version |

### Notes

- Images are pushed to `ghcr.io/fpittelo/harness-runner-python` and `ghcr.io/fpittelo/harness-runner-rust`.
- Authentication uses the repository's `GITHUB_TOKEN` via `docker/login-action`.
- BuildKit layer caching is enabled through GitHub Actions cache (`type=gha`).
- PR builds are **not** pushed; they only verify that the Dockerfiles still build.
- `deep-validation.yml` pulls the docs-validator image **digest-pinned** (#375): `:latest` is republished on the same push-to-main event, so a tag pull would race the publish. Refresh the pinned digest (the OCI image index from `docker buildx imagetools inspect ghcr.io/fpittelo/harness-docs-validator:latest`) whenever the validator image changes.

---

## 5. Resource Limits

The recommended container `run` flags (local runtime: rootless Podman, MADR-0024 D1) enforce deterministic, bounded resource usage:

| Resource | Flag | Value | Rationale |
| :--- | :--- | :--- | :--- |
| Memory limit | `--memory=4g` | 4 GB | Sufficient for Python/Rust test suites; prevents runaway containers |
| Memory + swap | `--memory-swap=4g` | 4 GB | Disables swap expansion, enforcing the hard limit |
| CPU limit | `--cpus=2.0` | 2 cores | Bounded compute; adjust per project |
| Network | `--network=none` | No network | Prevents tests from calling external services |
| Filesystem | `--read-only` | Read-only root | Forces explicit writable volumes |
| Temp storage | `--tmpfs /tmp:noexec,nosuid,size=1g` | 1 GB tmpfs | Writable scratch space without persisting host `/tmp` |
| User | `--userns=keep-id` | Container uid = host uid | Rootless-correct non-root bound: keeps the bind mount writable **and** host-owned (`--user 1000:1000` maps container uid 1000 to a host *subuid*, so `-v "$PWD:/workspace:rw"` fails with `Permission denied` — measured, #418 / MADR-0024 C6) |
| Timeout | harness orchestrator | 10 min lint / 30 min test | Hard cap on agent self-correction loop |

**Resource-limit enforcement is measured, not assumed (#418, MADR-0024 C6).** On VIDAR (rootless Podman 5.7.0, cgroup v2, systemd delegation) `--memory=32m` yields `memory.max` = `33554432` and `--cpus=2.0` yields `cpu.max` = `200000 100000` inside the container, so the DoS bound above is **real** on that host. On a host without delegated cgroup controllers the limits are accepted but silently ignored — that is a **recorded residual** (MADR-0024 C6), not an enforced bound, which is why `run.sh` keeps the flags and documents the dependency.

### Network Policy

- **Unit tests:** run with `--network=none`.
- **Dependency resolution / audit:** run in a separate setup step with network enabled, then drop network for the actual test execution.

This split prevents flaky tests caused by external network availability and closes a potential data-exfiltration vector.

---

## 6. Security & Governance Compliance

- **Multi-stage builds:** build tools and caches are not present in the final image.
- **Non-root user:** all containers run as `harness` (UID/GID 1000).
- **Minimal base images:** `python:3.12-slim-bookworm` and `rust:1.88.0-slim-bookworm`.
- **Zero hardcoded secrets:** credentials are injected via GitHub Actions `secrets.GITHUB_TOKEN` and `{env:VAR}` interpolation.
- **Read-only root filesystem:** runtime root is read-only; only `/workspace`, `/tmp`, and named cache volumes are writable.
- **HOME trunk+tag lifecycle (MADR-0017):** image builds follow the single trunk `main`; releases are semantic tags cut from `main` under the single explicit `@fpittelo` release approval (`home-governance` Rule 5).

---

## 7. Local Validation Commands

```bash
# Build locally (local runtime: Podman, MADR-0024 D1)
podman build -f harness/docker/Dockerfile.python -t ghcr.io/fpittelo/harness-runner-python:latest harness/docker
podman build -f harness/docker/Dockerfile.rust -t ghcr.io/fpittelo/harness-runner-rust:latest harness/docker

# Smoke test
podman run --rm ghcr.io/fpittelo/harness-runner-python:latest python --version
podman run --rm ghcr.io/fpittelo/harness-runner-rust:latest rustc --version
```

These are the local commands (§2); `harness/run.sh` resolves the same runtime from its `CONTAINER_RUNTIME` token (default `podman`). The CI-side runner images stay **Docker-based** (§4).

---

## 8. Native Fast Path & Config-Repo Gate (MADR-0003, #131)

`run.sh` is **native-first**: when the host can provision the project toolchain (`uv` present) or the project `.venv` already exists, the gates run directly on the host against the **project-pinned** `.venv` toolchain (no container cold start, no image pull, no volume warm-up). The native gate resolves every tool from `${REPO_ROOT}/.venv/bin` and **never** silently falls back to lookalike host-PATH tools: a missing `.venv` or a missing required tool is a hard failure (exit 3) with an actionable message (#256 AC2/AC3). Only when the host has neither `uv` nor a project `.venv` does the run fall back to the container path above, with the same isolation guarantees (same security flags, expressed rootless-correctly — `--userns=keep-id` replaces `--user 1000:1000`, §5; same two-phase deps/gate design, same coverage threshold). Every phase prints which path it took and why.

| Stack | Native gate requires in the project `.venv` | Native deps requires |
| :--- | :--- | :--- |
| `python` | `ruff`, `black`, `isort`, `mypy`, `pytest`, `pytest-cov` | `uv` (only when `pyproject.toml` exists) |
| `rust` | `cargo`, `rustfmt`, `clippy-driver` on `PATH` | `cargo` (only when `Cargo.toml` exists) |

The Python deps phase runs `uv sync --all-extras` so the dev extras (the gate toolchain) are retained in the project `.venv` (#256 AC1). The gate command chains are identical in both paths (`pytest --cov-fail-under=80` included). The network-off guarantee of the gate phase is container-only; native runs execute on the host under the operator's own controls.

`run-config-gate.sh` is the native pre-flight for **this configuration repository** (no `pyproject.toml`/`Cargo.toml`, so `run.sh` SKIPs its deps phase). It is **Tier A** of the two-tier config validation doctrine (§9): JSONC validation of `opencode.jsonc`, `bash -n install.sh`, agent/skill presence, the direct real-repo invariant checkers (`check_agent_frontmatter.py`, `check_coach_exclusivity.py`, `check_browser_launch_flags.py`, `check_bash_permission_tiers.py`, `check_gitleaks_allowlist.py`, `check_external_prerequisites.py`, `check_installed_posture_freshness.py`, `check_pin_freshness_workflow.py`), the three native docs validators (links, MADR, mermaid syntax), and the install-pin consistency suite (`test_pin_consistency.py`, real-repo assertions only). Zero Docker, fail-fast, well under 5 s (measured 0.43 s on VIDAR; the pre-#479 gate ran the regression suites and took 9.9 s):

```bash
bash harness/run-config-gate.sh            # this repo (default root)
bash harness/run-config-gate.sh /tmp/repo  # alternate root (negative-path tests)
```

The regression suites below are **Tier B** (§9): they run on the scheduled Deep Validation cadence (`.github/workflows/deep-validation.yml`, `config-regression-suites` job), not in the per-push gate. They are fully blocking — any suite failure fails the DV run (MADR-0028 fail-closed).

The mermaid syntax-mode regression suite (stdlib `unittest`) guards `check_mermaid.py --syntax`:

```bash
python3 harness/docs-validation/test_check_mermaid_syntax.py
```

The namespace-exclusivity regression suite (stdlib `unittest`) guards `check_coach_exclusivity.py` — both governed namespaces (COACH_* #150, BROWSER_* #207/MADR-0009), negative cases per invariant layer, real-repo positive control:

```bash
python3 harness/config-validation/test_check_coach_exclusivity.py
```

The harness native-gate regression suite (stdlib `unittest`) guards `run.sh` toolchain pinning (#256) and the single container-runtime token (#418) — deps retains dev extras, the native gate resolves tools from the project `.venv` (never host PATH) and exits 3 when the venv or a required tool is missing, and the container fallback keeps its isolation flags (`--userns=keep-id` non-root bound, `--network=none`, read-only root) while resolving its runtime from `CONTAINER_RUNTIME` (default `podman`, env-overridable) with no hardcoded `docker` invocation:

```bash
python3 harness/config-validation/test_harness_run.py
```

The per-pane profile selection regression suite (stdlib `unittest`, Tier B §9, #263) guards the dual-profile coexistence and per-pane secrets isolation delivered by #244 — profiles.sh provisioning and the `oc-home` wrapper semantics, the secrets split/migration (`.secrets-home.env`, shared `.secrets.env` retirement), legacy `/AI_OS_ROOT` switcher cleanup, permission hardening (700 config dir, mode-600 secrets, fail-closed assertion), and `.gitignore` coverage. Every behavioral test runs `install.sh` against a sandboxed fake `$HOME` with stubbed `systemctl`/`docker`/`curl`/`openssl` — never the real home directory, never the network:

```bash
python3 tests/test_per_pane_profile_selection.py
```

The agent front-matter validity gate (#338, `harness/config-validation/check_agent_frontmatter.py`) structurally parses the YAML front-matter block of every `agents/*.md` — `---` delimiters, YAML parseability with duplicate keys rejected, and the mandatory schema (`description`, `mode`, `openrouter/<slug>` model, `temperature` in [0, 2], non-empty `permission` mapping) — closing the #325 defect class where corrupted front-matter passed the indentation-insensitive namespace-exclusivity checker:

```bash
python3 harness/config-validation/check_agent_frontmatter.py .
```

---

## 9. Two-Tier Config Validation (#479)

Config validation is split so that **per-push cost tracks real-repo invariants** while the checker regression suites run on the deep cadence:

- **Tier A — per-push** (`harness/run-config-gate.sh`, invoked by `ci.yml` and as the local pre-flight): direct, real-repo invariant checks only. Fail-closed, first failing gate aborts, non-zero exit.
- **Tier B — scheduled** (`.github/workflows/deep-validation.yml`, `config-regression-suites` job): the checker regression suites — negative fixtures plus sandboxed behavioral suites. Any suite failure fails the DV run; a RED DV on trunk pauses new dispatches (MADR-0028, fail-closed).

**Invariant (non-negotiable):** every real-repo check enforced per-push before #479 is still enforced per-push — re-expressed as a **direct checker invocation** where it used to run only inside a `test_*.py` suite (the #371 removal of the back-to-back standalone checker runs had made those reachable only through their suites). No gate was dropped; the mapping below accounts for all 22 pre-split gates plus the post-split gate appended by #481 (row 23).

The split is machine-pinned by `harness/config-validation/test_config_gate_tiers.py` (Tier B): Tier A must invoke every mandated direct checker and no Tier B suite, the DV job must run every Tier B suite, and this table must keep covering gates 1–23.

| Gate | Check | Tier A — per-push (`run-config-gate.sh`) | Tier B — scheduled DV |
| :--- | :--- | :--- | :--- |
| 1 | `opencode.jsonc` parses as JSONC | gate 1 | — |
| 2 | `bash -n install.sh` | gate 2 | — |
| 3 | Agent files present (7) | gate 3 | — |
| 4 | Skill directories present (16) | gate 4 | — |
| 5 | Native links validator | gate 5 — `check_links.py .` | — |
| 6 | Native MADR schema validator | gate 6 — `check_madr.py .` | — |
| 7 | Mermaid syntax validator | gate 7 — `check_mermaid.py --syntax .` | — |
| 8 | Mermaid syntax checker regression suite | — | `test_check_mermaid_syntax.py` |
| 9 | COACH_*/BROWSER_*/GITHUB_SECURITY_*/openrouter_*/GITHUB_CODE_REVIEWER_* namespace exclusivity | gate 9 — `check_coach_exclusivity.py .` | `test_check_coach_exclusivity.py` |
| 10 | BROWSER launch-flag invariant | gate 10 — `check_browser_launch_flags.py .` | `test_check_browser_launch_flags.py` |
| 11 | `run.sh` native-gate toolchain pinning | — | `test_harness_run.py` |
| 12 | Per-pane profile selection / secrets isolation | — | `test_per_pane_profile_selection.py` |
| 13 | Install-pin consistency (real-repo only) | gate 16 — `test_pin_consistency.py` | — |
| 14 | Bash tier baseline, truth tables, agent inheritance | gate 11 — `check_bash_permission_tiers.py .` | `test_check_bash_permission_tiers.py` |
| 15 | Agent YAML front-matter validity | gate 8 — `check_agent_frontmatter.py .` | `test_check_agent_frontmatter.py` |
| 16 | GitHub namespace identity probe | — | `test_github_identity_probe.py` |
| 17 | External-prerequisite inventory | gate 13 — `check_external_prerequisites.py .` | `test_check_external_prerequisites.py` |
| 18 | Gitleaks allowlist + tracked runtime artifacts | gate 12 — `check_gitleaks_allowlist.py .` | `test_check_gitleaks_allowlist.py` |
| 19 | Pin-freshness workflow blast radius (MADR-0026 C6) | gate 15 — `check_pin_freshness_workflow.py .` | `test_check_pin_freshness_workflow.py` |
| 20 | Installed-posture freshness (deny tail + ordered wrappers/kill) | gate 14 — `check_installed_posture_freshness.py .` | `test_check_installed_posture_freshness.py` |
| 21 | Architecture-coverage gate logic (#421) | `ci.yml` — `check_arch_coverage.sh` (unchanged) | `test_check_arch_coverage.py` |
| 22 | Operator doctor orchestrator semantics | — | `test_doctor_script.py` |
| 23 | DoD closeout signal workflow blast radius + verifier logic (#481) | gates 17-18 — `test_check_dod_closeout_workflow.py`, `test_dod_closeout_verifier.py` | — |

Gates 8, 11, 12, 16 and 22 assert the behaviour of checkers and scripts against fixtures — they carry no real-repo invariant, so they are Tier B only. Gate 21 keeps its per-push enforcement in `ci.yml` (the script invocation, unchanged by #479) and only its suite moved. Gate 23 is the #481-mandated exception: its two suites are wired into the per-push gate DIRECTLY (gate 17 = the blast-radius suite with negative fixtures + the real-repo positive control, gate 18 = the verifier tri-state suite) because "a suite executed by no gate is advisory only" (#481 AC11/R5-C12/R5-C13) — both stay under 0.3 s so the Tier A budget holds.

**Runtime (AC4):** the per-push gate measures **0.43 s** after the split versus **9.9 s** before it (3-run median, VIDAR, same host); the #481 gate 17-18 additions measure **0.66 s** total — comfortably inside the < 5 s budget.
