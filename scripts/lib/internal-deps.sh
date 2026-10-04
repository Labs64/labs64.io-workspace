#!/usr/bin/env bash
# Internal (io.labs64) Maven artifacts for a from-source build.
#
# No pom in the ecosystem carries a real version: `${revision}` defaults to
# 0.0.0-SNAPSHOT and a release is the tagged commit built with -Drevision=<tag>.
# A from-source build therefore needs two kinds of internal artifact in the local
# Maven repository:
#
#   * the sibling checkouts at HEAD, installed as 0.0.0-SNAPSHOT   (install_commons_dev)
#   * every RELEASE a module pins — its labs64io-parent version and
#     auditflow-api.version                                        (ensure_pinned_releases)
#
# Released artifacts live in Labs64 Nexus, which needs credentials. Rather than require
# them, a pinned release is rebuilt from its own git tag (same sources, same version)
# and installed once; later runs find it in the local repository and skip the build.
#
# Usage: source this file after lib/progress.sh; ROOT must be the ecosystem root.

M2_REPO="${MAVEN_REPO_LOCAL:-${HOME}/.m2/repository}"
# Where the repositories' .git directories are. Differs from ROOT only for the Windows
# staging copy, which leaves .git behind (see stage-build-inputs.sh).
GIT_ROOT="${GIT_ROOT:-${ROOT}}"

install_commons_dev() {
    run_step "commons: parent + libraries (0.0.0-SNAPSHOT)" -- \
        bash -c "cd '${ROOT}/labs64.io-commons' && mvn -B -Dstyle.color=always -T 1C clean install -Dmaven.test.skip=true"
}

# _pinned_version <pom> <xpath-ish>
#   parent           -> version of the io.labs64:labs64io-parent <parent>
#   <property-name>  -> value of that <properties> entry
_pinned_version() {
    local pom=$1 what=$2
    [[ -f "$pom" ]] || return 0
    if [[ "$what" == "parent" ]]; then
        # The <version> that follows <artifactId>labs64io-parent</artifactId> inside <parent>.
        tr -d '\n' < "$pom" \
            | sed -n -E 's/.*<parent>[^!]*<artifactId>labs64io-parent<\/artifactId>[[:space:]]*<version>([^<]+)<\/version>.*/\1/p'
    else
        sed -n -E "s/.*<${what}>([^<]+)<\/${what}>.*/\1/p" "$pom" | head -1
    fi
}

# _build_release_from_tag <repo> <tag> <subdir> <label>
_build_release_from_tag() {
    local repo=$1 tag=$2 subdir=$3 label=$4
    local git_dir="${GIT_ROOT}/${repo}"
    if ! git -c safe.directory='*' -C "$git_dir" rev-parse -q --verify "refs/tags/${tag}^{commit}" >/dev/null 2>&1; then
        echo "ERROR: ${repo} has no tag '${tag}', but a module pins that release." >&2
        echo "       Run 'just pull' to fetch tags, or check the pinned version." >&2
        return 1
    fi
    local work
    work="$(mktemp -d)"
    # shellcheck disable=SC2064
    trap "rm -rf '$work'" RETURN
    git -c safe.directory='*' -C "$git_dir" archive "$tag" | tar -x -C "$work"
    run_step "${label} ${tag} (from tag)" -- \
        bash -c "cd '${work}/${subdir}' && mvn -B -Dstyle.color=always -Drevision='${tag}' -Dmaven.test.skip=true install"
}

# Installs every released internal artifact the cloned modules pin and the local
# repository does not have yet. -SNAPSHOT pins need nothing: the from-source build
# installs those from the sibling checkouts.
ensure_pinned_releases() {
    local pom version seen=" "

    for pom in \
        "${ROOT}/labs64.io-auditflow/auditflow-be/pom.xml" \
        "${ROOT}/labs64.io-checkout/checkout-be/pom.xml" \
        "${ROOT}/labs64.io-payment-gateway/payment-gateway-providers/pom.xml" \
        "${ROOT}/labs64.io-payment-gateway/payment-gateway-be/pom.xml"; do
        version="$(_pinned_version "$pom" parent)"
        [[ -n "$version" && "$version" != *-SNAPSHOT && "$seen" != *" commons:${version} "* ]] || continue
        seen+="commons:${version} "
        if [[ ! -f "${M2_REPO}/io/labs64/labs64io-parent/${version}/labs64io-parent-${version}.pom" ]]; then
            _build_release_from_tag labs64.io-commons "$version" "" "commons" || return 1
        fi
    done

    pom="${ROOT}/labs64.io-payment-gateway/payment-gateway-be/pom.xml"
    version="$(_pinned_version "$pom" auditflow-api.version)"
    if [[ -n "$version" && "$version" != *-SNAPSHOT \
          && ! -f "${M2_REPO}/io/labs64/auditflow-api/${version}/auditflow-api-${version}.pom" ]]; then
        _build_release_from_tag labs64.io-auditflow "$version" "auditflow-api" "auditflow-api" || return 1
    fi
}
