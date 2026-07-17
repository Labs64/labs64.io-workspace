#!/usr/bin/env bash
set -euo pipefail

TARGET=${1:-all}
REGISTRY="localhost:5005"

BUILD_ACTION="--push"
if [[ "$TARGET" != "commons" ]] && ! curl -s "http://${REGISTRY}/v2/" > /dev/null; then
    echo "INFO: Local registry at ${REGISTRY} is not reachable."
    echo "Images will be loaded into the local Docker daemon instead of being pushed."
    BUILD_ACTION="--load"
fi

build_image() {
    local tag=$1
    shift
    docker build -t "$tag" "$@"
    if [[ "$BUILD_ACTION" == "--push" ]]; then
        docker push "$tag"
    fi
}


build_commons() {
    echo "=== Building commons library ==="
    (
        echo "= Build Java auth-context starter ="
        cd ./labs64.io-commons/auth-context-java
        mvn -B -T 1C clean install -DskipTests -q
    )
    (
        echo "= Build Java openapi spring boot starter ="
        cd ./labs64.io-commons/openapi-spring-boot-starter
        mvn -B -T 1C clean install -DskipTests -q
    )
}

build_traefik_authproxy() {
    echo "=== Building traefik-authproxy image ==="
    (
        echo "= Build Auth Proxy ="
        cd ./labs64.io-authproxy/traefik-authproxy
        build_image ${REGISTRY}/traefik-authproxy:latest .
    )
}

build_auditflow() {
    echo "=== Building auditflow images ==="
    (
        echo "= Build API ="
        cd ./labs64.io-auditflow/auditflow-api
        mvn -B -T 1C clean install -DskipTests -q
    )
    (
        echo "= Build Backend ="
        cd ./labs64.io-auditflow/auditflow-be
        mvn -B -T 1C clean package -DskipTests -q
        build_image ${REGISTRY}/auditflow:latest .
    )
    (
        echo "= Build Transformer ="
        cd ./labs64.io-auditflow/auditflow-transformer
        build_image ${REGISTRY}/auditflow-transformer:latest .
    )
    (
        echo "= Build Sink ="
        cd ./labs64.io-auditflow/auditflow-sink
        build_image ${REGISTRY}/auditflow-sink:latest .
    )
}

build_checkout() {
    echo "=== Building checkout images ==="
    (
        echo "= Build Backend ="
        cd ./labs64.io-checkout/checkout-be
        mvn -B -T 1C clean package -DskipTests -q
        build_image ${REGISTRY}/checkout:latest .
    )
    (
        echo "= Build Frontend ="
        cd ./labs64.io-checkout/checkout-fe
        build_image ${REGISTRY}/checkout-ui:latest .
    )
}

build_payment_gateway() {
    echo "=== Building payment-gateway image ==="
    (
        echo "= Build Payment Gateway and Providers ="
        cd ./labs64.io-payment-gateway
        mvn -B -T 1C clean install -DskipTests -q
    )
    (
        echo "= Build Backend Image ="
        cd ./labs64.io-payment-gateway/payment-gateway-be
        build_image ${REGISTRY}/payment-gateway:latest .
    )
}

build_customer_portal() {
    echo "=== Building customer-portal-ui image ==="
    (
        echo "= Build Frontend ="
        cd ./labs64.io-customer-portal/customer-portal-fe
        build_image ${REGISTRY}/customer-portal-ui:latest .
    )
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
