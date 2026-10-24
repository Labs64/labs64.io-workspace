# Group `local stack` (docs/justfiles.md in labs64.io-workspace). Imported by the justfile.

# Build the module images (all by default) and push them to the local registry at localhost:5005
[group('local stack')]
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
[group('local stack')]
up:
    just helm-charts generate-secrets
    just helm-charts start-cluster
    just build
    just helm-charts deploy

# The monitoring stack (Prometheus, Grafana, Loki, Tempo, the OpenTelemetry collector) and module telemetry, on top of
# the local stack. It deploys the images `just up` built.
#
# Deploy the local stack with monitoring and OpenTelemetry, then open Grafana
[group('local stack')]
up-otel:
    just helm-charts up-otel
    just helm-charts open-grafana

# Show the pods, services and routes of the local stack
[group('local stack')]
status:
    @just helm-charts status

# Follow the logs of one app, or show the warnings and errors of all of them
[group('local stack')]
logs app="":
    @just helm-charts logs {{app}}

# Delete the local cluster and its registry
[group('local stack')]
down:
    just helm-charts down
