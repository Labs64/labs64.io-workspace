# Workspace reference

Long-form reference that used to live in the repository README. The [README](../README.md) is the
short entry point; the published documentation is at [labs64.io/docs](https://labs64.io/docs/).

## 🚀 Quick Start

Four commands take you from nothing to the whole platform running locally, built from your own checkouts.

```bash
mkdir labs64.io && cd labs64.io                 # an empty folder to hold all repositories
git clone https://github.com/Labs64/labs64.io-workspace.git
cd labs64.io-workspace
just doctor && just clone && just up
```

1. **Clone the workspace** into an empty folder, as above. The other repositories are cloned next to it, not inside it. Keep the folder name `labs64.io-workspace`: the dev container expects it at `/workspaces/labs64.io-workspace`. Prefer SSH? Use `git@github.com:Labs64/labs64.io-workspace.git`.

2. **Get the tools.** Either open the `labs64.io-workspace` folder in VS Code and choose **"Reopen in Container"**, which gives you every tool at the pinned version, or install the [prerequisites](#-prerequisites) yourself. `just doctor` reports what is missing.

3. **Fetch the ecosystem.** `just clone` clones the 10 ecosystem repositories into `../`.

4. **Start it.** `just up` creates a local k3d cluster with an image registry, builds every first-party image in a builder container, and deploys the platform. The first run downloads and builds everything, so it takes a while; later runs reuse the caches. It ends with:

   ```
   Local environment ready: http://gateway.localhost/swagger-ui/
   ```

5. **Check it.** Open <http://gateway.localhost/swagger-ui/>, then make an authenticated call:

   ```bash
   TOKEN=$(curl -s -X POST http://mock-oidc.localhost/labs64io/token \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     --data-urlencode 'grant_type=client_credentials' \
     --data-urlencode 'client_id=local-test' \
     --data-urlencode 'client_secret=local-test' \
     --data-urlencode 'scope=admin' \
     | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')

   curl -i -X POST http://gateway.localhost/auditflow/api/v1/audit/publish \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"eventType":"demo.hello","sourceSystem":"local"}'
   ```

   `just smoke` runs the fast smoke tests against the cluster, and `just down` deletes it again.

6. **(Optional) Open all repos at once.** `File ▸ Open Workspace from File…` → `labs64.io-workspace/labs64.io.code-workspace`. This multi-root workspace lists the workspace plus the 10 ecosystem repos as separate roots, each with its own Source Control view, and carries shared editor settings and extension recommendations. Repos you haven't cloned yet simply show up empty until `just clone` fetches them.

After `just clone`, the folder you started in looks like this:

```
<ecosystem-root>/
├── labs64.io-workspace/     # this repo — justfile, DevContainer, scripts
├── labs64.io-auditflow/
├── labs64.io-checkout/
├── labs64.io-helm-charts/
└── ...                      # the remaining ecosystem repositories
```

All `just` recipes are run from `labs64.io-workspace/` and resolve the other repos via `../`. The DevContainer mounts `<ecosystem-root>` at `/workspaces`, so the whole ecosystem is visible inside the container.

`just up` deploys what `labs64.io-helm-charts/overrides/helmfile/values.local.yaml` describes. That override decides whether mock OIDC, bundled Keycloak, or neither is installed; the API Gateway override selects the corresponding issuer.

Something not working? See [Troubleshooting your first run](https://labs64.io/docs/getting-started/troubleshooting.html).

## 📋 Prerequisites

The DevContainer bundles all of these. Install them yourself only if you work outside it.

| Tool | Version | Purpose |
|------|---------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine | latest | Container runtime (`brew install --cask docker`). Give it at least 4 CPUs and 8 GB of memory |
| [k3d](https://k3d.io/) | v5.x+ | Local k3s (lightweight Kubernetes) cluster used by `just up` (`brew install k3d`) |
| [Helm](https://helm.sh/) | v4.x | Kubernetes package manager (`brew install helm`) |
| [helm-diff plugin](https://github.com/databus23/helm-diff) | pinned | Previews chart changes (`helm diff upgrade`) before applying them |
| [Helmfile](https://github.com/helmfile/helmfile) | v1.x+ | Declarative multi-release orchestration (`brew install helmfile`) |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | v1.28+ | Kubernetes CLI (`brew install kubectl`) |
| [just](https://github.com/casey/just) | latest | Task runner (every repo has a `justfile`) (`brew install just`) |
| [curl](https://curl.se/) | latest | API testing |

The exact versions the project pins are in [`tool-versions.env`](../tool-versions.env). `just doctor` compares your machine against that file and, for a missing Helm plugin, prints the install command with the pinned version. To install helm-diff directly:

```bash
source tool-versions.env
helm plugin install https://github.com/databus23/helm-diff --version "v${HELM_DIFF_VERSION}" --verify=false
```

Ports 80, 443 and 5005 must be free: the local gateway and the image registry use them.

Optional tools, reported by `just doctor` but never required by `just up`:
- Java 25 (Temurin) + Maven 3.6.3+ — to build or test a Java backend on your machine instead of in the builder container
- Node.js 26+ — the same, for the Vue frontends
- [k9s](https://k9scli.io/) — Terminal UI to interact with your Kubernetes clusters (`brew install k9s`)

> **Setting up local Kubernetes (k3d)?** The workspace `justfile` drives the cluster lifecycle
> (`just up` / `just down`), but the full architecture, namespace layout, and step-by-step manual
> setup live in [`../labs64.io-helm-charts/DEVELOPERS.md`](https://github.com/Labs64/labs64.io-helm-charts/blob/master/DEVELOPERS.md) —
> read that if you want to understand or customize what's happening under the hood.

> **Deploying elsewhere?** The steps above spin up the **Local Development** mode (Helmfile + k3d).
> The published charts install on any cluster without this workspace: `install.sh` in
> [labs64.io-helm-charts](https://github.com/Labs64/labs64.io-helm-charts#quick-start) for a guided
> install, the umbrella chart with the **AWS Staging / Prod** reference profile on managed data
> stores, or individual charts on **your own infrastructure** (GCP, Azure, on-prem) via
> `helm repo add labs64io https://labs64.github.io/labs64.io-helm-charts`. See
> [Deployment Modes](https://github.com/Labs64/labs64.io-helm-charts#deployment-modes) in the
> helm-charts README for the full picture.

## 🤝 Contributing

Contributions are welcome, from a typo fix to a new module feature. The
[Contributing Guide](https://labs64.io/docs/development/contributing.html) explains where a change
belongs, the few rules the build enforces, and how to open a pull request. In short: fork the
repository that owns what you are changing, run its tests (`just --list` shows them), and open a
pull request against `master`. Each repository's `AGENTS.md` describes its layout and commands, for
people as much as for AI agents.

## Optional EE commands

The optional sibling repository `../labs64.io-workspace-ee/` adds commands under
`just ee`. It uses this workspace's DevContainer and shared tooling. The public
commands do not require it and keep the same behavior when it is present.

With the EE workspace in place, run `just ee clone` to clone missing
repositories listed in its `repos.txt` (Labs64 names or HTTPS GitHub URLs).
Run `just ee pull` to update its Git checkout and existing
listed checkouts. Missing checkouts are reported and skipped by `pull`.
Use `just ee status` for branches and local changes, and `just ee doctor` to check
EE checkouts, remote identities, upstreams and authenticated remote access.
Run `just ee test [target]` to execute module-owned test suites for one private
runtime module or all installed modules.
The public `just doctor` remains the shared tooling check.
See `../labs64.io-workspace-ee/README.md` for configuration.

## 🛠️ Included Repositories

The workspace clones 10 repositories as siblings of itself — the runtime services plus the shared libraries, infrastructure, and docs that support them.

**Services**

| Repository | Description |
|------------|-------------|
| [**labs64.io-authproxy**](https://github.com/Labs64/labs64.io-authproxy) | Traefik-based API gateway handling ecosystem ingress and authentication proxying. |
| [**labs64.io-auditflow**](https://github.com/Labs64/labs64.io-auditflow) | Multi-tenant Audit-as-a-Service platform for secure compliance logging. |
| [**labs64.io-payment-gateway**](https://github.com/Labs64/labs64.io-payment-gateway) | Subscription billing engine and Payment Service Provider (PSP) integrations. |
| [**labs64.io-checkout**](https://github.com/Labs64/labs64.io-checkout) | Core transaction processing and commerce workflow engine. |
| [**labs64.io-customer-portal**](https://github.com/Labs64/labs64.io-customer-portal) | Self-service SaaS management portal for end-users. |

**Shared libraries, infrastructure & docs**

| Repository | Description |
|------------|-------------|
| [**labs64.io-commons**](https://github.com/Labs64/labs64.io-commons) | Shared Java libraries (auth SDK, business telemetry, common utilities) consumed by the backend services. |
| [**labs64.io-helm-charts**](https://github.com/Labs64/labs64.io-helm-charts) | Kubernetes Helm charts (module charts + the `labs64io-ecosystem` umbrella), the local Helmfile stack, and the centralized observability stack. |
| [**labs64.io-tests**](https://github.com/Labs64/labs64.io-tests) | Black-box, contract-first API regression & integration test suite (Robot Framework). |
| [**labs64.io-docs**](https://github.com/Labs64/labs64.io-docs) | Public-facing product documentation and developer integration guides. |
| [**labs64.io**](https://github.com/Labs64/labs64.io) | Public marketing website (labs64.io). |

## 🎯 Key Features

### Universal DevContainer
Open the folder in VS Code and click **"Reopen in Container"**. You get a consistent development environment with:
- Java 25 & Maven 3.6.3+
- Python 3.14
- Node.js 26.x (Vue 3 ecosystem)
- Terraform
- Docker (Docker-in-Docker)
- All necessary build tools

### The Knowledge Graph
The ecosystem is indexed by a shared knowledge graph (`../graphify-out/`, at the ecosystem root so it spans every sibling repo). Use `graphify` for architectural queries:
```bash
graphify query "<question>"    # targeted lookup
graphify update ..             # refresh after code changes (indexes all sibling repos)
```

### 🤖 AI Skills
The workspace is equipped with custom AI agent skills located in `.agents/skills/` to automate complex ecosystem workflows. Available skills include:
- `openapi-first-change`: For safely updating OpenAPI specifications.
- `helm-config-binding-check`: For verifying Helm chart config mapping.
- `local-k8s-qa-audit`: For auditing local Kubernetes deployments.
- `rfc-writing`: For drafting architecture and technical RFCs.
- `ecosystem-website-sync`: For keeping the public website in sync with the ecosystem.
- `test-suite-steward`: For auditing and extending the black-box test suite.

## 🔧 Development Commands

Use `just` for ecosystem-wide orchestration. Run `just --list` any time for the full, up-to-date recipe list with descriptions.

### 🚀 Bootstrapping & Deploying
```bash
just doctor       # check required tooling is installed (run this first)
just clone        # clone all repositories
just up           # build and deploy the stack described by Helm overrides
just test         # complete local gate; auto-detects the deployed identity provider
IDENTITY_PROVIDER=keycloak just test  # optional explicit override
just down         # tear down the local cluster (images/registry untouched)
```

### 📂 Working with Repositories
```bash
just pull               # pull latest changes in all repos
just status             # check git status across all repos
just verify-deps        # confirm every Java module resolves its dependencies offline
just check              # cross-repo gates: release wiring + shared version pins
just verify-process     # the gates' own tests (here + helm-charts), then every gate (CI runs the same daily)
just logs [app]         # tail error logs for all modules, or one (e.g. `just logs checkout`)
just smoke              # run the fast, PR-gating smoke tests
just test               # run normal regression + PSP-stub tests, then restore normal PG
just regression         # run ordinary regression without changing provider endpoints
```

### 🔖 Versions, releases & dependency updates

Every version has exactly one owner; nothing below is restated anywhere else.

| What | Single source |
|------|---------------|
| CLI toolchain (helm, helmfile, k3d, terraform, …) for the dev container **and** CI | [`tool-versions.env`](../tool-versions.env) — `just doctor` reports drift |
| Spring Boot line, BOM overrides, shared Java dependency/plugin versions, commons libraries | `io.labs64:labs64io-parent` in `labs64.io-commons` |
| Third-party Helm chart versions and repositories | `labs64.io-helm-charts/helmfile.yaml.gotmpl` |
| CRD sets applied outside Helm (Gateway API, Traefik CRDs) | `labs64.io-helm-charts/justfile.versions` |
| Dependency updates in all repositories | Renovate, shared preset [`default.json`](../default.json) |

**Releasing** is the same gesture in every repository: publish a GitHub Release whose tag is the
version (`X.Y.Z`). No pom carries a version — the tag becomes the jar, the image tag and label,
and the chart `appVersion`; the module chart and the umbrella are bumped by an automated PR. The
published umbrella chart version is the ecosystem release; whoever operates an environment pins it. Release order when commons changed:
`commons` → modules pin the new `labs64io-parent` → module releases. See
[`.github/workflows/README.md`](../.github/workflows/README.md) for the pipeline in detail.

`just check` verifies the parts no single repository can see: `check-release-wiring` (every
released image reaches its chart) and `check-pins` (pins that two files or repositories must
share actually agree; no pom hard-codes a version; no version constant creeps back into a
justfile; the local k3s minor equals EKS and the local PostgreSQL, Valkey and RabbitMQ lines
equal the AWS ones).

The two justfile repositories keep their pins in a `justfile.versions` that the justfile `import`s,
so recipes still use `{{CHART_VERSION}}` etc. unchanged. (`just` loads only one dotenv file, and both
justfiles already use theirs, so the `tool-versions.env` approach is not available there.)
To bump a version, edit that one file or merge the Renovate PR.

Set `VERBOSE=0` to switch to a quieter animated-progress mode that only prints a module's log if it fails, e.g. `VERBOSE=0 just build`.
