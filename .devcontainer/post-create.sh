#!/usr/bin/env bash
set -euo pipefail

echo "=== Labs64.IO DevContainer Setup ==="

# The ecosystem repos are bind-mounted from the host, so their owner uid rarely matches the
# container user and git aborts with "detected dubious ownership". The container is a
# single-user sandbox, so trust every directory.
git config --global --replace-all safe.directory '*'

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

# CLI tool versions come from the workspace's single tool-versions.env — the same file CI
# installs from (.github/actions/setup-k8s-tools) and `just doctor` checks against. Helm and
# Terraform are installed by devcontainer features; devcontainer.json pins them to the same
# values (`just check-pins` verifies that).
# shellcheck source=../tool-versions.env
source "$(dirname "$0")/../tool-versions.env"
ARCH="$(dpkg --print-architecture)"

# Install k3d
if ! command -v k3d &> /dev/null; then
    echo "Installing k3d v${K3D_VERSION}..."
    curl -fsSL "https://raw.githubusercontent.com/k3d-io/k3d/v${K3D_VERSION}/install.sh" | TAG="v${K3D_VERSION}" bash
fi

# Install just
if ! command -v just &> /dev/null; then
    echo "Installing just ${JUST_VERSION}..."
    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | sudo bash -s -- --tag "${JUST_VERSION}" --to /usr/local/bin
fi

# Install helmfile
if ! command -v helmfile &> /dev/null; then
    echo "Installing helmfile ${HELMFILE_VERSION}..."
    curl -fsSL "https://github.com/helmfile/helmfile/releases/download/v${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION}_linux_${ARCH}.tar.gz" | tar -xz -C /tmp helmfile
    sudo mv /tmp/helmfile /usr/local/bin/helmfile
    sudo chmod +x /usr/local/bin/helmfile
fi

# Install required Helm plugins
echo "Installing Helm plugins..."
helm plugin install --version "v${HELM_DIFF_VERSION}" --verify=false https://github.com/databus23/helm-diff 2>/dev/null || true
helm plugin install --version "${HELM_SCHEMA_VERSION}" --verify=false https://github.com/dadav/helm-schema 2>/dev/null || true

# Install Checkov (Terraform posture/security scanner — labs64.io-devops/terraform's `just
# checkov` and its CI validate workflow both expect it on PATH). pipx keeps it in its own venv,
# isolated from the container's system/dev Python environments, same reasoning as graphify's uv
# tool install above. Needs pypi.org/files.pythonhosted.org, both in init-firewall.sh's required
# allowlist already; --skip-download at call time keeps the scan itself off the network entirely.
if ! command -v checkov &> /dev/null; then
    echo "Installing checkov..."
    pipx install checkov --quiet
fi

# Install k9s
if ! command -v k9s &> /dev/null; then
    echo "Installing k9s ${K9S_VERSION}..."
    curl -fsSL "https://github.com/derailed/k9s/releases/download/v${K9S_VERSION}/k9s_Linux_${ARCH}.tar.gz" | tar -xz -C /tmp k9s
    sudo mv /tmp/k9s /usr/local/bin/k9s
    sudo chmod +x /usr/local/bin/k9s
fi

echo "=== Setup Complete ==="
echo "To get started, run (from labs64.io-workspace):"
echo "  just clone   # clone the ecosystem repositories as siblings of this workspace"
echo "  just up      # build images and deploy the local cluster"
