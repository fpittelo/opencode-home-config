#!/usr/bin/env bash
set -euo pipefail

DEST="$HOME/.config/opencode"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DEST"

# Shared temp workspace for the pinned-binary downloads below: created once,
# cleaned once by a single EXIT trap. Per-block traps overwrite each other,
# leaking every TMP_DIR but the last (#168).
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# 1. Symlink runtime configuration, agents, and skills
ln -sf "$SCRIPT_DIR/opencode.jsonc" "$DEST/opencode.jsonc"
ln -sfn "$SCRIPT_DIR/agents" "$DEST/agents"
ln -sfn "$SCRIPT_DIR/skills" "$DEST/skills"

# 2. Install pinned native github-mcp-server binary (MADR-0002 decision point 3, #109)
#    Replaces the Docker transport for GITHUB/GITHUB_CODE_REVIEWER: native startup
#    is milliseconds vs ~0.6 s per container spawn (2x per session, #106 baseline).
#    Supply-chain posture: version pinned + SHA256 verified against the release's
#    published checksums file — fail hard on any mismatch. No curl|bash: the
#    artifact is downloaded, verified, then extracted. Idempotent: skipped when
#    the pinned version is already installed (trusted on --version alone —
#    deliberate: anyone able to write ~/.local/bin already has code execution).
GITHUB_MCP_VERSION="1.12.2" # same build as the previously pinned image digest sha256:508a0857… (commit 85598ba6, 2026-09-16)
GITHUB_MCP_TARBALL_SHA256="95843162759da2c31dde082dd145be35db82164594796c294414b69790c2290e" # github-mcp-server_Linux_x86_64.tar.gz, per github-mcp-server_1.12.2_checksums.txt
BIN_DIR="$HOME/.local/bin"
BIN_PATH="$BIN_DIR/github-mcp-server"
mkdir -p "$BIN_DIR"

if [ -x "$BIN_PATH" ] && "$BIN_PATH" --version 2>/dev/null | grep -qF "Version: $GITHUB_MCP_VERSION"; then
    echo "✅  github-mcp-server $GITHUB_MCP_VERSION already installed at $BIN_PATH (skipping)."
else
    echo "⏳  Installing github-mcp-server $GITHUB_MCP_VERSION (native binary, checksum-verified)..."
    # Platform guard: the pinned artifact is Linux x86_64 only (VIDAR target).
    [ "$(uname -s)/$(uname -m)" = "Linux/x86_64" ] || { echo "❌  Unsupported platform $(uname -s)/$(uname -m) — pinned artifact github-mcp-server_Linux_x86_64.tar.gz requires Linux x86_64." >&2; exit 1; }
    ARTIFACT="github-mcp-server_Linux_x86_64.tar.gz"
    RELEASE_URL="https://github.com/github/github-mcp-server/releases/download/v$GITHUB_MCP_VERSION"
    curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$TMP_DIR/$ARTIFACT" "$RELEASE_URL/$ARTIFACT"
    curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$TMP_DIR/checksums.txt" "$RELEASE_URL/github-mcp-server_${GITHUB_MCP_VERSION}_checksums.txt"
    # Verify against the published checksums file first (release integrity),
    # then against our pinned hash (pin-drift detection). Fail hard on mismatch.
    PUBLISHED_SHA256="$(awk -v f="$ARTIFACT" '$2 == f {print $1}' "$TMP_DIR/checksums.txt")"
    if [ -z "$PUBLISHED_SHA256" ]; then
        echo "❌  $ARTIFACT missing from published checksums file — aborting." >&2
        exit 1
    fi
    if [ "$PUBLISHED_SHA256" != "$GITHUB_MCP_TARBALL_SHA256" ]; then
        echo "❌  Published checksum $PUBLISHED_SHA256 differs from pinned $GITHUB_MCP_TARBALL_SHA256 — aborting (pin drift or compromised release)." >&2
        exit 1
    fi
    if ! echo "$PUBLISHED_SHA256  $TMP_DIR/$ARTIFACT" | sha256sum -c --quiet - >/dev/null 2>&1; then
        echo "❌  SHA256 mismatch for downloaded $ARTIFACT — aborting." >&2
        exit 1
    fi
    tar -xzf "$TMP_DIR/$ARTIFACT" -C "$TMP_DIR"
    install -m 0755 "$TMP_DIR/github-mcp-server" "$BIN_PATH"
    echo "✅  github-mcp-server $GITHUB_MCP_VERSION installed at $BIN_PATH (SHA256 verified)."
