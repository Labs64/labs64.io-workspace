<p align="center"><img src="https://raw.githubusercontent.com/Labs64/.github/refs/heads/master/assets/labs64-io-ecosystem.png"></p>

# Labs64.IO :: Workspace

> **START HERE:** This repository is the **primary entry point for all developers** working on the Labs64.IO ecosystem. It is the **master workspace** that orchestrates 9+ independent Git repositories with a unified `justfile` and DevContainer, instead of you having to manage each one by hand.

## 📋 Prerequisites

Install these tools before cloning (or skip straight to the DevContainer, which bundles all of them):

| Tool | Version | Purpose |
|------|---------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | latest | Container runtime (`brew install --cask docker`) |
| [k3d](https://k3d.io/) | v5.x+ | Local k3s (lightweight Kubernetes) cluster used by `just up` (`brew install k3d`) |
| [Helm](https://helm.sh/) | v3.x+ | Kubernetes package manager (`brew install helm`) |
| [helm-diff plugin](https://github.com/databus23/helm-diff) | latest | Previews chart changes (`helm diff upgrade`) before applying them |
| [Helmfile](https://helmfile.io/) | v1.x+ | Declarative multi-release orchestration (`brew install helmfile`) |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | v1.28+ | Kubernetes CLI (`brew install kubectl`) |
| [just](https://github.com/casey/just) | latest | Task runner (every repo has a `justfile`) (`brew install just`) |
| [curl](https://curl.se/) | latest | API testing |

**Important Setup Steps**:
1. Install `k3d` to run local Kubernetes clusters. Follow the [official docs](https://k3d.io/) or use Homebrew: `brew install k3d`.
2. Install the Helm Diff plugin to preview chart changes before applying them:
   ```bash
   helm plugin install https://github.com/databus23/helm-diff --verify=false
   ```

Optional tools:
- Java 25 (Temurin) + Maven 3.6.3+ — needed to build Java backend images locally
- Node.js 22+ — needed to build Vue frontend images locally
- [k9s](https://k9scli.io/) — Terminal UI to interact with your Kubernetes clusters (`brew install k9s`)

Once cloned, run `just doctor` to check all of the above are installed and print their versions.

> **Setting up local Kubernetes (k3d)?** The workspace `justfile` drives the cluster lifecycle
> (`just up` / `just down`), but the full architecture, namespace layout, and step-by-step manual
> setup live in [`labs64.io-helm-charts/DEVELOPERS.md`](labs64.io-helm-charts/DEVELOPERS.md) —
> read that if you want to understand or customize what's happening under the hood.

## 🚀 Quick Start

1. **Clone the Workspace Repo:**
   ```bash
   git clone git@github.com:Labs64/labs64.io-workspace.git labs64.io
   cd labs64.io
   ```

2. **Fetch the Ecosystem:**
   This clones all 9 microservice repositories into the workspace.
   ```bash
   just clone
   ```

3. **Open in DevContainer:**
   Open the folder in VS Code and click **"Reopen in Container"**.

4. **Start the Cluster:**
   ```bash
   just up
   ```

> **Deploying elsewhere?** The steps above spin up the **Local Development** mode (Helmfile + k3d).
> The Helm charts also support an **AWS QA / Staging / Prod Environment** mode (ArgoCD + Terraform,
> see `labs64.io-devops/`) and a **Users' Own Infrastructure (BYO Infra)** mode for your own cluster
> (GCP, Azure, on-prem) without cloning this whole workspace — cherry-pick individual charts via
> `helm repo add labs64io https://labs64.github.io/labs64.io-helm-charts`. See
> [Deployment Modes](https://github.com/Labs64/labs64.io-helm-charts#deployment-modes) in the
> helm-charts README for the full picture.

## 🛠️ Included Repositories

The workspace includes the following 9 core microservices:

| Repository | Description |
|------------|-------------|
| [**labs64.io-docs**](https://github.com/Labs64/labs64.io-docs) | Public-facing product documentation and developer integration guides. |
| [**labs64.io-devops**](https://github.com/Labs64/labs64.io-devops) | Infrastructure-as-Code (Terraform), CI/CD pipelines, and GitOps automation. |
| [**labs64.io-helm-charts**](https://github.com/Labs64/labs64.io-helm-charts) | Kubernetes Helm charts, ArgoCD deployments, and the centralized observability stack. |
| [**labs64.io-authproxy**](https://github.com/Labs64/labs64.io-authproxy) | Traefik-based API gateway handling ecosystem ingress and authentication proxying. |
| [**labs64.io-auditflow**](https://github.com/Labs64/labs64.io-auditflow) | Multi-tenant Audit-as-a-Service platform for secure compliance logging. |
| [**labs64.io-payment-gateway**](https://github.com/Labs64/labs64.io-payment-gateway) | Subscription billing engine and Payment Service Provider (PSP) integrations. |
| [**labs64.io-checkout**](https://github.com/Labs64/labs64.io-checkout) | Core transaction processing and commerce workflow engine. |
| [**labs64.io-customer-portal**](https://github.com/Labs64/labs64.io-customer-portal) | Self-service SaaS management portal for end-users. |

## 🎯 Key Features

### Universal DevContainer
Open the folder in VS Code and click **"Reopen in Container"**. You get a consistent development environment with:
- Java 25 & Maven 3.6.3+
- Python 3.13
- Node.js 20.x (Vue 3 ecosystem)
- Terraform
- Docker (Docker-in-Docker)
- All necessary build tools

### The Knowledge Graph
The ecosystem is indexed by a shared knowledge graph (`graphify-out/`). Use `graphify` for architectural queries:
```bash
graphify query "<question>"    # targeted lookup
graphify update .              # refresh after code changes
```

### 🤖 AI Skills
The workspace is equipped with custom AI agent skills located in `.agents/skills/` to automate complex ecosystem workflows. Available skills include:
- `openapi-first-change`: For safely updating OpenAPI specifications.
- `helm-config-binding-check`: For verifying Helm chart config mapping.
- `local-k8s-qa-audit`: For auditing local Kubernetes deployments.
- `rfc-writing`: For drafting architecture and technical RFCs.

## 🔧 Development Commands

Use `just` for ecosystem-wide orchestration. Run `just --list` any time for the full, up-to-date recipe list with descriptions.

### 🚀 Bootstrapping & Deploying
```bash
just doctor       # check required tooling is installed (run this first)
just clone        # clone all repositories
just up           # build images and deploy locally
just down         # tear down the local cluster (images/registry untouched)
```

### 📂 Working with Repositories
```bash
just pull               # pull latest changes in all repos
just status             # check git status across all repos
just verify-deps        # confirm every Java module resolves its dependencies offline
just logs [app]         # tail error logs for all modules, or one (e.g. `just logs checkout`)
just test               # run the test suite across all modules
just smoke              # run the fast, PR-gating smoke tests
```

By default, `just build` (and the module builds `just up` runs) print one colorized banner per
module with elapsed time, so a failure is easy to spot in a multi-module build. Set `VERBOSE=0` to
switch to a quieter animated-progress mode that only prints a module's log if it fails, e.g.
`VERBOSE=0 just build`.

## 📄 License

This is an open-source digital commerce platform licensed under the GNU Lesser General Public License v3.0 (LGPLv3). See the [LICENSE](LICENSE) file for details.
