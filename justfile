REPOS := "labs64.io-docs labs64.io-docs-internal labs64.io-devops labs64.io-tests labs64.io-helm-charts labs64.io-commons labs64.io-authproxy labs64.io-auditflow labs64.io-checkout labs64.io-customer-portal labs64.io-payment-gateway labs64.io-website"
GITHUB_ORG := "https://github.com/Labs64"
# Ecosystem root: repositories are cloned as siblings of this workspace, not inside it.
ROOT := ".."

# List available commands
default:
    @just --list

# Clone all ecosystem repositories (as siblings of this workspace)
clone:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ ! -d "{{ROOT}}/$repo" ]; then
            echo "Cloning $repo..."
            remote_repo="$repo"
            if [ "$repo" = "labs64.io-website" ]; then
                remote_repo="labs64.io"
            fi
            git clone "{{GITHUB_ORG}}/$remote_repo.git" "{{ROOT}}/$repo"
        else
            echo "$repo already exists, skipping."
        fi
    done

# Pull latest master/main on all repositories
pull:
    #!/bin/bash
    echo "Pulling workspace root..."
    git pull
    for repo in {{REPOS}}; do
        if [ -d "{{ROOT}}/$repo" ]; then
            echo "Pulling $repo..."
            git -C "{{ROOT}}/$repo" pull
        fi
    done

# Show git status across all repositories
status:
    #!/bin/bash
    echo "=== workspace root ==="
    git status -s
    for repo in {{REPOS}}; do
        if [ -d "{{ROOT}}/$repo" ]; then
            echo "=== $repo ==="
            git -C "{{ROOT}}/$repo" status -s
        fi
    done

# Build and push all module images to local registry (localhost:5005)
build module="all" verbose="1":
    #!/usr/bin/env bash
    set -euo pipefail
    builder_uid="$(id -u)"
    builder_gid="$(id -g)"
    docker_gid="$(stat -Lc '%g' /var/run/docker.sock)"
    maven_cache=/home/builder/.m2
    echo "=== Building dev container ==="
    docker build \
        --build-arg "USER_ID=${builder_uid}" \
        --build-arg "GROUP_ID=${builder_gid}" \
        -t labs64io-builder \
        -f scripts/Dockerfile.builder \
        scripts/

    # Existing installations used /root/.m2 and left this named volume owned
    # by root. Migrate it once (and again only if the invoking UID/GID changes).
    cache_owner="$(docker run --rm \
        -v "labs64-m2-cache:${maven_cache}" \
        --entrypoint stat \
        labs64io-builder \
        -c '%u:%g' "${maven_cache}")"
    if [[ "${cache_owner}" != "${builder_uid}:${builder_gid}" ]]; then
        echo "=== Migrating Maven cache ownership (${cache_owner} -> ${builder_uid}:${builder_gid}) ==="
        docker run --rm \
            --user 0:0 \
            -v "labs64-m2-cache:${maven_cache}" \
            --entrypoint chown \
            labs64io-builder \
            -R "${builder_uid}:${builder_gid}" "${maven_cache}"
    fi

    echo "=== Running build in dev container ==="
    MODULE='{{module}}'
    # The modules live next to this workspace, so mount the whole ecosystem root
    # and run the build from the workspace folder inside it.
    ws="${LOCAL_WORKSPACE_FOLDER:-$(pwd)}"
    # LOCAL_WORKSPACE_FOLDER is a host path. Docker Desktop passes a Windows
    # path into Linux dev containers, so dirname/basename cannot split it.
    case "$ws" in
        *\\*)
            workspace_name="${ws##*\\}"
            ecosystem_root="${ws%\\*}"
            ;;
        *)
            workspace_name="$(basename "$ws")"
            ecosystem_root="$(dirname "$ws")"
            ;;
    esac
    if [ -t 1 ]; then TTY_ARGS="-it"; else TTY_ARGS=""; fi; \
    docker run $TTY_ARGS --rm --network host --name "labs64io-builder-${MODULE:-all}-$$" \
        --user "${builder_uid}:${builder_gid}" \
        --group-add "${docker_gid}" \
        -e VERBOSE="{{verbose}}" \
        -e HOME=/home/builder \
        -e MAVEN_CONFIG="${maven_cache}" \
        --mount "type=bind,source=${ecosystem_root},target=/workspaces" \
        -v "labs64-m2-cache:${maven_cache}" \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -w "/workspaces/${workspace_name}" \
        labs64io-builder \
        ./scripts/build-images.sh "${MODULE:-all}"

# Start the entire local cluster
up:
    @cd {{ROOT}}/labs64.io-helm-charts && just cluster-up
    @just build
    @cd {{ROOT}}/labs64.io-helm-charts && just up

# Start the entire local cluster with OpenTelemetry
otel:
    @cd {{ROOT}}/labs64.io-helm-charts && just up-otel && just grafana

# Tear down the local cluster (cluster and registry will be destroyed)
down:
    @cd {{ROOT}}/labs64.io-helm-charts && just cluster-down

# Tail error logs for all modules, or `just logs <app>` for one (e.g. `just logs auditflow`)
logs app="":
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{ROOT}}/labs64.io-helm-charts
    if [ -n "{{app}}" ]; then
        just logs {{app}}
    else
        just logs-errors
    fi

# Check that required local tooling is installed
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
            echo "❌ helm-diff plugin missing. Install: helm plugin install https://github.com/databus23/helm-diff --version v3.15.11 --verify=false"
            missing=$((missing + 1))
        fi
    fi
    echo "---"
    echo "$ok OK, $missing missing"
    [ "$missing" -eq 0 ]

# Verify all Java modules can resolve their dependencies offline (catches broken/missing artifacts early)
verify-deps verbose="1":
    #!/usr/bin/env bash
    set -euo pipefail
    export VERBOSE="{{verbose}}"
    source scripts/lib/progress.sh
    # labs64.io-commons libraries are consumed by other modules via the local Maven repo, so they
    # must be installed (like a real build does), not just dependency:go-offline'd, before the
    # modules below can resolve against them.
    for dir in \
        {{ROOT}}/labs64.io-commons/auth-context-java \
        {{ROOT}}/labs64.io-commons/openapi-spring-boot-starter \
        {{ROOT}}/labs64.io-commons/authz-queryplan-jpa \
        {{ROOT}}/labs64.io-auditflow/auditflow-api; do
        if [ -d "$dir" ]; then
            run_step "deps: $dir (install)" -- bash -c "cd '$dir' && mvn -B install -Dmaven.test.skip=true"
        else
            echo "skip: $dir (not cloned, run 'just clone')"
        fi
    done
    for dir in \
        {{ROOT}}/labs64.io-auditflow/auditflow-be \
        {{ROOT}}/labs64.io-checkout/checkout-be \
        {{ROOT}}/labs64.io-payment-gateway; do
        if [ -d "$dir" ]; then
            run_step "deps: $dir" -- bash -c "cd '$dir' && mvn -B dependency:go-offline"
        else
            echo "skip: $dir (not cloned, run 'just clone')"
        fi
    done

# Run the full test suite across all modules
test:
    @cd {{ROOT}}/labs64.io-tests && just all

# Run the fast PR-gating smoke tests across all modules
smoke:
    @cd {{ROOT}}/labs64.io-tests && just smoke

# Run the full nightly-shape regression test suite
regression:
    @cd {{ROOT}}/labs64.io-tests && just regression

# Verify the cross-repo release wiring
check-release:
    @python3 {{ROOT}}/labs64.io-workspace/scripts/check-release-wiring.py --root {{ROOT}}
