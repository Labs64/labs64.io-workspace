#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, and pipeline failures
IFS=$'\n\t'       # Stricter word splitting

# =============================================================================
# Labs64.IO DevContainer egress firewall
#
# Restricts the container's outbound network traffic to a curated allowlist:
# everything Claude Code needs, plus the package registries, container
# registries and dev-tooling endpoints used across the Labs64.IO ecosystem.
#
# Adapted from the Claude Code reference container:
#   https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh
#   https://code.claude.com/docs/en/devcontainer#restrict-network-egress
#
# Runs at container start (postStartCommand). Requires NET_ADMIN + NET_RAW
# (granted via runArgs in devcontainer.json) and the packages installed by
# post-create.sh (iptables, ipset, dnsutils, aggregate, jq).
# =============================================================================

# 1. Extract Docker DNS info BEFORE any flushing
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# Flush existing rules and delete existing ipsets
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

# 2. Selectively restore ONLY internal Docker DNS resolution
if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "Restoring Docker DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
else
    echo "No Docker DNS rules to restore"
fi

# First allow DNS and localhost before any restrictions
# Allow outbound DNS (UDP + TCP for large responses)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
# Allow inbound DNS responses
iptables -A INPUT -p udp --sport 53 -j ACCEPT
iptables -A INPUT -p tcp --sport 53 -m state --state ESTABLISHED -j ACCEPT
# Allow outbound SSH
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT
# Allow inbound SSH responses
iptables -A INPUT -p tcp --sport 22 -m state --state ESTABLISHED -j ACCEPT
# Allow localhost
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Create ipset with CIDR support
ipset create allowed-domains hash:net

