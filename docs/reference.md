# Workspace reference

Long-form reference that used to live in the repository README. The [README](../README.md) is the
short entry point; the published documentation is at [labs64.io/docs](https://labs64.io/docs/).

For everything else see [Run the full ecosystem locally](https://labs64.io/docs/getting-started/run-the-full-ecosystem-locally.html) and [Workspace repositories](https://labs64.io/docs/development/workspace-repositories.html).

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