fi

# 3. Install pinned Herdr agent-runtime binary (MADR-0005, #148)
#    Herdr hosts the OpenCode TUI as real PTY panes and reports agent lifecycle
#    state (working/blocked/idle); sessions survive terminal detach and Herdr
#    server restarts. Supply-chain posture: version pinned + SHA256 verified —
#    fail hard on any mismatch. No curl|bash: the artifact is downloaded,
#    verified, then installed. Idempotent: skipped when the pinned version is
#    already installed (trusted on --version alone — deliberate: anyone able to
#    write ~/.local/bin already has code execution).
#    Pin source: upstream publishes no checksums file; the SHA256 below is the
#    asset digest published by the GitHub release API for herdr-linux-x86_64
#    (api.github.com/repos/herdrdev/herdr/releases/tags/v0.9.3).
HERDR_VERSION="0.9.3"
HERDR_BINARY_SHA256="18a8dc65f1c2fa485884344356dea1cfd911c6f06cf46fa78e193f4087f4dba7"
BIN_DIR="$HOME/.local/bin"
BIN_PATH="$BIN_DIR/herdr"
mkdir -p "$BIN_DIR"

# Token-boundary match instead of grep -qF: a bare "0.9.3" pin must not
# substring-match a future "0.9.31" --version output and freeze a stale
# binary in the skip path (github-mcp-server avoids this via its full
# "Version: X" line format; herdr's output format is not line-anchored).
HERDR_VERSION_RX="$(printf '%s' "$HERDR_VERSION" | sed 's/\./\\./g')"
if [ -x "$BIN_PATH" ] && "$BIN_PATH" --version 2>/dev/null | grep -qE "(^|[^0-9.])${HERDR_VERSION_RX}([^0-9.]|$)"; then
    echo "✅  herdr $HERDR_VERSION already installed at $BIN_PATH (skipping)."
else
    echo "⏳  Installing herdr $HERDR_VERSION (checksum-verified)..."
    # Platform guard: the pinned artifact is Linux x86_64 only (VIDAR target).
    [ "$(uname -s)/$(uname -m)" = "Linux/x86_64" ] || { echo "❌  Unsupported platform $(uname -s)/$(uname -m) — pinned artifact herdr-linux-x86_64 requires Linux x86_64." >&2; exit 1; }
    ARTIFACT="herdr-linux-x86_64"
    RELEASE_URL="https://github.com/herdrdev/herdr/releases/download/v$HERDR_VERSION"
    curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$TMP_DIR/$ARTIFACT" "$RELEASE_URL/$ARTIFACT"
    # Verify the downloaded artifact against our pinned hash (pin-drift and
    # corrupted/tampered-download detection). Fail hard on mismatch.
    if ! echo "$HERDR_BINARY_SHA256  $TMP_DIR/$ARTIFACT" | sha256sum -c --quiet - >/dev/null 2>&1; then
        echo "❌  SHA256 mismatch for downloaded $ARTIFACT — aborting (expected $HERDR_BINARY_SHA256)." >&2
        exit 1
    fi
    install -m 0755 "$TMP_DIR/$ARTIFACT" "$BIN_PATH"
    echo "✅  herdr $HERDR_VERSION installed at $BIN_PATH (SHA256 verified)."
fi

# 4. Verify the pinned @playwright/mcp package (MADR-0009, #207)
#    The BROWSER MCP server runs via `npx @playwright/mcp@<version>` (stdio,
#    opencode.jsonc). npx itself re-verifies every download against the
#    registry's published dist.integrity on each launch; this check closes
#    the remaining gap — registry metadata for the pinned version drifting
#    from what we pinned (pin-drift / compromised-registry detection). The
#    SHA512 below is the dist.integrity of playwright-mcp-<version>.tgz as
#    published by the npm registry for @playwright/mcp@<version>, captured
#    at pin time (npm view @playwright/mcp@<version> dist.integrity) and
#    re-verified against the freshly downloaded registry tarball. Read-only
#    and idempotent: nothing is installed here — npx resolves the pinned
#    version at session start. Fail hard on any mismatch.
PLAYWRIGHT_MCP_VERSION="0.0.83"
PLAYWRIGHT_MCP_INTEGRITY="sha512-oNcl+Ae2/IAjhfPeP46BfIkSakfmprY+aOtkv5MjrQ4lPav4/yNtPhL0iq8SlIM90oApWgBDUxaNKvktazUKOg==" # dist.integrity of playwright-mcp-0.0.83.tgz, per registry.npmjs.org metadata for @playwright/mcp@0.0.83
if ! command -v openssl >/dev/null 2>&1; then
    echo "❌  openssl not found — required to verify @playwright/mcp ${PLAYWRIGHT_MCP_VERSION}." >&2
    exit 1
