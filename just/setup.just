# Group `setup` (docs/justfiles.md in labs64.io-workspace). Imported by the justfile.

# Sync the shared skills into the user-level skill folders of Claude Code and Codex CLI
[group('setup')]
sync-skills:
    ./scripts/sync-skills.sh

# Copy your personal skills into .agents/skills/ so they become shared skills
[group('setup')]
import-skills:
    ./scripts/import-personal-skills.sh

# Required tools fail the check when missing; optional ones are only reported, so a machine
# without a JDK or Terraform still passes (images are built in a container, see `build`).
#
# Check that the required local tools are installed at the versions pinned in tool-versions.env
[group('setup')]
doctor:
    #!/usr/bin/env bash
    set -euo pipefail
    # shellcheck source=tool-versions.env
    source tool-versions.env
    ok=0; missing=0; drift=0; skipped=0; optional=0
    # check <name> <cmd> <install hint> <expected version | ""> <version command...>
    check() {
        local name=$1 cmd=$2 hint=$3 want=$4
        if ! command -v "$cmd" >/dev/null 2>&1; then
            if [ "$optional" = 1 ]; then
                echo "➖ $name not installed (optional). Install: $hint"
                skipped=$((skipped + 1))
            else
                echo "❌ $name not found. Install: $hint"
                missing=$((missing + 1))
            fi
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
    check "curl"      curl      "https://curl.se/"                                ""                      curl --version
    optional=1
    echo "--- optional (build a module on the host, browse the cluster, regenerate chart docs) ---"
    check "Java"  java "Temurin ${JAVA_VERSION}, https://adoptium.net/" " ${JAVA_VERSION}."  java --version
    check "Maven" mvn  "3.6.3+, https://maven.apache.org/"              ""                    mvn --version
    check "Node"  node "${NODE_VERSION}+, https://nodejs.org/"          "v${NODE_VERSION}."   node --version
    check "k9s"   k9s  "https://k9scli.io/"                             "v${K9S_VERSION}"     k9s version -s
    check "helm-docs" helm-docs "https://github.com/norwoodj/helm-docs/releases (or rebuild the dev container)" "${HELM_DOCS_VERSION}" helm-docs --version
    echo "--- optional (operate the AWS environments) ---"
    check "Terraform" terraform "https://developer.hashicorp.com/terraform" "v${TERRAFORM_VERSION}" terraform --version
    check "AWS CLI"   aws       "https://aws.amazon.com/cli/"               ""                      aws --version
    optional=0
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
    echo "$ok OK, $missing missing, $skipped optional not installed, $drift differ from tool-versions.env"
    [ "$missing" -eq 0 ]
