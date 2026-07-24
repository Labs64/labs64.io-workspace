#!/usr/bin/env bash
set -euo pipefail

echo "=== Labs64.IO DevContainer Setup ==="

# Install egress-firewall dependencies and stage the init script.
# The firewall itself is (re)applied on every container start via
# postStartCommand -> /usr/local/bin/init-firewall.sh (see devcontainer.json).
echo "Installing firewall dependencies..."
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends iptables ipset dnsutils aggregate jq
sudo install -m 0755 "$(dirname "$0")/init-firewall.sh" /usr/local/bin/init-firewall.sh

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

echo "=== Setup Complete ==="
echo "To get started, run:"
echo "cd labs64.io-helm-charts && just build-images && just up"
