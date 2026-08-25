#!/usr/bin/env bash
set -euo pipefail

required_repos() {
    case "$1" in
        all)
            printf '%s\n' \
                labs64.io-commons \
                labs64.io-authproxy \
                labs64.io-auditflow \
                labs64.io-checkout \
                labs64.io-customer-portal \
                labs64.io-payment-gateway
            ;;
        commons) printf '%s\n' labs64.io-commons ;;
        traefik-authproxy|gateway) printf '%s\n' labs64.io-authproxy ;;
        auditflow) printf '%s\n' labs64.io-auditflow ;;
        checkout) printf '%s\n' labs64.io-checkout ;;
        customer-portal|customer-portal-ui) printf '%s\n' labs64.io-customer-portal ;;
        payment-gateway) printf '%s\n' labs64.io-payment-gateway ;;
        *)
            echo "Unknown target: $1" >&2
            echo "Valid targets: all, commons, auditflow, checkout, payment-gateway, traefik-authproxy, customer-portal" >&2
            return 2
            ;;
    esac
}

if [[ "${1:-}" == "--required-repos" ]]; then
    required_repos "${2:-all}"
    exit
fi

# shellcheck source=lib/progress.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/progress.sh"

TARGET=${1:-all}
REGISTRY="host.docker.internal:5005"

# Module repositories are cloned as siblings of the workspace, so every module
# path is resolved against the ecosystem root one level up.
ROOT=${ROOT:-".."}

BUILD_ACTION="--push"
if [[ "$TARGET" != "commons" ]] && ! curl -s --connect-timeout 2 "http://${REGISTRY}/v2/" > /dev/null; then
    echo "INFO: Local registry at ${REGISTRY} is not reachable."
    echo "Images will be loaded into the local Docker daemon instead of being pushed."
    BUILD_ACTION="--load"
fi

build_image() {
    local tag=$1
    shift
    # Filter legacy builder warnings safely without losing exit code
    docker build -t "$tag" "$@" 2>&1 | awk '
      /DEPRECATED: The legacy builder/ { skip=3; next }
      skip > 0 { skip--; next }
      { print }
    '
    # Capture docker build exit code safely (pipestatus works in bash)
    local status=${PIPESTATUS[0]}
    if [ $status -ne 0 ]; then
        return $status
    fi
    if [[ "$BUILD_ACTION" == "--push" ]]; then
        docker push "$tag"
    fi
}
export -f build_image
export BUILD_ACTION REGISTRY

# mvn_step "label" "module_dir" [mvn-goal-args...]
mvn_step() {
    local label=$1 dir=$2; shift 2
    run_step "$label" -- bash -c "cd '$dir' && mvn -B -Dstyle.color=always -T 1C $*"
}

# image_step "label" "module_dir" "image_name"
image_step() {
    local label=$1 dir=$2 image=$3
    run_step "$label" -- bash -c "cd '$dir' && build_image localhost:5005/${image}:latest ."
}

build_commons() {
    mvn_step "commons: auth-context-java" "${ROOT}/labs64.io-commons/auth-context-java" clean install -Dmaven.test.skip=true
    mvn_step "commons: openapi-spring-boot-starter" "${ROOT}/labs64.io-commons/openapi-spring-boot-starter" clean install -Dmaven.test.skip=true
    mvn_step "commons: authz-queryplan-jpa" "${ROOT}/labs64.io-commons/authz-queryplan-jpa" clean install -Dmaven.test.skip=true
}

build_traefik_authproxy() {
    image_step "traefik-authproxy: image" "${ROOT}/labs64.io-authproxy/traefik-authproxy" traefik-authproxy
}

build_auditflow() {
    mvn_step "auditflow: api + backend build" "${ROOT}/labs64.io-auditflow" clean install -Dmaven.test.skip=true
    image_step "auditflow: backend image" "${ROOT}/labs64.io-auditflow/auditflow-be" auditflow
    image_step "auditflow: transformer image" "${ROOT}/labs64.io-auditflow/auditflow-transformer" auditflow-transformer
    image_step "auditflow: sink image" "${ROOT}/labs64.io-auditflow/auditflow-sink" auditflow-sink
}

build_checkout() {
    mvn_step "checkout: backend build" "${ROOT}/labs64.io-checkout/checkout-be" clean package -Dmaven.test.skip=true
    image_step "checkout: backend image" "${ROOT}/labs64.io-checkout/checkout-be" checkout
    image_step "checkout: frontend image" "${ROOT}/labs64.io-checkout/checkout-fe" checkout-ui
}

build_payment_gateway() {
    mvn_step "payment-gateway: api + backend + providers" "${ROOT}/labs64.io-payment-gateway" clean install -Dmaven.test.skip=true
    image_step "payment-gateway: backend image" "${ROOT}/labs64.io-payment-gateway/payment-gateway-be" payment-gateway
}

build_customer_portal() {
    image_step "customer-portal: frontend image" "${ROOT}/labs64.io-customer-portal/customer-portal-fe" customer-portal-ui
}

case "$TARGET" in
    all)
        build_commons
        build_traefik_authproxy
        build_auditflow
        build_checkout
        build_customer_portal
        build_payment_gateway
        ;;
    commons)
        build_commons
        ;;
    traefik-authproxy|gateway)
        build_traefik_authproxy
        ;;
    auditflow)
        build_auditflow
        ;;
    checkout)
        build_checkout
        ;;
    customer-portal|customer-portal-ui)
        build_customer_portal
        ;;
    payment-gateway)
        build_payment_gateway
        ;;
    *)
        echo "Unknown target: $TARGET"
        echo "Valid targets: all, commons, auditflow, checkout, payment-gateway, traefik-authproxy, customer-portal"
        exit 1
        ;;
esac

if [[ "$BUILD_ACTION" == "--push" ]]; then
    echo "=== All requested images built and pushed ==="
    curl -s http://${REGISTRY}/v2/_catalog || true
else
    echo "=== All requested images built and loaded locally ==="
fi
