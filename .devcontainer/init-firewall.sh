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
if curl -s --connect-timeout 5 -o /dev/null https://api.github.com/zen \
    && curl -s --connect-timeout 5 -o /dev/null https://ip-ranges.amazonaws.com/ip-ranges.json; then
    echo "Egress available for allowlist resolution"
else
    echo "WARNING: bootstrap host(s) unreachable - opening temporary egress window"
    # A prior successful run leaves its own OUTPUT REJECT rule (anything not in
    # the live ipset) installed in the chain. That's a rule, not a default
    # policy, so it still matches and wins even after the policy is flipped to
    # ACCEPT below. Flush it out too - the ruleset gets rebuilt from scratch
    # later regardless, so there's nothing to preserve here.
    iptables -F
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
# AWS S3 IP ranges (eu-west-1)
#
# S3's regional endpoint, its bucket-specific virtual-hosted hostnames, and the
# internal s3-r-w.<region>.amazonaws.com redirect target it sends new buckets
# to all round-robin across a large, constantly-rotating fleet - a single dig
# snapshot (what resolve_and_add does for every other domain) only ever
# captures a handful of the possible backend IPs, so S3 calls fail
# unpredictably once traffic lands on an address outside that snapshot. AWS
# publishes the full CIDR list for exactly this purpose, filterable by
# service/region - same idea as the GitHub ranges above, applied to S3.
# -----------------------------------------------------------------------------
echo "Fetching AWS S3 IP ranges (eu-west-1)..."
aws_ranges=$(curl -s https://ip-ranges.amazonaws.com/ip-ranges.json)
if [ -z "$aws_ranges" ]; then
    echo "ERROR: Failed to fetch AWS IP ranges"
    exit 1
fi

if ! echo "$aws_ranges" | jq -e '.prefixes' >/dev/null; then
    echo "ERROR: AWS ip-ranges response missing required fields"
    exit 1
fi

echo "Processing AWS S3 IPs..."
while read -r cidr; do
    if [[ ! "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
        echo "ERROR: Invalid CIDR range from AWS ip-ranges: $cidr"
        exit 1
    fi
    echo "Adding AWS S3 range $cidr"
    ipset add "$IPSET_STAGING" "$cidr" -exist
done < <(echo "$aws_ranges" | jq -r '.prefixes[] | select(.service=="S3" and (.region=="eu-west-1" or .region=="GLOBAL")) | .ip_prefix' | aggregate -q)

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
    "download.eclipse.org" \
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

# --- Optional: Terraform CLI (labs64.io-devops/terraform, `just bootstrap-ci`) ---
# registry.terraform.io serves the provider discovery document; the actual
# provider binaries are then fetched from releases.hashicorp.com. Both are
# CDN-fronted (Fastly) and rotate IPs, so they're also kept fresh in
# DYNAMIC_DOMAINS below.
resolve_and_add optional \
    "registry.terraform.io" \
    "releases.hashicorp.com"

# --- Optional: AWS API endpoints (labs64.io-devops terraform apply, aws-cli,
# IAM Identity Center / SSO login) ---
# `sso.<region>`/`oidc.<region>`/`signin.aws.amazon.com` cover `aws sso login` /
# `aws configure sso` (device-authorization + token exchange +
# ListAccounts/ListAccountRoles); the rest are the regional service endpoints
# Terraform's AWS provider and the AWS CLI talk to for this repo's resources
# (VPC/EC2, EKS, RDS, ElastiCache, Amazon MQ, S3, Secrets Manager, KMS, IAM,
# STS, CloudWatch Logs/Metrics, autoscaling for EKS managed node groups, SNS
# for cost-alert notifications). IAM is a global (non-regional) endpoint; STS
# is resolved both regionally (the CLI v2 default) and globally as a fallback.
# Budgets and Cost Explorer/Cost Anomaly Detection are also global services —
# both are always hosted in us-east-1 regardless of the provider's configured
# region, hence the literal "us-east-1" in those two hostnames below.
#
# NOT covered here: the per-cluster EKS API server endpoint itself
# (`<id>.gr7.eu-west-1.eks.amazonaws.com`) — that hostname is an opaque per-cluster ID assigned by
# AWS, unknowable until the cluster exists, so it can never be in this static list. labs64.io-devops's
# `just kubeconfig <env>` handles this automatically now (looks up the cluster's endpoint, appends
# it to /etc/l64-firewall-extra-domains below if not already present, and re-runs this script) —
# see its justfile. The manual fallback, if ever needed for a cluster outside that workflow:
#     echo "<id>.gr7.<region>.eks.amazonaws.com" | sudo tee -a /etc/l64-firewall-extra-domains
#     sudo bash /usr/local/bin/init-firewall.sh
resolve_and_add optional \
    "signin.aws.amazon.com" \
    "eu-west-1.signin.aws.amazon.com" \
    "oidc.eu-west-1.amazonaws.com" \
    "portal.sso.eu-west-1.amazonaws.com" \
    "sso.eu-west-1.amazonaws.com" \
    "sts.eu-west-1.amazonaws.com" \
    "sts.amazonaws.com" \
    "iam.amazonaws.com" \
    "ec2.eu-west-1.amazonaws.com" \
    "eks.eu-west-1.amazonaws.com" \
    "oidc.eks.eu-west-1.amazonaws.com" \
    "rds.eu-west-1.amazonaws.com" \
    "elasticache.eu-west-1.amazonaws.com" \
    "mq.eu-west-1.amazonaws.com" \
    "secretsmanager.eu-west-1.amazonaws.com" \
    "kms.eu-west-1.amazonaws.com" \
    "logs.eu-west-1.amazonaws.com" \
    "monitoring.eu-west-1.amazonaws.com" \
    "autoscaling.eu-west-1.amazonaws.com" \
    "sns.eu-west-1.amazonaws.com" \
    "scheduler.eu-west-1.amazonaws.com" \
    "budgets.amazonaws.com" \
    "ce.us-east-1.amazonaws.com" \
    "guardduty.eu-west-1.amazonaws.com" \
    "config.eu-west-1.amazonaws.com" \
    "securityhub.eu-west-1.amazonaws.com" \
    "access-analyzer.eu-west-1.amazonaws.com" \
    "cloudtrail.eu-west-1.amazonaws.com" \
    "s3control.eu-west-1.amazonaws.com" \
    "route53.amazonaws.com" \
    "acm.eu-west-1.amazonaws.com" \
    "elasticloadbalancing.eu-west-1.amazonaws.com" \
    "wafv2.eu-west-1.amazonaws.com"

# --- Optional: payment provider server APIs ---
# Payment Gateway uses these endpoints for Stripe Checkout, PayPal Orders,
# captures, OAuth tokens and PayPal webhook signature verification.
resolve_and_add optional \
    "api.stripe.com" \
    "api-m.sandbox.paypal.com" \
    "api-m.paypal.com"

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
    "production.cloudfront.docker.com"
    "charts.external-secrets.io"
    # charts.bitnami.com is CloudFront-fronted and rotates across entire /24s, not just
    # within one: observed 18.172.112.{8,76,80,82} and, twenty minutes later,
    # 54.230.228.{10,30,45,58}. Seeding it once above is therefore not enough — the
    # allowlist goes stale on the next rotation and `helmfile`/`helm repo update` fail
    # with "no route to host" for rabbitmq, postgresql and redis. That intermittency is
    # what made this look like a flaky network rather than a stale ipset.
    "charts.bitnami.com"
    # Terraform's provider registry/release hosts are Fastly-fronted and rotate.
    "registry.terraform.io"
    "releases.hashicorp.com"
    # PSP API hosts are backed by distributed infrastructure and can return
    # different addresses as DNS caches and routing change.
    "api.stripe.com"
    "api-m.sandbox.paypal.com"
    "api-m.paypal.com"
    # IAM/STS and the other regional AWS control-plane endpoints below are backed by a fleet
    # that rotates over time, same failure mode as the S3/PayPal/Stripe entries above: a single
    # resolution goes stale and every `aws`/terraform-provider-aws call against it (bootstrap-ci's
    # IAM role creation, `aws sts get-caller-identity`, `terraform apply` on VPC/EKS/RDS/etc.)
    # starts silently REJECTing and hanging in the SDK's retry loop for many minutes, looking
    # exactly like a stuck/hung process rather than a firewall problem - e.g. `aws_vpc.main`
    # sitting on "Still creating..." long after the VPC is already Available in the console,
    # because the CreateVpc call landed on an IP this ipset had, but the follow-up DescribeVpcs
    # poll landed on one it didn't. S3 gets full CIDR-range coverage above (service=S3 in AWS's
    # ip-ranges.json) instead of this dynamic-refresh treatment; these endpoints don't have their
    # own ip-ranges.json service tag (only the account-wide "AMAZON" one, far too broad to
    # allow-list), so periodic single-IP refresh is the practical fix here.
    "iam.amazonaws.com"
    "sts.eu-west-1.amazonaws.com"
    "sts.amazonaws.com"
    "ec2.eu-west-1.amazonaws.com"
    "eks.eu-west-1.amazonaws.com"
    "oidc.eks.eu-west-1.amazonaws.com"
    "rds.eu-west-1.amazonaws.com"
    "elasticache.eu-west-1.amazonaws.com"
    "mq.eu-west-1.amazonaws.com"
    "secretsmanager.eu-west-1.amazonaws.com"
    "kms.eu-west-1.amazonaws.com"
    "logs.eu-west-1.amazonaws.com"
    "monitoring.eu-west-1.amazonaws.com"
    "autoscaling.eu-west-1.amazonaws.com"
    "sns.eu-west-1.amazonaws.com"
    "budgets.amazonaws.com"
    "ce.us-east-1.amazonaws.com"
    "guardduty.eu-west-1.amazonaws.com"
    "config.eu-west-1.amazonaws.com"
    "securityhub.eu-west-1.amazonaws.com"
    "access-analyzer.eu-west-1.amazonaws.com"
    "cloudtrail.eu-west-1.amazonaws.com"
    "s3control.eu-west-1.amazonaws.com"
    # Edge stack (Route 53 zone, ACM certificate, ALB/NLB target groups, WAFv2) - same rotating-fleet
    # failure mode: "Still creating..." hangs while the SDK retries against REJECTed IPs.
    "route53.amazonaws.com"
    "acm.eu-west-1.amazonaws.com"
    "elasticloadbalancing.eu-west-1.amazonaws.com"
    "wafv2.eu-west-1.amazonaws.com"
)
# 10s, not 30s: IAM/STS/EC2's global control-plane fleets are large enough that a single DNS
# answer only ever returns a small slice of them, and each answer is cached for its TTL — querying
# the same domain twice inside that TTL just returns the identical slice, it doesn't broaden
# coverage. What actually broadens coverage is elapsed wall-clock time (letting the cache expire
# and re-querying upstream), so a shorter loop interval accumulates a wider slice of the fleet
# faster than a longer one would, for the same per-query cost.
DYNAMIC_REFRESH_INTERVAL=10

if [ -f "$REFRESH_PID_FILE" ]; then
    old_pid=$(cat "$REFRESH_PID_FILE" 2>/dev/null || true)
    if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
        echo "Stopping previous dynamic-refresh loop (pid $old_pid)..."
        kill "$old_pid" 2>/dev/null || true
    fi
    rm -f "$REFRESH_PID_FILE"
fi

# setsid (new session, no controlling terminal — immune to SIGHUP by construction, the
# `trap '' HUP` below is belt-and-suspenders) with stdin explicitly detached from /dev/null: a
# plain `(...) &` backgrounded subshell still inherits this shell's stdin, and in a sandboxed
# tool-call environment where each command's controlling pipe/session gets torn down when the
# call returns, that's enough to take the "background" job down with it even though nothing sent
# it a signal — it was observed dying within seconds of every init-firewall.sh run this way,
# silently defeating the whole point of a *dynamic* refresh loop (every fix in this file that
# depended on it just happened to work off that run's one-time resolve_and_add snapshot instead).
# setsid forks (the process `&` backgrounds is a short-lived wrapper that execs the real loop as
# a *different* PID, confirmed by observation), so the loop writes its own $$ to the PID file
# itself as its first action rather than relying on the caller's $! — that would capture the
# wrapper's already-dead PID, making the "stop previous loop" check above a no-op that leaves
# orphaned loops running across repeated init-firewall.sh invocations.
setsid bash -c '
    echo $$ > '"$REFRESH_PID_FILE"'
    trap "" HUP
    while true; do
        for domain in '"$(printf '%q ' "${DYNAMIC_DOMAINS[@]}")"'; do
            # +short on a CNAME prints the chain too; keep only the A records.
            dig +short "$domain" A 2>/dev/null \
                | grep -E "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$" \
                | while read -r ip; do
                    ipset add "'"$IPSET_NAME"'" "$ip" -exist 2>/dev/null || true
                done
        done
        sleep "'"$DYNAMIC_REFRESH_INTERVAL"'"
    done
' </dev/null >/dev/null 2>&1 &
disown
sleep 0.2
echo "Dynamic-refresh loop started (pid $(cat "$REFRESH_PID_FILE" 2>/dev/null))"

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
