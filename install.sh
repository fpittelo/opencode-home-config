#!/usr/bin/env bash
set -euo pipefail

DEST="$HOME/.config/opencode"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DEST"

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
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
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

# 3. Pre-pull the pinned coach image (idempotent: docker pull is a no-op when the
#    image is already present locally, so session start never waits on a registry
#    fetch — MADR-0002 decision point 3, #107). Coach stays containerized (#109):
#    the github-mcp-server Docker image is no longer used (native binary above).
COACH_DEV_IMAGE="ghcr.io/fpittelo/coach:dev"
echo "⏳  Pre-pulling pinned coach image..."
docker pull "$COACH_DEV_IMAGE"
echo "✅  Coach image pre-pulled (coach:dev)."

# 4. Generate secrets template if absent
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

# 5. Propagate secrets to interactive shells and GUI desktop sessions
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
