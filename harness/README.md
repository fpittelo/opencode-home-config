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
docker run --rm \
  --read-only \
  --user 1000:1000 \
  --memory=4g --memory-swap=4g \
  --cpus=2.0 \
  --network=none \
  --tmpfs /tmp:noexec,nosuid,size=1g \
  -v "$PWD:/workspace:rw" \
  -v harness-uv-cache:/home/harness/.cache/uv \
  -v harness-pip-cache:/home/harness/.cache/pip \
  -w /workspace \
  ghcr.io/fpittelo/harness-runner-python:dev \
  bash -c "uv sync --frozen && uv run pytest -W error --cov=."
```

```bash
# Rust project
docker run --rm \
  --read-only \
  --user 1000:1000 \
  --memory=4g --memory-swap=4g \
  --cpus=2.0 \
  --network=none \
  --tmpfs /tmp:noexec,nosuid,size=1g \
  -v "$PWD:/workspace:rw" \
  -v harness-cargo-registry:/home/harness/.cargo/registry \
  -v harness-cargo-git:/home/harness/.cargo/git \
  -v harness-cargo-target:/workspace/target \
  -w /workspace \
  ghcr.io/fpittelo/harness-runner-rust:dev \
  bash -c "cargo fmt --check && cargo clippy -- -D warnings && cargo test"
```

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

Named volumes are ideal for **runtime** harness execution because they persist across `docker run` invocations. BuildKit cache mounts are ideal for **image build time** because they are scoped to the build and do not bloat the final image. We use both at the appropriate layer.

---

## 4. CI Integration

The workflow `.github/workflows/harness-image-build.yml` builds and publishes both images on every push to `dev`, `qa`, or `main` (and on PRs affecting the harness Dockerfiles).

### Tagging Strategy

| Branch | Image Tag | Meaning |
| :--- | :--- | :--- |
| `dev` | `:dev` | Bleeding-edge harness runner for sprint development |
| `qa` | `:qa` | Staging-qualified harness runner |
| `main` | `:latest` + `:qa` | Production release; `:latest` points to the last stable build |

### Notes

- Images are pushed to `ghcr.io/fpittelo/harness-runner-python` and `ghcr.io/fpittelo/harness-runner-rust`.
- Authentication uses the repository's `GITHUB_TOKEN` via `docker/login-action`.
- BuildKit layer caching is enabled through GitHub Actions cache (`type=gha`).
- PR builds are **not** pushed; they only verify that the Dockerfiles still build.

---

## 5. Resource Limits

The recommended `docker run` flags enforce deterministic, bounded resource usage:

| Resource | Flag | Value | Rationale |
| :--- | :--- | :--- | :--- |
| Memory limit | `--memory=4g` | 4 GB | Sufficient for Python/Rust test suites; prevents runaway containers |
| Memory + swap | `--memory-swap=4g` | 4 GB | Disables swap expansion, enforcing the hard limit |
| CPU limit | `--cpus=2.0` | 2 cores | Bounded compute; adjust per project |
| Network | `--network=none` | No network | Prevents tests from calling external services |
| Filesystem | `--read-only` | Read-only root | Forces explicit writable volumes |
| Temp storage | `--tmpfs /tmp:noexec,nosuid,size=1g` | 1 GB tmpfs | Writable scratch space without persisting host `/tmp` |
| User | `--user 1000:1000` | Non-root | Matches the `harness` user inside the image |
| Timeout | harness orchestrator | 10 min lint / 30 min test | Hard cap on agent self-correction loop |

### Network Policy

- **Unit tests:** run with `--network=none`.
- **Dependency resolution / audit:** run in a separate setup step with network enabled, then drop network for the actual test execution.

This split prevents flaky tests caused by external network availability and closes a potential data-exfiltration vector.

---

## 6. Security & Governance Compliance

- **Multi-stage builds:** build tools and caches are not present in the final image.
- **Non-root user:** all containers run as `harness` (UID/GID 1000).
- **Minimal base images:** `python:3.12-slim-bookworm` and `rust:1.81.0-slim-bookworm`.
- **Zero hardcoded secrets:** credentials are injected via GitHub Actions `secrets.GITHUB_TOKEN` and `{env:VAR}` interpolation.
- **Read-only root filesystem:** runtime root is read-only; only `/workspace`, `/tmp`, and named cache volumes are writable.
- **HOME 3-branch lifecycle:** image builds follow `dev` → `qa` → `main` promotions with explicit `@fpittelo` approval gates.

---

## 7. Local Validation Commands

```bash
# Build locally
docker build -f harness/docker/Dockerfile.python -t ghcr.io/fpittelo/harness-runner-python:dev harness/docker
docker build -f harness/docker/Dockerfile.rust -t ghcr.io/fpittelo/harness-runner-rust:dev harness/docker

# Smoke test
docker run --rm ghcr.io/fpittelo/harness-runner-python:dev python --version
docker run --rm ghcr.io/fpittelo/harness-runner-rust:dev rustc --version
```
