# AGENTS.md — Labs64.IO Ecosystem

Guidance for AI agents working in the Labs64.IO workspace. Read this before making changes.

## What this is

Open-source digital commerce platform — polyglot microservices ecosystem. 9 independent git repos, shared Helm charts, ArgoCD deployment. **Not a monorepo.**

## Quick orientation

| What you need | Where to look |
|---------------|---------------|
| Work on a module | `<module>/AGENTS.md` (always read before changes) |
| Understand architecture | `graphify query "<question>"` |
| Deploy to Kubernetes | `labs64.io-helm-charts/` + `labs64.io-devops/` |
| Write infrastructure | `labs64.io-devops/terraform/` |
| Write an RFC | `labs64.io-docs-internal/rfc/RFC_TEMPLATE.md` |
| Set up local k8s | `labs64.io-helm-charts/DEVELOPERS.md` |
| Understand observability | `labs64.io-helm-charts/OBSERVABILITY.md` |

## Critical guardrails

Non-negotiable. Violations break builds, deployments, or observability.

1. **Never edit OpenAPI-generated Java** under `target/`. Change the YAML spec and rebuild.
2. **Never hardcode credentials.** Environment variables or K8s Secrets only.
3. **Preserve non-root user `l64user`** (uid/gid 1064) in all Dockerfiles.
4. **Observability is infrastructure-owned.** Never add OpenTelemetry SDK/starter dependencies or SDK bootstrap to services; the OTel Java Agent (bundled in images) / `opentelemetry-instrument` (entrypoint) provide instrumentation, toggled purely by deployment env (`observability.enabled` in Helm, obs compose overlay). Business telemetry goes through each service's thin `BusinessTelemetry` abstraction. See `labs64.io-helm-charts/OBSERVABILITY.md` (canonical model) and RFC 03 in labs64.io-docs-internal.
5. **Keep transformer/sink ID validation regex consistent** across Java and Python (`^[a-zA-Z0-9_]+$`).
6. **Chart versions must match** between Helm `Chart.yaml` and ArgoCD ApplicationSet pin.
7. **Network policies are restrictive** — new services need explicit ingress from traefik.
8. **Each repo has its own git history** — never cross-commit between repositories.
9. **Run `graphify update .`** after significant code changes.

## Shared conventions

| Convention | Detail |
|------------|--------|
| Java | 25, Maven 3.6.3+, Spring Boot 4.x, OpenAPI-first |
| Python | 3.13, FastAPI, Uvicorn |
| Vue | 3, Composition API, Vite, Pinia, Bootstrap 5 |
| Docker | All images run as `l64user` (uid/gid 1064) |
| Tests | JUnit 5 (Java), pytest (Python), Vitest (Vue) |
| Task runner | `just` — check each repo's justfile |
| Observability | Infrastructure-owned; runtime auto-instrumentation (OTel Java Agent / opentelemetry-instrument) → OTel Collector → Tempo (traces) / VictoriaLogs k8s · Loki compose (logs) / Prometheus (metrics) → Grafana; Java metrics via Micrometer `/actuator/prometheus`. Canonical model: `labs64.io-helm-charts/OBSERVABILITY.md` |

## Where to make common changes

| Goal | Where |
|------|-------|
| AuditFlow API contract | `labs64.io-auditflow/auditflow-api/src/main/resources/openapi/openapi-audit-v1.yaml` |
| Add AuditFlow sink | `labs64.io-auditflow/auditflow-sink/sinks/<name>.py` |
| Checkout API contract | `labs64.io-checkout/checkout-be/src/main/resources/openapi/` |
| Payment Gateway PSP | `labs64.io-payment-gateway/payment-gateway-be/src/main/java/.../psp/providers/` |
| Traefik auth behavior | `labs64.io-gateway/traefik-authproxy/` |
| Helm chart templates | `labs64.io-helm-charts/charts/<chart>/templates/` |
| Terraform infrastructure | `labs64.io-devops/terraform/` |
| Network policies | `labs64.io-devops/kubernetes/network-policies/` |

## Knowledge graph

Shared graph at `graphify-out/` covers all repos (7000+ nodes).

```bash
graphify query "<question>"    # targeted lookup (preferred)
graphify path "A" "B"         # relationship trace
graphify explain "concept"    # focused explanation
graphify update .             # refresh after code changes
```

## Superpowers

- **Plans:** `.claude/superpowers/plans/YYYY-MM-DD-{session-slug}.md`
- **Specs:** `.claude/superpowers/specs/YYYY-MM-DD-{session-slug}.md`
