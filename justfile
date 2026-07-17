REPOS := "labs64.io-docs labs64.io-docs-internal labs64.io-devops labs64.io-tests labs64.io-helm-charts labs64.io-commons labs64.io-authproxy labs64.io-auditflow labs64.io-checkout labs64.io-customer-portal labs64.io-payment-gateway"
GITHUB_ORG := "git@github.com:Labs64"

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
	./scripts/build-images.sh {{module}}

# Start the entire local cluster
up: build
    cd labs64.io-helm-charts && just up
