#!/usr/bin/env bash
set -euo pipefail

DEST="$HOME/.config/opencode"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DEST"

# 1. Symlink runtime configuration, agents, and skills
ln -sf "$SCRIPT_DIR/opencode.jsonc" "$DEST/opencode.jsonc"
ln -sfn "$SCRIPT_DIR/agents" "$DEST/agents"
ln -sfn "$SCRIPT_DIR/skills" "$DEST/skills"

# 2. Pre-pull pinned MCP images (idempotent: docker pull is a no-op when the
#    image is already present locally, so session start never waits on a
#    registry fetch — MADR-0002 decision point 3, #107)
GITHUB_MCP_IMAGE="ghcr.io/github/github-mcp-server@sha256:508a0857ec762b1ab1cece29193345b501fab1dd9d1228a7b617062954cecac6" # v1.12.2 (2026-09-16)
COACH_DEV_IMAGE="ghcr.io/fpittelo/coach:dev"
echo "⏳  Pre-pulling pinned MCP images..."
docker pull "$GITHUB_MCP_IMAGE"
docker pull "$COACH_DEV_IMAGE"
echo "✅  MCP images pre-pulled (github-mcp-server v1.12.2 digest-pinned, coach:dev)."

# 3. Generate secrets template if absent
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

# 4. Propagate secrets to interactive shells and GUI desktop sessions
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
