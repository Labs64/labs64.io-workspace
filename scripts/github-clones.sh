#!/usr/bin/env bash
# Print every direct subfolder of <root> that is a clone of a GitHub repository
# (origin on github.com), one path per line. Used by the multi-repo just recipes.
set -euo pipefail
root="${1:?usage: github-clones.sh <root>}"
for dir in "$root"/*/; do
    dir="${dir%/}"
    [ -e "$dir/.git" ] || continue
    url=$(git -C "$dir" remote get-url origin 2>/dev/null || true)
    case "$url" in
        *github.com[/:]*) echo "$dir" ;;
    esac
done
