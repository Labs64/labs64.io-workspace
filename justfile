# Internal commands from the optional EE workspace
mod? ee '../labs64.io-workspace-ee/justfile'

REPOS := "labs64.io-docs labs64.io-tests labs64.io-helm-charts labs64.io-commons labs64.io-authproxy labs64.io-auditflow labs64.io-checkout labs64.io-customer-portal labs64.io-payment-gateway labs64.io"
GITHUB_ORG := "https://github.com/Labs64"
# Ecosystem root: repositories are cloned as siblings of this workspace, not inside it.
ROOT := ".."

# List available commands
default:
    @just --list

# One-time migration: the website repo used to be cloned as labs64.io-website. Rename an existing
# checkout so it matches a fresh one (plain `mv`: branches, stashes and uncommitted work are kept).
# Safe to remove once everyone has run any recipe below after pulling this change.
#
# Rename an old labs64.io-website checkout to labs64.io
_migrate-website-folder:
    #!/bin/bash
    set -euo pipefail
    old="{{ROOT}}/labs64.io-website"
    new="{{ROOT}}/labs64.io"
    [ -d "$old/.git" ] || exit 0
    if [ -e "$new" ]; then
        echo "WARNING: both $old and $new exist, leaving both untouched."
        echo "         Keep $new; delete $old once it holds no unpushed work."
        exit 0
    fi
    url=$(git -C "$old" remote get-url origin 2>/dev/null | tr 'A-Z' 'a-z' || true)
    url="${url%/}"; url="${url%.git}"
    case "$url" in
        *[/:]labs64/labs64.io) ;;
        *) echo "WARNING: $old is not a Labs64/labs64.io clone (origin: ${url:-none}), leaving it alone."; exit 0 ;;
    esac
    echo "Renaming $old -> $new (the website repo is now cloned as labs64.io)..."
    mv "$old" "$new"

# Clone all ecosystem repositories (as siblings of this workspace)
clone: _migrate-website-folder
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ ! -d "{{ROOT}}/$repo" ]; then
            echo "Cloning $repo..."
            git clone "{{GITHUB_ORG}}/$repo.git" "{{ROOT}}/$repo"
        else
            echo "$repo already exists, skipping."
        fi
    done

