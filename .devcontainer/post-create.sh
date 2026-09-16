#!/usr/bin/env bash
set -euo pipefail

echo "=== Labs64.IO DevContainer Setup ==="

# Removes a legacy whole-directory shared-skills symlink at $CLAUDE_CONFIG_DIR/skills or
# $CODEX_HOME/skills, if one is still present. Such a symlink breaks scripts/sync-skills.sh
# below: its `mkdir -p` is a no-op on an existing symlink, so the per-skill loop then reads
# the shared skill directories themselves through it, mistaking each one for an
# already-present personal skill and skipping it.
#
# TODO(remove after 2027-01-01): delete this block once it has gone a full quarter without
# ever printing "Removing legacy...". Until then it's a harmless no-op for anyone already
# migrated.
SKILLS_SRC=/workspaces/labs64.io-workspace/.agents/skills
for skills_dir in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" "${CODEX_HOME:-$HOME/.codex}/skills"; do
  if [ -L "$skills_dir" ] && [ "$(readlink "$skills_dir")" = "$SKILLS_SRC" ]; then
    echo "Removing legacy whole-directory shared-skills symlink at $skills_dir..."
    rm "$skills_dir"
  fi
done

# Symlinks each shared skill into Claude Code's and Codex CLI's user-level skills
# directory. Runs once at container creation, so a newly-added shared skill needs a
# container rebuild, or `just sync-skills`, before it shows up in an already-running
# container. See scripts/sync-skills.sh for the full rationale and AGENTS.md's "Skills"
# section.
"$(dirname "$0")/../scripts/sync-skills.sh"

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
