# AGENTS.md — Labs64.IO Ecosystem

Guidance for AI agents working in the Labs64.IO workspace. Read this before making changes.

## What this is

Open-source digital commerce platform — polyglot microservices ecosystem. 12 independent git repos, shared Helm charts, ArgoCD deployment. **Not a monorepo.**

## Repository layout

The 12 ecosystem repos are cloned as **siblings** of `labs64.io-workspace`, not inside it:

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
| Understand architecture | `graphify query "<question>"` |
| Deploy to Kubernetes | `labs64.io-helm-charts/` (see its README's Deployment Modes: Local Development, AWS QA/Staging/Prod, BYO Infra) + `labs64.io-devops/` for the ArgoCD/Terraform path |
| Write infrastructure | `labs64.io-devops/terraform/` |
| Write an RFC | `labs64.io-docs-internal/rfc/RFC_TEMPLATE.md` |
| Write public docs (onboarding, config, technical reference) | `labs64.io-docs/` (its `AGENTS.md` first — the ultimate reference for running/using/configuring modules; mirrors module ids from `labs64.io-website/_data/modules.yml`, never restates status/version) |
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
6. **Chart versions must match** between Helm `Chart.yaml` and ArgoCD ApplicationSet pin.
7. **Network policies must preserve explicit communication paths** — allow ingress from
   Traefik/AuthProxy for external routes and from the specific caller modules for direct
   in-cluster integrations.
8. **Each repo has its own git history** — never cross-commit between repositories.
9. **Run `graphify update ..`** (from `labs64.io-workspace/`, so all sibling repos are indexed) after significant code changes.
10. **Database-per-service.** Each service owns its logical database(s). Never share database credentials or connect to another service's database. New services must declare egress NetworkPolicies restricting outbound traffic to only their designated databases. See `labs64.io-helm-charts/DATABASES.md`.

## Shared conventions

| Convention | Detail |
| --- | --- |
| Java | 25, Maven 3.6.3+, Spring Boot 4.x, OpenAPI-first |
| Python | 3.13, FastAPI, Uvicorn |
| Vue | 3, Composition API, Vite, Pinia, Bootstrap 5 |
| Docker | All images run as `l64user` (uid/gid 1064) |
| Tests | JUnit 5 (Java), pytest (Python), Vitest (Vue); black-box API-edge regression in `labs64.io-tests/` (Robot Framework) |
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

Decision record:
`labs64.io-docs-internal/rfc/2026-08-12_RFC_09_service-principal-delegated-tenant-publishing.md`.

## Where to make common changes

| Goal | Where |
| --- | --- |
| AuditFlow API contract | `labs64.io-auditflow/auditflow-api/src/main/resources/openapi/openapi-audit-v1.yaml` |
| Add AuditFlow sink | `labs64.io-auditflow/auditflow-sink/sinks/<name>.py` |
| Checkout API contract | `labs64.io-checkout/checkout-be/src/main/resources/openapi/` |
| Payment Gateway PSP | `labs64.io-payment-gateway/payment-gateway-be/src/main/java/.../psp/providers/` |
| Traefik auth behavior | `labs64.io-authproxy/traefik-authproxy/` |
| Authorization policy (Cerbos PDP) | Change `x-labs64.auth` in the module OpenAPI; policies are generated by `labs64.io-helm-charts/policies/build-authz-policies.sh` into `charts/authz-pdp/` |
| Helm chart templates | `labs64.io-helm-charts/charts/<chart>/templates/` |
| Terraform infrastructure | `labs64.io-devops/terraform/` |
| Network policies | `labs64.io-devops/kubernetes/network-policies/` |
| Website / Marketing Content | `labs64.io-website/` |
| Module status / website module list | `labs64.io-website/_data/modules.yml` (single source; rendered into nav, module pages, roadmap; `labs64.io-docs` must never restate this — link/copy from here) |
| Module technical/integration docs | `labs64.io-docs/<module>/` (dir name must match the module's `id` in `labs64.io-website/_data/modules.yml`) |
| Add/audit/run tests for a module | `labs64.io-tests/tests/<module>/` (see `test-suite-steward` skill) |

## Knowledge graph

Shared graph at `graphify-out/` (ecosystem root) covers all repos (7000+ nodes).

```bash
graphify query "<question>"    # targeted lookup (preferred)
graphify path "A" "B"         # relationship trace
graphify explain "concept"    # focused explanation
graphify update ..            # refresh after code changes (from labs64.io-workspace/)
```

## Superpowers

- **Plans:** `.agents/superpowers/plans/YYYY-MM-DD-{session-slug}.md`
- **Specs:** `.agents/superpowers/specs/YYYY-MM-DD-{session-slug}.md`

## Skills

Ecosystem-wide skills live in `.agents/skills/<name>/SKILL.md` (git-tracked here, so every
developer gets them by cloning this repo). There is no single shared "skills" env var across
agent tools, so the devcontainer's `post-create.sh` symlinks this one directory into each
tool's own user-level config dir separately: `$CLAUDE_CONFIG_DIR/skills` for Claude Code and
`$CODEX_HOME/skills` for Codex CLI (both auto-discover `SKILL.md` by its `name`/`description`
frontmatter — no per-project setup, works from any repo's cwd). Agents without native
skill-tool support (e.g. reading only `AGENTS.md`) should still open the relevant `SKILL.md`
directly and follow it as instructions when its `description` matches the task at hand:

- `rfc-writing` — propose an architectural/cross-module change
- `openapi-first-change` — change an API contract
- `test-suite-steward` — add/audit/run tests in `labs64.io-tests/`
- `helm-config-binding-check` — Helm chart config changes
- `local-k8s-qa-audit` — QA against the local k3d cluster
- `ecosystem-website-sync` — keep `labs64.io-website` module data in sync

Adding a skill: create `.agents/skills/<name>/SKILL.md` with `name`/`description`
frontmatter (Claude Code's skill format) and it's picked up automatically — no registration
step, same as adding a transformer/sink in AuditFlow.
