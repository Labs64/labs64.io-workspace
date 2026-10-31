# Group `quality gates` (docs/justfiles.md in labs64.io-workspace). Imported by the justfile.

# What the workspace's CI (.github/workflows/labs64io-ci.yml) runs, in the same order: the gate scripts' own tests,
# actionlint over the workflows, the Renovate preset, then the cross-repository gates over the clones next to this
# one (strict: a repository that is not cloned fails). Needs python3 with pytest and pyyaml, curl (actionlint) and
# npx (Renovate's validator), and network access for those two.
#
# Run what the workspace's CI runs
[group('quality gates')]
ci: test-scripts lint-workflows check-renovate-preset check-release-wiring check-renovate-wiring (check-pins "--strict") check-just

# Run every cross-repository consistency gate over the clones next to this workspace
[group('quality gates')]
check: check-release-wiring check-pins check-renovate-wiring check-just

# A gate nobody tests reports "clean" forever: the tests of scripts/ (the gates, the skill sync, the build helpers).
#
# Run the tests of this repository's scripts
[group('quality gates')]
test-scripts:
    python3 -m pytest scripts/tests -q -p no:cacheprovider

# actionlint, with shellcheck over every `run:` block where shellcheck is installed, at the ACTIONLINT_VERSION of
# tool-versions.env: a matching actionlint on the PATH, else that release downloaded into a temporary folder.
# Intentional findings are not suppressed: quote the line, or add a `# shellcheck disable`.
#
# Lint every workflow and composite action of this repository with actionlint
[group('quality gates')]
lint-workflows:
    #!/usr/bin/env bash
    set -euo pipefail
    source tool-versions.env
    if command -v actionlint >/dev/null 2>&1 && [ "$(actionlint -version | head -n 1)" = "$ACTIONLINT_VERSION" ]; then
        exec actionlint -color
    fi
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
    case "$(uname -m)" in x86_64|amd64) arch=amd64 ;; aarch64|arm64) arch=arm64 ;; *) arch=$(uname -m) ;; esac
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    curl -fsSL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_${os}_${arch}.tar.gz" \
        | tar -xz -C "$tmp" actionlint
    "$tmp/actionlint" -color

# The shared Renovate preset every repository extends, and this repository's renovate.json, through Renovate's own
# validator. Renovate 44 runs on Node 24 (its supported range lags the newest release).
#
# Validate the Renovate preset with Renovate's config validator
[group('quality gates')]
check-renovate-preset:
    npx --yes --package renovate@44 -- renovate-config-validator default.json renovate.json

# Verify the cross-repo release wiring: every released image reaches its chart
[group('quality gates')]
check-release-wiring:
    @python3 scripts/check-release-wiring.py --root {{ROOT}}

# Verify that every version pin shared by more than one file or repository agrees (tool
# versions, platform charts and engine lines, Cerbos, OTel), that no pom
# hard-codes a version or the Spring Boot parent, and release order: services must pin
# released commons / auditflow-api versions (no -SNAPSHOT, tag exists upstream).
# `--strict` (CI): a repository that is not cloned fails instead of being skipped.
#
# Check that version pins agree across files and repositories and no pom hard-codes a version
[group('quality gates')]
check-pins *args:
    @python3 scripts/check-version-pins.py --root {{ROOT}} {{args}}

# Verify that every event which makes a Renovate pull request due starts the (self-hosted) runner:
# a dashboard-tick caller in every repository with a renovate.json, the trigger in the Maven publish and
# the chart release, and the inputs the runner must accept.
#
# Check that every event that makes a Renovate pull request due starts the runner
[group('quality gates')]
check-renovate-wiring:
    @python3 scripts/check-renovate-wiring.py --root {{ROOT}}

# The justfile convention (docs/justfiles.md) over every repository cloned next to this one that has a justfile:
# groups and descriptions, the reserved recipes, environment parameters without a default, and every `just <recipe>`
# named by a workflow, a script or the documentation exists. Needs `just` itself.
#
# Check every justfile against the convention and every reference to a recipe
[group('quality gates')]
check-just *args:
    @python3 scripts/check-just.py --root {{ROOT}} {{args}}

# Check that all Java modules resolve their dependencies offline
[group('quality gates')]
check-deps verbose="1":
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
        {{ROOT}}/labs64.io-payment-gateway \
        {{ROOT}}/labs64.io-reporting; do
        if [ -d "$dir" ]; then
            run_step "deps: $dir" -- bash -c "cd '$dir' && mvn -B dependency:go-offline"
        else
            echo "skip: $dir (not cloned, run 'just clone')"
        fi
    done
