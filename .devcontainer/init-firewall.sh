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
#
# -----------------------------------------------------------------------------
# Adding a host without rebuilding the container
# -----------------------------------------------------------------------------
# Either add the domain to one of the resolve_and_add lists below, or - for
# one-off/ad-hoc hosts - drop it into /etc/l64-firewall-extra-domains (one
# domain per line, '#' comments allowed):
#
#     echo "example.com" | sudo tee -a /etc/l64-firewall-extra-domains
#
# Then re-apply from inside the container:
#
#     sudo bash /workspaces/labs64.io-workspace/.devcontainer/init-firewall.sh
#
# Running the repo copy re-installs itself to /usr/local/bin on success, so an
# edit here also survives the next container start (postStartCommand runs the
# installed copy).
#
# The script is idempotent and safe to re-run any number of times: the allowlist
# is rebuilt in a staging ipset and swapped in atomically, so the live firewall
# is never taken down while domains are being resolved. If it aborts partway
# through it fails closed (egress DROP) rather than leaving egress wide open.
# =============================================================================

IPSET_NAME="allowed-domains"
IPSET_STAGING="allowed-domains-stg"
REFRESH_PID_FILE="/run/l64-firewall-refresh.pid"
EXTRA_DOMAINS_FILE="/etc/l64-firewall-extra-domains"
INSTALL_PATH="/usr/local/bin/init-firewall.sh"

FIREWALL_OK=0        # set to 1 once the final ruleset is in place and verified

# Host IP / network is needed both by lockdown() and by the final ruleset, so
# resolve it up front.
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
    echo "ERROR: Failed to detect host IP"
    exit 1
fi
HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
echo "Host network detected as: $HOST_NETWORK"

# -----------------------------------------------------------------------------
# Fail closed: if anything below aborts (or a bootstrap egress window was
# opened and never closed), leave the container with egress blocked instead of
# unrestricted. Loopback + the Docker host network stay reachable so the dev
# session survives and the script can simply be re-run.
# -----------------------------------------------------------------------------
lockdown() {
    echo "Locking down egress (firewall setup did not complete)..."
    iptables -F
    iptables -A INPUT -i lo -j ACCEPT
    iptables -A OUTPUT -o lo -j ACCEPT
    iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
    iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -P INPUT DROP
    iptables -P FORWARD DROP
    iptables -P OUTPUT DROP
}

on_exit() {
    local rc=$?
    if [ "$FIREWALL_OK" -ne 1 ]; then
        lockdown
    fi
    ipset destroy "$IPSET_STAGING" 2>/dev/null || true
    exit "$rc"
}
trap on_exit EXIT

# -----------------------------------------------------------------------------
# Bootstrap egress
#
# Populating the staging set needs DNS plus one call to api.github.com/meta. On
# a first run egress is still unrestricted; on a re-run the *live* firewall
# already permits both, so nothing has to be opened. Only a partially applied
# ruleset from an earlier failure needs a temporary window.
# -----------------------------------------------------------------------------
if curl -s --connect-timeout 5 -o /dev/null https://api.github.com/zen; then
    echo "Egress available for allowlist resolution"
else
    echo "WARNING: api.github.com unreachable - opening temporary egress window"
    iptables -P INPUT ACCEPT
    iptables -P OUTPUT ACCEPT
    iptables -P FORWARD ACCEPT
fi

# Build the new allowlist in a staging set; it is swapped into place only once
# fully populated.
ipset destroy "$IPSET_STAGING" 2>/dev/null || true
ipset create "$IPSET_STAGING" hash:net

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
    ipset add "$IPSET_STAGING" "$cidr" -exist
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
            ipset add "$IPSET_STAGING" "$ip" -exist
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
    "api.spring.io" \
    "repo.maven.apache.org" \
    "repo1.maven.org" \
    "nexus.labs64.com" \
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
# charts.external-secrets.io is a CNAME onto ghs.googlehosted.com and its IP
# rotates on a short TTL - this only seeds the ipset; DYNAMIC_DOMAINS below
# keeps it current.
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

