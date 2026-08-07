#!/usr/bin/env bash
set -euo pipefail

echo "=== Labs64.IO DevContainer Setup ==="

# Wire the ecosystem's shared skills (.agents/skills/, git-tracked here) into every AI
# coding agent that reads this container's user-level config. Symlinked rather than
# copied so edits show up immediately for every developer without a rebuild. Lives at
# user level (not project-level .claude/skills) because sessions may be rooted at
# /workspaces (ecosystem root, not a git repo) or any individual sibling repo, and
# user-level config applies regardless of cwd.
#
# There is no shared "AGENTS_CONFIG_DIR" env var that multiple agents honor — each tool
# defines its own (CLAUDE_CONFIG_DIR here, CODEX_HOME for Codex), so each gets linked
# separately. The SKILL.md format (name/description frontmatter) happens to be portable
# across both, so one source directory serves both links.
SKILLS_SRC=/workspaces/labs64.io-workspace/.agents/skills

echo "Linking shared skills into Claude Code..."
CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
mkdir -p "$CLAUDE_CONFIG_DIR"
ln -sfn "$SKILLS_SRC" "$CLAUDE_CONFIG_DIR/skills"

echo "Linking shared skills into Codex CLI..."
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME"
ln -sfn "$SKILLS_SRC" "$CODEX_HOME/skills"

# Install egress-firewall dependencies and stage the init script.
# The firewall itself is (re)applied on every container start via
# postStartCommand -> /usr/local/bin/init-firewall.sh (see devcontainer.json).
echo "Installing firewall dependencies..."
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends iptables ipset dnsutils aggregate jq
sudo install -m 0755 "$(dirname "$0")/init-firewall.sh" /usr/local/bin/init-firewall.sh

# Install just-lsp
# The Ubuntu-packaged cargo is 1.75, too old for just-lsp (needs edition2024 /
# Rust >= 1.85), so install a current stable toolchain via rustup instead.
# Currently commented-out as installation takes too long
# echo "Probing rustup..."
# if ! command -v rustup &> /dev/null; then
#     echo "Installing Rust toolchain..."
#     curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
# fi
# # shellcheck source=/dev/null
# source "$HOME/.cargo/env"
# cargo install just-lsp

# Install k3d
if ! command -v k3d &> /dev/null; then
    echo "Installing k3d..."
    curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
fi

# Install just
if ! command -v just &> /dev/null; then
    echo "Installing just..."
    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | sudo bash -s -- --to /usr/local/bin
fi

# Install helmfile
if ! command -v helmfile &> /dev/null; then
    echo "Installing helmfile..."
    HELMFILE_VERSION="1.7.1"
    curl -fsSL "https://github.com/helmfile/helmfile/releases/download/v${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION}_linux_amd64.tar.gz" | tar -xz -C /tmp helmfile
    sudo mv /tmp/helmfile /usr/local/bin/helmfile
    sudo chmod +x /usr/local/bin/helmfile
fi

# Install required Helm plugins
echo "Installing Helm plugins..."
helm plugin install --verify=false https://github.com/databus23/helm-diff 2>/dev/null || true
helm plugin install --verify=false https://github.com/dadav/helm-schema 2>/dev/null || true

# Install k9s
if ! command -v k9s &> /dev/null; then
    echo "Installing k9s..."
    K9S_VERSION="0.51.0"
    curl -fsSL "https://github.com/derailed/k9s/releases/download/v${K9S_VERSION}/k9s_Linux_amd64.tar.gz" | tar -xz -C /tmp k9s
    sudo mv /tmp/k9s /usr/local/bin/k9s
    sudo chmod +x /usr/local/bin/k9s
fi

echo "=== Setup Complete ==="
echo "To get started, run (from labs64.io-workspace):"
echo "  just clone   # clone the ecosystem repositories as siblings of this workspace"
echo "  just up      # build images and deploy the local cluster"
