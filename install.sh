#!/usr/bin/env bash
set -euo pipefail

DEST="$HOME/.config/opencode"
mkdir -p "$DEST"

# 1. Symlink runtime configuration, agents, and skills
ln -sf "$PWD/opencode.jsonc" "$DEST/opencode.jsonc"
ln -sfn "$PWD/agents" "$DEST/agents"
ln -sfn "$PWD/skills" "$DEST/skills"

# 2. Generate secrets template if absent
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

# 3. Propagate secrets to interactive shells and GUI desktop sessions
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
