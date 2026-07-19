REPOS := "labs64.io-docs labs64.io-docs-internal labs64.io-devops labs64.io-tests labs64.io-helm-charts labs64.io-commons labs64.io-authproxy labs64.io-auditflow labs64.io-checkout labs64.io-customer-portal labs64.io-payment-gateway labs64.io-website"
GITHUB_ORG := "git@github.com:Labs64"

# List available commands
default:
    @just --list

# Clone all ecosystem repositories
clone-all:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ ! -d "$repo" ]; then
            echo "Cloning $repo..."
            git clone "{{GITHUB_ORG}}/$repo.git"
        else
            echo "$repo already exists, skipping."
        fi
    done

# Pull latest master/main on all repositories
pull-all:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ -d "$repo" ]; then
            echo "Pulling $repo..."
            git -C "$repo" pull
        fi
    done

# Show git status across all repositories
status-all:
    #!/bin/bash
    for repo in {{REPOS}}; do
        if [ -d "$repo" ]; then
            echo "=== $repo ==="
            git -C "$repo" status -s
        fi
    done

# Build and push all module images to local registry (localhost:5005)
build module="all":
    @echo "=== Building dev container ==="
    @docker build -t labs64io-builder -f scripts/Dockerfile.builder scripts/
    @echo "=== Running build in dev container ==="
    @export MODULE='{{module}}'; \
    docker run --rm --network host --name "labs64io-builder-${MODULE:-all}-$$" \
        -v $(pwd):/workspace \
        -v labs64-m2-cache:/root/.m2 \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -w /workspace \
        labs64io-builder \
        ./scripts/build-images.sh "${MODULE:-all}"

# Start the entire local cluster
up:
    @cd labs64.io-helm-charts && just cluster-up
    @just build
    @cd labs64.io-helm-charts && just up