# --- Optional: ad-hoc hosts added at runtime ---
# One domain per line; blank lines and '#' comments ignored. Add a host and
# re-run this script - no container rebuild needed:
#     echo "example.com" | sudo tee -a /etc/l64-firewall-extra-domains
if [ -f "$EXTRA_DOMAINS_FILE" ]; then
    echo "Reading extra domains from $EXTRA_DOMAINS_FILE..."
    extra_domains=()
    while read -r line; do
        line="${line%%#*}"
        line="$(echo "$line" | tr -d '[:space:]')"
        [ -n "$line" ] && extra_domains+=("$line")
    done < "$EXTRA_DOMAINS_FILE"
    if [ ${#extra_domains[@]} -gt 0 ]; then
        resolve_and_add optional "${extra_domains[@]}"
    fi
fi

# -----------------------------------------------------------------------------
# Swap the freshly built allowlist in
#
# `ipset swap` exchanges the contents of two sets by name, so iptables rules
# referencing $IPSET_NAME keep working and never point at a half-built set.
# Create an empty $IPSET_NAME first in case this is the initial run.
# -----------------------------------------------------------------------------
ipset create "$IPSET_NAME" hash:net -exist
ipset swap "$IPSET_STAGING" "$IPSET_NAME"
ipset destroy "$IPSET_STAGING"
echo "Allowlist installed ($(ipset save "$IPSET_NAME" | grep -c '^add ' || true) entries)"

# -----------------------------------------------------------------------------
# Rebuild the ruleset
#
# From here on no network access is needed, so the chains can be torn down and
# rebuilt from scratch - that is what makes a re-run pick up rule changes.
# Policies go to DROP *before* the flush so the rebuild window is closed, not
# open.
# -----------------------------------------------------------------------------
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# 1. Extract Docker DNS info BEFORE any flushing
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# Flush existing rules (the ipset is referenced by nothing once OUTPUT is empty)
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X

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

# Allow the host network (Docker bridge) - reaches the host daemon, the local
# image registry and the k3d API server exposed on the host.
iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# First allow established connections for already approved traffic
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Then allow only specific outbound traffic to allowed domains
iptables -A OUTPUT -m set --match-set "$IPSET_NAME" dst -j ACCEPT

# Explicitly REJECT all other outbound traffic for immediate feedback
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# --- Dynamic IP Updates ---
# Some domains cycle their IPs constantly, so the single resolution done above
# goes stale within minutes. Two flavours of this:
#
#   * round-robin / geo-balanced fleets (registry-1.docker.io on AWS)
#   * CNAMEs onto a shared hosting frontend whose A records rotate
#     (charts.external-secrets.io -> ghs.googlehosted.com, ~70s TTL, and the
#     answer differs per resolver)
#
# A background loop re-resolves them and unions every observed IP into the
# ipset. Poll faster than the shortest TTL in the list (70s for ghs) so the
# refresh lands before the resolver cache expires and hands the client an
# address the firewall has never seen.
#
# The PID is tracked so a re-run replaces the previous loop instead of stacking
# another one on top of it.
DYNAMIC_DOMAINS=(
    "registry-1.docker.io"
    "charts.external-secrets.io"
    # charts.bitnami.com is CloudFront-fronted and rotates across entire /24s, not just
    # within one: observed 18.172.112.{8,76,80,82} and, twenty minutes later,
    # 54.230.228.{10,30,45,58}. Seeding it once above is therefore not enough — the
    # allowlist goes stale on the next rotation and `helmfile`/`helm repo update` fail
    # with "no route to host" for rabbitmq, postgresql and redis. That intermittency is
    # what made this look like a flaky network rather than a stale ipset.
    "charts.bitnami.com"
)
DYNAMIC_REFRESH_INTERVAL=30

if [ -f "$REFRESH_PID_FILE" ]; then
    old_pid=$(cat "$REFRESH_PID_FILE" 2>/dev/null || true)
    if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
        echo "Stopping previous dynamic-refresh loop (pid $old_pid)..."
        kill "$old_pid" 2>/dev/null || true
    fi
    rm -f "$REFRESH_PID_FILE"
fi

(
    # Detach from the parent's traps and from SIGHUP so the loop survives both
    # this script exiting and the terminal it was launched from closing.
    trap - EXIT
    trap '' HUP
    while true; do
        for domain in "${DYNAMIC_DOMAINS[@]}"; do
            # +short on a CNAME prints the chain too; keep only the A records.
            dig +short "$domain" A 2>/dev/null \
                | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' \
                | while read -r ip; do
                    ipset add "$IPSET_NAME" "$ip" -exist 2>/dev/null || true
                done
        done
        sleep "$DYNAMIC_REFRESH_INTERVAL"
    done
) >/dev/null 2>&1 &
echo $! > "$REFRESH_PID_FILE"
echo "Dynamic-refresh loop started (pid $(cat "$REFRESH_PID_FILE"))"

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

FIREWALL_OK=1

# Keep the installed copy in sync when run from the repo, so edits made here
# also apply on the next container start (postStartCommand runs the installed
# copy, not this file).
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
if [ "$SCRIPT_PATH" != "$INSTALL_PATH" ] && ! cmp -s "$SCRIPT_PATH" "$INSTALL_PATH"; then
    echo "Updating $INSTALL_PATH from $SCRIPT_PATH"
    install -m 0755 "$SCRIPT_PATH" "$INSTALL_PATH"
fi
