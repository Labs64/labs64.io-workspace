# Workspace reference

Long-form reference that used to live in the repository README. The [README](../README.md) is the
short entry point; the published documentation is at [labs64.io/docs](https://labs64.io/docs/).

For everything else see [Run the full ecosystem locally](https://labs64.io/docs/getting-started/run-the-full-ecosystem-locally.html).

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
Use `just ee show-repos` for branches and local changes, and `just ee doctor` to check
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
| [**labs64.io-authproxy**](https://github.com/Labs64/labs64.io-authproxy) | The Auth Gateway: the authenticated edge for the ecosystem. It verifies OIDC/JWT tokens, matches the route and asks Cerbos before a request reaches a module. |
| [**labs64.io-auditflow**](https://github.com/Labs64/labs64.io-auditflow) | Multi-tenant Audit-as-a-Service platform for secure compliance logging. |
| [**labs64.io-payment-gateway**](https://github.com/Labs64/labs64.io-payment-gateway) | Subscription billing engine and Payment Service Provider (PSP) integrations. |
| [**labs64.io-checkout**](https://github.com/Labs64/labs64.io-checkout) | Core transaction processing and commerce workflow engine. |
| [**labs64.io-reporting**](https://github.com/Labs64/labs64.io-reporting) | Read-only reports over the events AuditFlow stored, per customer. |
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

### 📂 Working with Repositories
```bash
just list-prs           # open pull requests across all repos
just check-deps         # confirm every Java module resolves its dependencies offline
just check              # cross-repo gates: release wiring, Renovate wiring, shared version pins, justfiles
just ci                 # what this repository's CI runs: the gates' own tests, actionlint, the Renovate preset, every gate
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
