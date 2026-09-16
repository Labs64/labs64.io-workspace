#!/usr/bin/env bash
set -euo pipefail

echo "=== Labs64.IO DevContainer Setup ==="

# The ecosystem's shared skills (.agents/skills/, git-tracked in labs64.io-workspace) are
# exposed as project-level skills via git-tracked symlinks committed in the repo itself
# (.claude/skills -> ../.agents/skills, .codex/skills -> ../.agents/skills). Both Claude
# Code and Codex CLI discover project-level skills natively, so no container-boot wiring
# is needed for the primary devcontainer root. This keeps each developer's real
# $CLAUDE_CONFIG_DIR/skills and $CODEX_HOME/skills free for personal, untracked skills,
# and free for Codex's own auto-managed skills (.system/, .curated/) — neither leaks into
# this repo or into the other tool's view. See AGENTS.md's "Skills" section.
SKILLS_SRC=/workspaces/labs64.io-workspace/.agents/skills

for skills_dir in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" "${CODEX_HOME:-$HOME/.codex}/skills"; do
  if [ -L "$skills_dir" ] && [ "$(readlink "$skills_dir")" = "$SKILLS_SRC" ]; then
    echo "Removing legacy shared-skills symlink at $skills_dir..."
    rm "$skills_dir"
  fi
done

# Install egress-firewall dependencies and stage the init script.
# The firewall itself is (re)applied on every container start via
# postStartCommand -> /usr/local/bin/init-firewall.sh (see devcontainer.json).
echo "Installing firewall dependencies..."
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends iptables ipset dnsutils aggregate jq
sudo install -m 0755 "$(dirname "$0")/init-firewall.sh" /usr/local/bin/init-firewall.sh

echo "Installing python dependencies..."
pip3 install pyyaml

# Install graphify (knowledge graph CLI backing the ecosystem-wide graph at
# ../graphify-out/ — see AGENTS.md). PyPI package name is "graphifyy"; the
# installed executable is "graphify". Installed as a uv tool so it stays
# isolated from the container's system/dev Python environments.
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    pip3 install --user uv
fi
echo "Installing graphify..."
uv tool install graphifyy --quiet

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
    HELMFILE_VERSION="1.7.4"
    curl -fsSL "https://github.com/helmfile/helmfile/releases/download/v${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION}_linux_amd64.tar.gz" | tar -xz -C /tmp helmfile
    sudo mv /tmp/helmfile /usr/local/bin/helmfile
    sudo chmod +x /usr/local/bin/helmfile
fi

# Install required Helm plugins
echo "Installing Helm plugins..."
helm plugin install --version v3.15.11 --verify=false https://github.com/databus23/helm-diff 2>/dev/null || true
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
