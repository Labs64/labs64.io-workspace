#!/usr/bin/env bash
set -euo pipefail

echo "=== Labs64.IO DevContainer Setup ==="

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
