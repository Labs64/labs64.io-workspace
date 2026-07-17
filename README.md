<p align="center"><img src="https://raw.githubusercontent.com/Labs64/.github/refs/heads/master/assets/labs64-io-ecosystem.png"></p>

# Labs64.IO :: Workspace

This repository serves as the **master workspace** for the entire Labs64.IO ecosystem. Instead of managing 9+ independent Git repositories, this workspace provides a unified `justfile` and DevContainer to orchestrate them all.

## 🚀 Quick Start

1. **Clone the Workspace Repo:**
   ```bash
   git clone git@github.com:Labs64/labs64.io-workspace.git labs64.io
   cd labs64.io
   ```

2. **Fetch the Ecosystem:**
   This clones all 9 microservice repositories into the workspace.
   ```bash
   just clone-all
   ```

3. **Open in DevContainer:**
   Open the folder in VS Code and click **"Reopen in Container"**.

4. **Start the Cluster:**
   ```bash
   just up
   ```

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

Use `just` for ecosystem-wide orchestration.

### 🚀 Bootstrapping & Deploying
```bash
# Clone all repositories
just clone-all

# Build images and deploy locally
just up
```

### 📂 Working with Repositories
```bash
# Pull latest changes in all repos
just pull-all

# Check git status across all repos
just status-all
```

## 📄 License

This is an open-source digital commerce platform licensed under the GNU Lesser General Public License v3.0 (LGPLv3). See the [LICENSE](LICENSE) file for details.