fi
echo "⏳  Verifying pinned @playwright/mcp ${PLAYWRIGHT_MCP_VERSION}..."
PLAYWRIGHT_MCP_ARTIFACT="mcp-${PLAYWRIGHT_MCP_VERSION}.tgz"
curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$TMP_DIR/$PLAYWRIGHT_MCP_ARTIFACT" "https://registry.npmjs.org/@playwright/mcp/-/$PLAYWRIGHT_MCP_ARTIFACT"
PLAYWRIGHT_MCP_ACTUAL_INTEGRITY="sha512-$(openssl dgst -sha512 -binary "$TMP_DIR/$PLAYWRIGHT_MCP_ARTIFACT" | openssl base64 -A)"
if [ "$PLAYWRIGHT_MCP_ACTUAL_INTEGRITY" != "$PLAYWRIGHT_MCP_INTEGRITY" ]; then
    echo "❌  Registry tarball integrity $PLAYWRIGHT_MCP_ACTUAL_INTEGRITY differs from pinned $PLAYWRIGHT_MCP_INTEGRITY — aborting (pin drift or compromised registry)." >&2
    exit 1
fi
echo "✅  @playwright/mcp ${PLAYWRIGHT_MCP_VERSION} verified (registry tarball SHA512 matches pin)."

# 5. Pre-pull the pinned coach image (idempotent: docker pull is a no-op when the
#    image is already present locally, so session start never waits on a registry
#    fetch — MADR-0002 decision point 3, #107). Coach stays containerized (#109):
#    the github-mcp-server Docker image is no longer used (native binary above).
COACH_DEV_IMAGE="ghcr.io/fpittelo/coach:dev"
echo "⏳  Pre-pulling pinned coach image..."
docker pull "$COACH_DEV_IMAGE"
echo "✅  Coach image pre-pulled (coach:dev)."

# 6. Generate secrets template if absent
SECRETS_FILE="$DEST/.secrets.env"
if [ ! -f "$SECRETS_FILE" ]; then
    cat << 'EOF' > "$SECRETS_FILE"
export OPENROUTER_HOME_API_KEY=""
export GITHUB_PERSONAL_ACCESS_TOKEN=""
export GITHUB_TOKEN_CODE_REVIEWER=""  # token for @devfpittelo machine account — @code-reviewer identity
export INTERVALS_API_KEY=""
export INTERVALS_ATHLETE_ID=""
EOF
    chmod 600 "$SECRETS_FILE"
    echo "⚠️  Created $SECRETS_FILE. Please populate your secrets."
fi

# 7. Propagate secrets to interactive shells and GUI desktop sessions
# Shell profiles
if ! grep -q "source $SECRETS_FILE" "$HOME/.bashrc" 2>/dev/null; then
    echo "[ -f $SECRETS_FILE ] && source $SECRETS_FILE" >> "$HOME/.bashrc"
fi
if ! grep -q "source $SECRETS_FILE" "$HOME/.profile" 2>/dev/null; then
    echo "[ -f $SECRETS_FILE ] && source $SECRETS_FILE" >> "$HOME/.profile"
fi

# Systemd user session (allows GUI application launcher to inherit tokens)
if command -v systemctl >/dev/null 2>&1 && systemctl --user is-system-running >/dev/null 2>&1; then
    set -a
    # shellcheck disable=SC1090
    source "$SECRETS_FILE"
    systemctl --user import-environment OPENROUTER_HOME_API_KEY GITHUB_PERSONAL_ACCESS_TOKEN GITHUB_TOKEN_CODE_REVIEWER INTERVALS_API_KEY INTERVALS_ATHLETE_ID || true
    set +a
fi

echo "✅ VIDAR Home OpenCode configured successfully (CLI & Desktop)."