# Pull the current branch (rebase, autostash) in every GitHub clone next to this workspace
pull: _migrate-website-folder
    #!/bin/bash
    failed=()
    while read -r dir; do
        name=$(basename "$dir")
        if ! git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
            echo "Skipping $name (current branch has no upstream)."
            continue
        fi
        echo "Pulling $name..."
        git -C "$dir" pull --rebase --autostash || failed+=("$name")
    done < <(bash scripts/github-clones.sh "{{ROOT}}")
    if [ ${#failed[@]} -gt 0 ]; then
        echo >&2
        echo "Pull failed in: ${failed[*]}" >&2
        exit 1
    fi

# Show git status across every GitHub clone next to this workspace
status: _migrate-website-folder
    #!/bin/bash
    while read -r dir; do
        echo "=== $(basename "$dir") ==="
        git -C "$dir" status -s
    done < <(bash scripts/github-clones.sh "{{ROOT}}")

# Show open pull requests across all GitHub clones next to this workspace (incl. private EE repos)
pr: _migrate-website-folder
    #!/bin/bash
    if ! command -v gh >/dev/null 2>&1; then
        echo "gh CLI not found" >&2
        exit 1
    fi
    list_prs() {
        local rows
        rows=$(gh pr list --state open --json number,title,headRefName,createdAt,url \
            --template '{{ "{{" }}range .{{ "}}" }}#{{ "{{" }}.number{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.title{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.headRefName{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.createdAt | timefmt "2006-01-02 15:04"{{ "}}" }}{{ "{{" }}"\t"{{ "}}" }}{{ "{{" }}.url{{ "}}" }}{{ "{{" }}"\n"{{ "}}" }}{{ "{{" }}end{{ "}}" }}')
        if [ -n "$rows" ]; then
            printf 'ID\tTITLE\tBRANCH\tCREATED AT\tLINK\n%s\n' "$rows" | column -t -s $'\t'
        fi
    }
    first=1
    while read -r dir; do
        [ "$first" = 1 ] || echo
        first=0
        echo "=== $(basename "$dir") ==="
        (cd "$dir" && list_prs)
    done < <(bash scripts/github-clones.sh "{{ROOT}}")

# Sync the shared skills into the user-level skill folders of Claude Code and Codex CLI
sync-skills:
    ./scripts/sync-skills.sh

# Copy your personal skills into .agents/skills/ so they become shared skills
import-skills:
    ./scripts/import-personal-skills.sh

# Build the module images (all by default) and push them to the local registry at localhost:5005
build module="all" verbose="1":
    #!/usr/bin/env bash
    set -euo pipefail
    builder_uid="$(id -u)"
    builder_gid="$(id -g)"
    maven_cache=/home/builder/.m2
    echo "=== Building dev container ==="
    docker build \
        --build-arg "USER_ID=${builder_uid}" \
        --build-arg "GROUP_ID=${builder_gid}" \
        -t labs64io-builder \
        -f scripts/Dockerfile.builder \
        scripts/

    # Get the GID of the docker socket inside the container (solves macOS root:root mapping)
    docker_gid="$(docker run --rm -v /var/run/docker.sock:/var/run/docker.sock labs64io-builder stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 0)"

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
    # The modules live next to this workspace. Windows needs a native-Linux staging
    # copy because Maven cannot change POSIX modes on Docker Desktop's 9p/DrvFS
    # mount (MSHARED-1153). Keep the original direct mount on macOS and Linux.
    ws="${LOCAL_WORKSPACE_FOLDER:-$(pwd)}"
    # LOCAL_WORKSPACE_FOLDER is a host path. Docker Desktop passes a Windows
    # path into Linux dev containers, so dirname/basename cannot split it.
    windows_host=false
    case "$ws" in
        [A-Za-z]:\\*|\\\\*)
            windows_host=true
            workspace_name="${ws##*\\}"
            ecosystem_root="${ws%\\*}"
            ;;
        [A-Za-z]:/*)
            windows_host=true
            workspace_name="$(basename "$ws")"
            ecosystem_root="$(dirname "$ws")"
            ;;
        *)
            workspace_name="$(basename "$ws")"
            ecosystem_root="$(dirname "$ws")"
            ;;
    esac
    if [[ "$windows_host" == true ]]; then
        mount_args=(--mount "type=bind,source=${ecosystem_root},target=/source,readonly")
        workdir=/workspaces
        builder_command=(
            bash "/source/${workspace_name}/scripts/stage-build-inputs.sh"
            "${workspace_name}"
            "${MODULE:-all}"
    )
    else
        mount_args=(--mount "type=bind,source=${ecosystem_root},target=/workspaces")
        workdir="/workspaces/${workspace_name}"
        builder_command=(./scripts/build-images.sh "${MODULE:-all}")
    fi
    if [[ -t 1 ]]; then tty_args=(-it); else tty_args=(); fi
    docker run "${tty_args[@]}" --rm --network host --name "labs64io-builder-${MODULE:-all}-$$" \
        --user "${builder_uid}:${builder_gid}" \
        --group-add "${docker_gid}" \
        -e VERBOSE="{{verbose}}" \
        -e HOME=/home/builder \
        -e MAVEN_CONFIG="${maven_cache}" \
        "${mount_args[@]}" \
        -v "labs64-m2-cache:${maven_cache}" \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -w "${workdir}" \
        labs64io-builder \
        "${builder_command[@]}"

# Build the first-party images and deploy the local stack from the Helm overrides
up:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ROOT}}/labs64.io-helm-charts"
    just generate-secrets
    just cluster-up
    cd "{{justfile_directory()}}"
    just build
    cd "{{ROOT}}/labs64.io-helm-charts"
    just deploy

# Start the local cluster with the monitoring stack and OpenTelemetry, then open Grafana
otel:
    @cd {{ROOT}}/labs64.io-helm-charts && just up-otel && just grafana

# Delete the local cluster and its registry
down:
    @cd {{ROOT}}/labs64.io-helm-charts && just cluster-down

# Show errors from all module logs, or follow the logs of a single app
logs app="":
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{ROOT}}/labs64.io-helm-charts
    if [ -n "{{app}}" ]; then
        just logs {{app}}
    else
        just logs-errors
    fi

# Check that the required local tools are installed at the versions pinned in tool-versions.env
doctor:
    #!/usr/bin/env bash
    set -euo pipefail
    # shellcheck source=tool-versions.env
    source tool-versions.env
    ok=0; missing=0; drift=0
    # check <name> <cmd> <install hint> <expected version | ""> <version command...>
    check() {
        local name=$1 cmd=$2 hint=$3 want=$4
        if ! command -v "$cmd" >/dev/null 2>&1; then
            echo "❌ $name not found. Install: $hint"
            missing=$((missing + 1))
            return
        fi
        # Capture everything, then keep the first line: `| head -1` closes the pipe early, and a
        # tool that keeps writing (k9s) then dies of SIGPIPE, failing the recipe under pipefail.
        local have
        have="$("${@:5}" 2>&1 || true)"
        have="${have%%$'\n'*}"
        if [ -n "$want" ] && [[ "$have" != *"$want"* ]]; then
            echo "⚠️  $name: $have — tool-versions.env pins $want"
            drift=$((drift + 1))
        else
            echo "✅ $name: $have"
        fi
        ok=$((ok + 1))
    }
    check "Docker"    docker    "https://www.docker.com/products/docker-desktop/" ""                     docker --version
    check "k3d"       k3d       "https://k3d.io/"                                 "v${K3D_VERSION}"       k3d --version
    check "Helm"      helm      "https://helm.sh/"                                "v${HELM_VERSION}"      helm version --short
    check "Helmfile"  helmfile  "https://helmfile.io/"                            "${HELMFILE_VERSION}"   helmfile --version
    check "kubectl"   kubectl   "https://kubernetes.io/docs/tasks/tools/"         ""                      kubectl version --client
    check "just"      just      "https://github.com/casey/just"                   "${JUST_VERSION}"       just --version
    check "Terraform" terraform "https://developer.hashicorp.com/terraform"       "v${TERRAFORM_VERSION}" terraform --version
    check "AWS CLI"   aws       "https://aws.amazon.com/cli/"                     ""                      aws --version
    check "curl"      curl      "https://curl.se/"                                ""                      curl --version
    echo "--- optional (only needed to build images locally) ---"
    check "Java"  java "Temurin ${JAVA_VERSION}, https://adoptium.net/" " ${JAVA_VERSION}."  java --version
    check "Maven" mvn  "3.6.3+, https://maven.apache.org/"              ""                    mvn --version
    check "Node"  node "${NODE_VERSION}+, https://nodejs.org/"          "v${NODE_VERSION}."   node --version
    check "k9s"   k9s  "https://k9scli.io/"                             "v${K9S_VERSION}"     k9s version -s
    check "helm-docs" helm-docs "https://github.com/norwoodj/helm-docs/releases (or rebuild the dev container)" "${HELM_DOCS_VERSION}" helm-docs --version
    echo "---"
    if command -v helm >/dev/null 2>&1; then
        for plugin in "diff:${HELM_DIFF_VERSION}:https://github.com/databus23/helm-diff --version v${HELM_DIFF_VERSION}" \
                      "schema:${HELM_SCHEMA_VERSION}:https://github.com/dadav/helm-schema --version ${HELM_SCHEMA_VERSION}"; do
            name="${plugin%%:*}"; rest="${plugin#*:}"; want="${rest%%:*}"; source_url="${rest#*:}"
            have="$(helm plugin list 2>/dev/null | awk -v n="$name" '$1 == n {print $2}')"
            if [ -z "$have" ]; then
                echo "❌ helm-$name plugin missing. Install: helm plugin install $source_url --verify=false"
                missing=$((missing + 1))
            elif [ "$have" != "$want" ]; then
                echo "⚠️  helm-$name plugin: $have — tool-versions.env pins $want"
                drift=$((drift + 1))
            else
                echo "✅ helm-$name plugin: $have"
            fi
        done
    fi
    echo "---"
    echo "$ok OK, $missing missing, $drift differ from tool-versions.env"
    [ "$missing" -eq 0 ]

# Check that all Java modules resolve their dependencies offline
verify-deps verbose="1":
    #!/usr/bin/env bash
    set -euo pipefail
    export VERBOSE="{{verbose}}"
    ROOT="{{ROOT}}"
    source scripts/lib/progress.sh
    source scripts/lib/internal-deps.sh
    # Internal artifacts are consumed through the local Maven repo, so they must be installed
    # (like a real build does), not just dependency:go-offline'd, before the modules below can
    # resolve against them: commons at HEAD (0.0.0-SNAPSHOT), every released version a module
    # pins (rebuilt from its tag), then auditflow-api, which payment-gateway consumes.
    if [ -d "{{ROOT}}/labs64.io-commons" ]; then
        install_commons_dev
    else
        echo "skip: labs64.io-commons (not cloned, run 'just clone')"
    fi
    ensure_pinned_releases
    if [ -d "{{ROOT}}/labs64.io-auditflow/auditflow-api" ]; then
        run_step "deps: auditflow-api (install)" -- bash -c "cd '{{ROOT}}/labs64.io-auditflow/auditflow-api' && mvn -B install -Dmaven.test.skip=true"
    else
        echo "skip: labs64.io-auditflow (not cloned, run 'just clone')"
    fi
    for dir in \
        {{ROOT}}/labs64.io-auditflow \
        {{ROOT}}/labs64.io-checkout/checkout-be \
        {{ROOT}}/labs64.io-payment-gateway; do
        if [ -d "$dir" ]; then
            run_step "deps: $dir" -- bash -c "cd '$dir' && mvn -B dependency:go-offline"
        else
            echo "skip: $dir (not cloned, run 'just clone')"
        fi
    done

# Run a test recipe against the selected or deployed identity provider
_test-with-identity recipe:
    #!/usr/bin/env bash
    set -euo pipefail

    provider="${IDENTITY_PROVIDER:-}"
    if [ -z "${provider}" ]; then
        keycloak_installed=false
        mock_installed=false

        if helm status keycloak --namespace tools >/dev/null 2>&1; then
            keycloak_installed=true
        fi
        if helm status mock-oidc --namespace tools >/dev/null 2>&1; then
            mock_installed=true
        fi

        if [ "${keycloak_installed}" = true ] && [ "${mock_installed}" = false ]; then
            provider=keycloak
        elif [ "${mock_installed}" = true ] && [ "${keycloak_installed}" = false ]; then
            provider=mock
        elif [ "${keycloak_installed}" = true ]; then
            echo "Cannot auto-detect identity provider: both keycloak and mock-oidc are installed." >&2
            echo "Set IDENTITY_PROVIDER explicitly or reconcile the Helmfile overrides with just up." >&2
            exit 1
        else
            echo "Cannot auto-detect identity provider: neither keycloak nor mock-oidc is installed." >&2
            echo "Run just up or set IDENTITY_PROVIDER explicitly for an external environment." >&2
            exit 1
        fi
    fi

    case "${provider}" in
        mock|keycloak) ;;
        *)
            echo "Unsupported IDENTITY_PROVIDER: ${provider}. Expected mock or keycloak." >&2
            exit 1
            ;;
    esac

    echo "Using identity provider: ${provider}"
    cd "{{ROOT}}/labs64.io-tests"
    IDENTITY_PROVIDER="${provider}" just "{{recipe}}"

# Run the normal regression, then the isolated PSP-stub scenarios
test:
    @just _test-with-identity test-all

# Run the fast PR-gating smoke tests across all modules
smoke:
    @just _test-with-identity smoke

# Run the nightly regression suite without changing provider endpoints
regression:
    @just _test-with-identity regression

# Verify the cross-repo release wiring: every released image reaches its chart
check-release-wiring:
    @python3 scripts/check-release-wiring.py --root {{ROOT}}

alias check-release := check-release-wiring

# Verify that every version pin shared by more than one file or repository agrees (tool
# versions, platform charts and engine lines, Cerbos, OTel), that no pom
# hard-codes a version or the Spring Boot parent, and release order: services must pin
# released commons / auditflow-api versions (no -SNAPSHOT, tag exists upstream)
#
# Check that version pins agree across files and repositories and no pom hard-codes a version
check-pins:
    @python3 scripts/check-version-pins.py --root {{ROOT}}

# Run every cross-repo consistency gate
check: check-release-wiring check-pins

# Verify the release and maintenance tooling itself, offline (no cluster, no registry writes):
# the gate scripts' own tests (here and in labs64.io-helm-charts), then every cross-repo gate.
# Needs `pytest` and `pyyaml`; CI runs the same steps (.github/workflows/labs64io-ci.yml).
#
# Run the gate scripts' own tests offline, then every cross-repo gate
verify-process:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 -m pytest scripts/tests -q -p no:cacheprovider
    if [ -d "{{ROOT}}/labs64.io-helm-charts/scripts" ]; then
        (cd "{{ROOT}}/labs64.io-helm-charts" && python3 -m pytest scripts -q -p no:cacheprovider)
    else
        echo "skip: labs64.io-helm-charts not cloned (run 'just clone')"
    fi
    just check
