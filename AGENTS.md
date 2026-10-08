# AGENTS.md — Labs64.IO Ecosystem

Guidance for AI agents working in the Labs64.IO workspace. Read this before making changes.

## What this is

Open-source digital commerce platform — polyglot microservices ecosystem. 10 independent git repos, shared Helm charts; environments install the published `labs64io-ecosystem` umbrella chart. **Not a monorepo.**

## Repository layout

The 10 ecosystem repos are cloned as **siblings** of `labs64.io-workspace`, not inside it:

```
/workspaces/                    # ecosystem root (mounted by the DevContainer)
├── labs64.io-workspace/        # justfile, DevContainer, scripts — you usually start here
├── labs64.io-auditflow/
├── labs64.io-helm-charts/
└── ...
```

**Throughout this file, a path like `labs64.io-helm-charts/…` is relative to the ecosystem root** — from `labs64.io-workspace/` (the default working directory) reach it as `../labs64.io-helm-charts/…`. Paths between two ecosystem repos are unaffected: they remain siblings of each other.

## Quick orientation

| What you need | Where to look |
| --- | --- |
| Work on a module | `<module>/AGENTS.md` (always read before changes) |
| Deploy to Kubernetes | `labs64.io-helm-charts/` (see its README's Deployment Modes: Local Development, AWS QA/Staging/Prod, BYO Infra) |
| Write public docs (onboarding, config, technical reference) | `labs64.io-docs/` (its `AGENTS.md` first — the ultimate reference for running/using/configuring modules; mirrors module ids from `labs64.io/_data/modules.yml`, never restates status/version) |
| Set up local k8s | `labs64.io-helm-charts/DEVELOPERS.md` |
| Understand observability | `labs64.io-helm-charts/OBSERVABILITY.md` |
| Run/add regression & integration tests | `labs64.io-tests/` (`AGENTS.md` first — contract-first, gateway-edge only) |

## Critical guardrails

Non-negotiable. Violations break builds, deployments, or observability.

1. **Never edit OpenAPI-generated Java** under `target/`. Change the YAML spec and rebuild.
2. **Never hardcode credentials.** Environment variables or K8s Secrets only.
3. **Preserve non-root user `l64user`** (uid/gid 1064) in all Dockerfiles (exception: nginx-based UI frontends may use UID 101).
4. **Observability is infrastructure-owned.** Never add OpenTelemetry SDK/starter dependencies or SDK bootstrap to services; the OTel Java Agent (bundled in images) / `opentelemetry-instrument` (entrypoint) provide instrumentation, toggled purely by deployment env (`observability.enabled` in Helm, obs compose overlay). Business telemetry goes through each service's thin `BusinessTelemetry` abstraction. See `labs64.io-helm-charts/OBSERVABILITY.md` (canonical model).
5. **Keep transformer/sink ID validation regex consistent** across Java and Python (`^[a-zA-Z0-9_]+$`).
6. **Every version has one owner — never restate a pin, never write a version into a pom.**
   - Chart versions and Helm repositories: `labs64.io-helm-charts/helmfile.yaml.gotmpl`.
     Spring Boot line, BOM overrides, shared Java versions: `io.labs64:labs64io-parent`
     (`labs64.io-commons`). CLI tools: `tool-versions.env` here.
   - What an environment runs: the umbrella chart version its operator pins — the umbrella
     chart version is the ecosystem release number. Versions never go back into a justfile:
     `labs64.io-helm-charts` keeps its own in `justfile.versions`, which the justfile imports
     (`just check-pins` fails on a `*_VERSION :=` in a justfile). A chart change bumps its `version` and every chart vendoring it,
     umbrella included (`just bump <chart>` in helm-charts; chart CI enforces it).
   - Java poms declare `<version>${revision}</version>` (default `0.0.0-SNAPSHOT`). A release is
     a GitHub Release tagged `X.Y.Z`: the tag becomes the jar version, image tag/label and chart
     `appVersion`. Never commit a version bump, and never release against a `-SNAPSHOT` parent
     or dependency — the release build refuses it (`requireReleaseDeps` in `labs64io-parent`).
   - A pin that two places genuinely must share is verified by `just check-pins`; add it there
     instead of writing "keep in sync" in a comment.
7. **Network policies must preserve explicit communication paths** — allow ingress from
   Traefik/AuthProxy for external routes and from the specific caller modules for direct
   in-cluster integrations.
8. **Each repo has its own git history** — never cross-commit between repositories.
9. **Database-per-service.** Each service owns its logical database(s). Never share database credentials or connect to another service's database. New services must declare egress NetworkPolicies restricting outbound traffic to only their designated databases. See `labs64.io-helm-charts/DATABASES.md`.

## Shared conventions

| Convention | Detail |
| --- | --- |
| Java | 25, Maven 3.6.3+, Spring Boot 4.x, OpenAPI-first |
| Python | 3.14, FastAPI, Uvicorn |
| Vue | 3, Composition API, Vite, Pinia, Bootstrap 5 |
| Docker | All images run as `l64user` (uid/gid 1064) |
| Tests | JUnit 5 (Java), pytest (Python), Vitest (Vue); black-box API-edge regression in `labs64.io-tests/` (Robot Framework) |
| Versions | One owner per pin (guardrail 6); runtime/tool versions in `tool-versions.env`; `just doctor` reports local drift |
| Dependency updates | Renovate; every repo's `renovate.json` only extends the shared preset `default.json` in this repo. Pins outside a package manifest carry a `# renovate: datasource=… depName=…` line directly above them |
| CI building blocks | Reusable workflows and composite actions in `.github/` here, referenced as `…@v1` (see `.github/workflows/README.md`) |
| Process self-checks | `just verify-process` (tests of the gate scripts + `just check`); this repo's `labs64io-ci.yml` runs them on every change and daily across all repositories |
| Task runner | `just` — check each repo's justfile |
| Observability | Infrastructure-owned; runtime auto-instrumentation (OTel Java Agent / opentelemetry-instrument) → OTel Collector → Tempo (traces) / Loki compose (logs) / Prometheus (metrics) → Grafana; Java metrics via Micrometer `/actuator/prometheus`. Canonical model: `labs64.io-helm-charts/OBSERVABILITY.md` |

## Service-to-service communication

- External traffic enters the Kubernetes cluster through Traefik/AuthProxy.
- HTTP calls between modules in the same cluster use the target module's Kubernetes
  Service directly and must not route through Traefik.
- Traefik/AuthProxy removes caller-supplied `X-Auth-*` headers and creates the trusted
  auth context from the validated JWT.
- Internal callers construct the same standard context:
  `X-Auth-User`, `X-Auth-Scopes`, `X-Auth-Tenant`, and `X-Request-ID`.
- `X-Auth-User` identifies the immediate caller as `service:<module>`; do not forward
  the original end-user as the authenticated caller.
- Internal scopes come from the caller integration configuration.
- Tenant comes from the trusted current context or verified domain state. For example,
  Payment Gateway resolves a PSP webhook tenant through the payment transaction, never
  directly from the webhook payload.
- Public endpoints validate request authenticity inside the owning module before
  constructing an internal auth context.
- The current model trusts in-cluster modules. Cryptographic caller verification and
  module certification through mTLS, SPIFFE/SPIRE, or an equivalent mechanism are
  unresolved future work.

## Releases

One gesture in every repository: **publish a GitHub Release whose tag is the version `X.Y.Z`.**

| Repository | What the release publishes |
| --- | --- |
| `labs64.io-commons` | `labs64io-parent` + every Java library at `X.Y.Z` (Labs64 Nexus) |
| `labs64.io-auditflow` | three images + `io.labs64:auditflow-api`, all `X.Y.Z`; chart PR |
| `labs64.io-checkout`, `-payment-gateway`, `-customer-portal`, `-authproxy` | image(s) `X.Y.Z`; chart PR |
| `labs64.io-helm-charts` | every push to `master` touching `charts/**` publishes the bumped charts |

The chain after a module release is automatic up to the deploy decision: images by digest →
PR pinning them into the module chart and bumping the umbrella → published umbrella. The
published umbrella chart version is the release; rolling it out is the operator's step.

Order matters only when commons changed: release `commons`, move the modules to the new
`labs64io-parent` (Renovate opens those PRs), then release the modules. `just check` (here)
runs the cross-repo gates; its `note` lines list modules still on a `-SNAPSHOT` parent.

## Pull requests

Every PR opened in any of the ecosystem repos must:

- Be assigned to the GitHub user `gh` is authorized as (`gh pr create --assignee "@me" ...`,
  or `gh pr edit <PR URL> --add-assignee "@me"` for one already open).
- Be added to the GitHub Project `Labs64.IO` (org `Labs64`, project number 6):

```bash
gh project item-add 6 --owner Labs64 --url <PR URL>
```

## Where to make common changes

| Goal | Where |
| --- | --- |
| AuditFlow API contract | `labs64.io-auditflow/auditflow-api/src/main/resources/openapi/openapi-audit-v1.yaml` |
| Add AuditFlow sink | `labs64.io-auditflow/auditflow-sink/sinks/<name>.py` |
| Checkout API contract | `labs64.io-checkout/checkout-be/src/main/resources/openapi/` |
| Payment Gateway PSP | `labs64.io-payment-gateway/payment-gateway-providers/<psp>/src/main/java/.../psp/providers/` |
| Traefik auth behavior | `labs64.io-authproxy/traefik-authproxy/` |
| Authorization policy (Cerbos PDP) | Change `x-labs64.auth` in the module OpenAPI; policies are generated by `labs64.io-helm-charts/policies/build-authz-policies.sh` into `charts/authz-pdp/` |
| Helm chart templates | `labs64.io-helm-charts/charts/<chart>/templates/` |
| Network policies | `labs64.io-helm-charts/charts/<chart>/templates/` (`networkPolicy` in each chart's values) |
| Website / Marketing Content | `labs64.io/` |
| Bump a 3pp chart / Helm repo | `labs64.io-helm-charts/helmfile.yaml.gotmpl` (only there) |
| Bump Spring Boot or a shared Java dependency | `labs64.io-commons/labs64io-parent/pom.xml` (only there), then release commons and move the modules' parent version |
| Bump a CLI tool (dev container + CI) | `tool-versions.env` |
| Bump a CRD set | `labs64.io-helm-charts/justfile.versions` (only there) |
| Module status / website module list | `labs64.io/_data/modules.yml` (single source; rendered into nav, module pages, roadmap; `labs64.io-docs` must never restate this — link/copy from here) |
| Module technical/integration docs | `labs64.io-docs/<module>/` (dir name must match the module's `id` in `labs64.io/_data/modules.yml`) |
| Add/audit/run tests for a module | `labs64.io-<module>/tests/e2e/` (shared keywords in `labs64.io-tests/resources/`; see `test-suite-steward` skill) |

## Superpowers

- **Plans:** `.agents/superpowers/plans/YYYY-MM-DD-{session-slug}.md`
- **Specs:** `.agents/superpowers/specs/YYYY-MM-DD-{session-slug}.md`

## Skills

Ecosystem-wide skills live in `.agents/skills/<name>/SKILL.md` (git-tracked here, so every
developer gets them by cloning this repo). The devcontainer's `post-create.sh` (via
`scripts/sync-skills.sh`) symlinks each one, by name, into Claude Code's and Codex CLI's
user-level skills directories (`$CLAUDE_CONFIG_DIR/skills`, `$CODEX_HOME/skills`) at
container creation; see `scripts/sync-skills.sh` for why this has to be per-skill and
user-level rather than a single project-level symlink. Run `just sync-skills` to pick up a
newly-added skill without a rebuild. Another `labs64.io*` repository cloned next to this one
may ship skills of its own under `.agents/skills/`; `sync-skills.sh` links those too.

Keep personal skills out of `.agents/skills/`; add them directly under your own
`$CLAUDE_CONFIG_DIR/skills` / `$CODEX_HOME/skills` instead, or promote one into this repo
with `just import-skills`.

Agents without native skill-tool support (e.g. reading only `AGENTS.md`) should still open
the relevant `SKILL.md` directly and follow it as instructions when its `description`
matches the task at hand:

- `openapi-first-change` — change an API contract
- `test-suite-steward` — add/audit/run tests in `labs64.io-tests/`
- `helm-config-binding-check` — Helm chart config changes
- `local-k8s-qa-audit` — QA against the local k3d cluster
- `ecosystem-website-sync` — keep `labs64.io` module data in sync

Adding a skill: create `.agents/skills/<name>/SKILL.md` with `name`/`description`
frontmatter (Claude Code's skill format), then run `just sync-skills` (or rebuild the
container) to link it — no other registration step, same as adding a transformer/sink in AuditFlow.
