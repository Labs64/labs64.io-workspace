# Group `tests` (docs/justfiles.md in labs64.io-workspace). Imported by the justfile.

# Run a test recipe against the selected or deployed identity provider
[private]
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
    IDENTITY_PROVIDER="${provider}" just tests "{{recipe}}"

# Run the normal regression, then the isolated PSP-stub scenarios
[group('tests')]
test:
    @just _test-with-identity test

# Run the fast PR-gating smoke tests across all modules
[group('tests')]
smoke:
    @just _test-with-identity smoke

# Run the nightly regression suite without changing provider endpoints
[group('tests')]
regression:
    @just _test-with-identity regression
