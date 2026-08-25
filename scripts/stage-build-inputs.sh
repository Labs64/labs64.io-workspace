#!/usr/bin/env bash
set -euo pipefail

readonly SOURCE_ROOT="${SOURCE_ROOT:-/source}"
readonly DEST_ROOT="${DEST_ROOT:-/workspaces}"
readonly WORKSPACE_NAME="${1:?Usage: stage-build-inputs.sh WORKSPACE_NAME BUILD_TARGET}"
readonly BUILD_TARGET="${2:-all}"
readonly BUILD_SCRIPT="${SOURCE_ROOT}/${WORKSPACE_NAME}/scripts/build-images.sh"

if [[ ! -f "$BUILD_SCRIPT" ]]; then
    echo "Build script not found: $BUILD_SCRIPT" >&2
    exit 1
fi
if [[ ! -d "$DEST_ROOT" || ! -w "$DEST_ROOT" ]]; then
    echo "Build staging directory is not writable: $DEST_ROOT" >&2
    exit 1
fi

repo_output="$(bash "$BUILD_SCRIPT" --required-repos "$BUILD_TARGET")"
mapfile -t module_repos <<<"$repo_output"
repos=("$WORKSPACE_NAME" "${module_repos[@]}")

echo "=== Staging Windows build inputs on Linux: ${repos[*]} ==="
for repo in "${repos[@]}"; do
    if [[ ! -d "${SOURCE_ROOT}/${repo}" ]]; then
        echo "Required build repository not found: ${SOURCE_ROOT}/${repo}" >&2
        exit 1
    fi

    # Build outputs are recreated below. Excluding them keeps the copy small and,
    # crucially, prevents root-owned 9p artifacts from entering the Linux stage.
    tar -C "$SOURCE_ROOT" \
        --exclude="${repo}/.git" \
        --exclude="${repo}/*/target" \
        --exclude="${repo}/*/*/target" \
        --exclude="${repo}/*/node_modules" \
        --exclude="${repo}/*/.venv" \
        --exclude="${repo}/*/__pycache__" \
        -cf - -- "$repo" \
        | tar -C "$DEST_ROOT" --no-same-owner -xf -
done

cd "${DEST_ROOT}/${WORKSPACE_NAME}"
exec ./scripts/build-images.sh "$BUILD_TARGET"