# -----------------------------------------------------------------------------
# GitHub IP ranges (web + api + git + pages)
#
# Covers github.com, api.github.com, raw.githubusercontent.com,
# codeload.github.com, *.githubusercontent.com and GitHub Pages
# (labs64.github.io Helm chart repo). Sources: repo clones/pulls, devcontainer
# feature installers, k3d/helm-diff/just install scripts, gh CLI.
# -----------------------------------------------------------------------------
echo "Fetching GitHub IP ranges..."
gh_ranges=$(curl -s https://api.github.com/meta)
if [ -z "$gh_ranges" ]; then
    echo "ERROR: Failed to fetch GitHub IP ranges"
    exit 1
fi

if ! echo "$gh_ranges" | jq -e '.web and .api and .git and .pages' >/dev/null; then
    echo "ERROR: GitHub API response missing required fields"
    exit 1
fi

echo "Processing GitHub IPs..."
while read -r cidr; do
    if [[ ! "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
        echo "ERROR: Invalid CIDR range from GitHub meta: $cidr"
        exit 1
    fi
    echo "Adding GitHub range $cidr"
    ipset add allowed-domains "$cidr" -exist
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git + .pages)[]' | aggregate -q)

# -----------------------------------------------------------------------------
# Domain allowlist
#
# resolve_and_add <required|optional> <domain...>
#   required  -> abort the firewall setup if the domain cannot be resolved
#   optional  -> warn and continue (best-effort: telemetry, editor assets and
#                CDN-backed registries whose A records are volatile)
# -----------------------------------------------------------------------------
resolve_and_add() {
    local mode="$1"; shift
    local domain ips ip
    for domain in "$@"; do
        echo "Resolving $domain..."
        ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}')
        if [ -z "$ips" ]; then
            if [ "$mode" = "required" ]; then
                echo "ERROR: Failed to resolve required domain $domain"
                exit 1
            fi
            echo "WARNING: Failed to resolve optional domain $domain - skipping"
            continue
        fi
        while read -r ip; do
            if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
                echo "ERROR: Invalid IP from DNS for $domain: $ip"
                exit 1
            fi
            echo "Adding $ip for $domain"
            ipset add allowed-domains "$ip" -exist
        done < <(echo "$ips")
    done
}

# --- Required: core services the toolchain cannot build without ---
resolve_and_add required \
    "api.anthropic.com" \
    "auth.openai.com" \
    "chatgpt.com" \
    "api.openai.com" \
    "registry.npmjs.org" \
    "repo.maven.apache.org" \
    "repo1.maven.org" \
    "pypi.org" \
    "files.pythonhosted.org" \
    "index.crates.io" \
    "static.crates.io" \
    "ports.ubuntu.com" \
    "archive.ubuntu.com" \
    "security.ubuntu.com" \
    "download.docker.com"

# --- Optional: Claude Code / VS Code telemetry & editor assets ---
# statsig.anthropic.com/statsig.com back feature-flagging & telemetry, not the
# core API — and their DNS records are CDN-backed and can flake/NXDOMAIN.
# Best-effort so a transient resolution failure doesn't kill container start.
resolve_and_add optional \
    "sentry.io" \
    "statsig.anthropic.com" \
    "statsig.com" \
    "marketplace.visualstudio.com" \
    "vscode.blob.core.windows.net" \
    "update.code.visualstudio.com"

# Marketplace API responses point to publisher-specific asset hosts. Include
# both documented suffixes for the configured extensions and extension-pack
# dependencies (for example redhat.java and VS IntelliCode).
for publisher in \
    vscjava vmware ms-python vue ms-azuretools ms-kubernetes-tools nefrob \
    anthropic openai github redhat visualstudioexptteam; do
    resolve_and_add optional \
        "${publisher}.gallery.vsassets.io" \
        "${publisher}.gallerycdn.vsassets.io"
done

# --- Optional: GitHub Copilot authentication, inference and telemetry ---
# GitHub publishes wildcard allowlist entries, while this IP-based firewall
# needs concrete hostnames. These cover the public API and the plan-specific
# endpoints currently used by VS Code Copilot clients.
resolve_and_add optional \
    "api.githubcopilot.com" \
    "api.individual.githubcopilot.com" \
    "api.business.githubcopilot.com" \
    "api.enterprise.githubcopilot.com" \
    "copilot-proxy.githubusercontent.com" \
    "origin-tracker.githubusercontent.com" \
    "copilot-telemetry.githubusercontent.com" \
    "collector.github.com" \
    "default.exp-tas.com"

# --- Optional: container registries (image pulls for k3d / helm workloads) ---
# NOTE: with docker-outside-of-docker most `docker pull`/`docker build` traffic
# egresses via the host daemon, not this namespace; these entries cover
# in-container pulls (helm OCI, skopeo, direct registry probes).
resolve_and_add optional \
    "ghcr.io" \
    "pkg-containers.githubusercontent.com" \
    "registry-1.docker.io" \
    "index.docker.io" \
    "auth.docker.io" \
    "production.cloudflare.docker.com" \
    "production.cloudfront.docker.com" \
    "mcr.microsoft.com"

# --- Optional: Helm chart repositories & dev-tooling installers ---
resolve_and_add optional \
    "charts.bitnami.com" \
    "repo.broadcom.com" \
    "charts.external-secrets.io" \
    "get.helm.sh" \
    "just.systems" \
    "get.sdkman.io" \
    "api.sdkman.io" \
    "sh.rustup.rs" \
    "static.rust-lang.org"

# --- Optional: host.docker.internal (k3d API server, local OIDC provider,
# Cerbos PDP and other host-side services reached from the container, e.g.
# labs64.io-authproxy/traefik-authproxy and labs64.io-helm-charts justfiles).
# The docker embedded DNS resolves this to the host gateway IP, which is
# normally inside HOST_NETWORK below, but resolving it explicitly here keeps
# the allowlist correct even if that mapping ever differs. ---
resolve_and_add optional "host.docker.internal"

# --- Dynamic IP Updates ---
# Some domains (like registry-1.docker.io on AWS) cycle their IPs constantly via
# round-robin DNS. A one-time resolution at startup will quickly become stale.
# We run a tiny background loop to keep the ipset updated with new IPs.
(
    while true; do
        for domain in "registry-1.docker.io"; do
            dig +short "$domain" 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | while read -r ip; do
                ipset add allowed-domains "$ip" -exist 2>/dev/null || true
            done
        done
        sleep 60
    done
) &

# Get host IP from default route
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
    echo "ERROR: Failed to detect host IP"
    exit 1
fi

HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
echo "Host network detected as: $HOST_NETWORK"

# Set up remaining iptables rules
# Allow the host network (Docker bridge) - reaches the host daemon, the local
# image registry and the k3d API server exposed on the host.
iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# Set default policies to DROP first
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# First allow established connections for already approved traffic
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Then allow only specific outbound traffic to allowed domains
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

# Explicitly REJECT all other outbound traffic for immediate feedback
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

echo "Firewall configuration complete"
echo "Verifying firewall rules..."
if curl --connect-timeout 5 https://example.com >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - was able to reach https://example.com"
    exit 1
else
    echo "Firewall verification passed - unable to reach https://example.com as expected"
fi

# Verify GitHub API access
if ! curl --connect-timeout 5 https://api.github.com/zen >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - unable to reach https://api.github.com"
    exit 1
else
    echo "Firewall verification passed - able to reach https://api.github.com as expected"
fi
