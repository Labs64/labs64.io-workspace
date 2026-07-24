REPOS := "labs64.io-docs labs64.io-docs-internal labs64.io-devops labs64.io-tests labs64.io-helm-charts labs64.io-commons labs64.io-authproxy labs64.io-auditflow labs64.io-checkout labs64.io-customer-portal labs64.io-payment-gateway labs64.io-website"
GITHUB_ORG := "https://github.com/Labs64"

# List available commands
default:
    @just --list

# Clone all ecosystem repositories
clone:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ ! -d "$repo" ]; then
            echo "Cloning $repo..."
            remote_repo="$repo"
            if [ "$repo" = "labs64.io-website" ]; then
                remote_repo="labs64.io"
            fi
            git clone "{{GITHUB_ORG}}/$remote_repo.git" "$repo"
        else
            echo "$repo already exists, skipping."
        fi
    done

# Pull latest master/main on all repositories
pull:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ -d "$repo" ]; then
            echo "Pulling $repo..."
            git -C "$repo" pull
        fi
    done

# Show git status across all repositories
status:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ -d "$repo" ]; then
            echo "=== $repo ==="
            git -C "$repo" status -s
        fi
    done

# Build and push all module images to local registry (localhost:5005)
build module="all":
    @echo "=== Building dev container ==="
    @docker build -t labs64io-builder -f scripts/Dockerfile.builder scripts/
    @echo "=== Running build in dev container ==="
    @export MODULE='{{module}}'; \
    docker run --rm --network host --name "labs64io-builder-${MODULE:-all}-$$" \
        -v $(pwd):/workspace \
        -v labs64-m2-cache:/root/.m2 \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -w /workspace \
        labs64io-builder \
        ./scripts/build-images.sh "${MODULE:-all}"

# Start the entire local cluster
up:
    @cd labs64.io-helm-charts && just cluster-up
    @just build
    @cd labs64.io-helm-charts && just up

# Tear down the local cluster (registry and images are untouched)
down:
    @cd labs64.io-helm-charts && just cluster-down

# Tail error logs for all modules, or `just logs <app>` for one (e.g. `just logs checkout`)
logs app="":
    #!/usr/bin/env bash
    set -euo pipefail
    cd labs64.io-helm-charts
    if [ -n "{{app}}" ]; then
        just logs {{app}}
    else
        just logs-errors
    fi

# Check that required local tooling is installed (Docker, k3d, Helm (+ helm-diff), Helmfile, kubectl, just; optional Java/Maven/Node)
doctor:
    #!/usr/bin/env bash
    set -euo pipefail
    ok=0; missing=0
    check() {
        local name=$1 cmd=$2 hint=$3
        if command -v "$cmd" >/dev/null 2>&1; then
            echo "✅ $name: $("${@:4}" 2>&1 | head -1)"
            ok=$((ok + 1))
        else
            echo "❌ $name not found. Install: $hint"
            missing=$((missing + 1))
        fi
    }
    check "Docker"   docker   "https://www.docker.com/products/docker-desktop/" docker --version
    check "k3d"      k3d      "https://k3d.io/"                                 k3d --version
    check "Helm"     helm     "https://helm.sh/"                                helm version --short
    check "Helmfile" helmfile "https://helmfile.io/"                            helmfile --version
    check "kubectl"  kubectl  "https://kubernetes.io/docs/tasks/tools/"         kubectl version --client
    check "just"     just     "https://github.com/casey/just"                  just --version
    check "curl"     curl     "https://curl.se/"                                curl --version
    echo "--- optional (only needed to build images locally) ---"
    check "Java"  java "Temurin 25, https://adoptium.net/"     java --version
    check "Maven" mvn  "3.6.3+, https://maven.apache.org/"     mvn --version
    check "Node"  node "22+, https://nodejs.org/"              node --version
    check "k9s"   k9s  "https://k9scli.io/"                    k9s version -s
    echo "---"
    if command -v helm >/dev/null 2>&1; then
        if helm plugin list 2>/dev/null | grep -q '^diff'; then
            echo "✅ helm-diff plugin installed"
        else
            echo "❌ helm-diff plugin missing. Install: helm plugin install https://github.com/databus23/helm-diff"
            missing=$((missing + 1))
        fi
    fi
    echo "---"
    echo "$ok OK, $missing missing"
    [ "$missing" -eq 0 ]

# Verify all Java modules can resolve their dependencies offline (catches broken/missing artifacts early)
verify-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    source scripts/lib/progress.sh
    # labs64.io-commons libraries are consumed by other modules via the local Maven repo, so they
    # must be installed (like a real build does), not just dependency:go-offline'd, before the
    # modules below can resolve against them.
    for dir in \
        labs64.io-commons/auth-context-java \
        labs64.io-commons/openapi-spring-boot-starter \
        labs64.io-commons/authz-queryplan-jpa; do
        if [ -d "$dir" ]; then
            run_step "deps: $dir (install)" -- bash -c "cd '$dir' && mvn -B install -Dmaven.test.skip=true"
        else
            echo "skip: $dir (not cloned, run 'just clone')"
        fi
    done
    for dir in \
        labs64.io-auditflow/auditflow-api \
        labs64.io-auditflow/auditflow-be \
        labs64.io-checkout/checkout-be \
        labs64.io-payment-gateway; do
        if [ -d "$dir" ]; then
            run_step "deps: $dir" -- bash -c "cd '$dir' && mvn -B dependency:go-offline"
        else
            echo "skip: $dir (not cloned, run 'just clone')"
        fi
    done

# Run the full test suite across all modules
test:
    @cd labs64.io-tests && just all

# Run the fast PR-gating smoke tests across all modules
smoke:
    @cd labs64.io-tests && just smoke

# Run the full nightly-shape regression test suite
regression:
    @cd labs64.io-tests && just regression
