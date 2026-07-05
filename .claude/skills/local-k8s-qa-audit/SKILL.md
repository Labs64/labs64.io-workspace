---
name: local-k8s-qa-audit
description: Use when the developer asks to verify, audit, or QA the local Kubernetes deployment of the Labs64.IO Ecosystem — checking that all modules, third-party (3pp) tools, Helm releases, and configs are healthy and consistent. Triggers include "verify local k8s setup", "audit the cluster", "check local deployment health", "validate the local stack".
---

# Local K8s QA & Configuration Audit

## Overview

Full-stack audit of the Labs64.IO Ecosystem's **local** Kubernetes deployment: infra health, runtime health, functional flows, config consistency, and architecture docs. Produces one Markdown report and fixes obvious low-risk issues in place. Not for production/staging clusters or CI pipelines.

Every module and every third-party tool in the local stack is expected to be **fully functional** — audit all of them with the same rigor. If a module turns out not to be, that's a finding, not an assumption to build the audit around.

Act as senior QA Engineer + Kubernetes Engineer + Solution Architect simultaneously.

> **TEMPORARY EXCEPTION (until further notice):** `labs64.io-checkout`, `labs64.io-payment-gateway`, and `labs64.io-customer-portal` are currently under active development and not fully implemented. **Still deploy them as part of the stack** (Steps 1–3, 5–7 apply normally — install their charts, audit their k8s resources, config, and docs like everything else) but **exclude them from Step 4 functional/e2e validation** — don't run their API smoke tests or fail the audit over their functional gaps. Remove this exception once the user says these modules are ready for full functional coverage again.

## Step 1 — Discover the ecosystem fresh (don't reuse a stale module list)

- Read root `AGENTS.md` and every `<module>/AGENTS.md` before touching anything — conventions and each module's own documented data/event flow live there.
- Run `graphify query "<question>"` for architecture/relationship questions (shared graph covers all repos).
- Enumerate modules with `ls -d labs64.io-*/` and **audit every module found** — do not hardcode a fixed module list here, the ecosystem grows.
- Read `labs64.io-helm-charts/DEVELOPERS.md` and its `justfile` for the actual local commands/topology.
- **Important**: For a clean cluster test, run `just down` to destroy the existing environment, then run `just cluster-create` to start the registry, `just build-images` to push images, and finally `just up`. If the cluster is simply stopped, you can just run `just up`. Ensure any necessary local secrets are configured in `labs64.io-helm-charts/overrides/<module>/values.secrets.local.yaml` if the cluster fails to pull secrets.

## Step 2 — Kubernetes audit

Namespaces, Helm releases (`helm ls -A`), Deployments/StatefulSets, Services, Ingress/IngressRoute, gateway config, PVs/PVCs, ConfigMaps, Secrets, ServiceAccounts/RBAC, startup ordering & dependencies, resource requests/limits.

## Step 3 — Runtime health

Pod readiness, liveness/readiness probes, restart counts, CrashLoopBackOff, image pull errors, log warnings/errors, service discovery, in-cluster DNS, internal networking.

## Step 4 — Functional validation

- **Skip checkout, payment-gateway, and customer-portal here** per the temporary exception noted above — deploy them, but don't run their functional/e2e checks until the user lifts the exception.
- API Gateway routing (Traefik) — e.g. `gateway.localhost/swagger-ui/`.
- AuthN/AuthZ + OIDC flow — e.g. `just e2e-auth-test` (no-token → 401, valid → pass, wrong-scope → 403). The OIDC provider is part of the local stack's shared tooling; validate the flow works, don't re-evaluate where it's deployed.
- Service-to-service communication, event/queue processing.
- For each module with a multi-hop data or event flow (queue → service → downstream steps), check its own `AGENTS.md`/docs for the flow it claims to implement, then verify actual runtime behavior matches — request/response tracing, log correlation, whatever confirms the real path. Don't assume a flow shape; every module can differ.
- Observability: confirm metrics/traces/logs actually reach Prometheus/Tempo/Loki via the OTel Collector. A bare `up` profile without the collector deployed will show expected OTLP export errors — check which profile is running before flagging this as a defect.

## Step 5 — Configuration review

Look for: duplicate config, missing config, obsolete config, drift between modules, inconsistent naming/Helm values, deployment patterns that diverge between modules that should follow the same convention (see AGENTS.md "Shared conventions" table), simplification/standardization opportunities.

**Fix obvious, low-risk, safe issues directly.** Document — don't implement — anything architectural or high-risk (leave those for the backlog, or route through the `rfc-writing` skill).

## Step 6 — Architecture review

**Mermaid diagrams**: search `**/*.md` across all modules and `labs64.io-docs*`/`labs64.io-docs-internal` for `mermaid` blocks. For every diagram, verify it still matches the module's actual implemented behavior (traced in Step 4) — correct any diagram that has drifted from reality, regardless of which module it belongs to. Also improve diagrams generally: fewer crossing lines, related services grouped, consistent naming, clear visual hierarchy.

## Step 7 — Code/config quality

Helm chart consistency, manifest YAML quality, naming conventions, reuse opportunities, structural consistency across modules per the AGENTS.md conventions table.

## Guardrails while auditing

- Never edit OpenAPI-generated Java under `target/` — change the YAML spec instead (see `openapi-first-change`).
- Never hardcode credentials — env vars / K8s Secrets only.
- Preserve non-root `l64user` (uid/gid 1064) in Dockerfiles.
- Never remove `OtelLogbackInstaller`.
- Each repo has independent git history — never cross-commit between repos. Don't commit fixes unless the user asks; an audit run shouldn't commit unprompted.
- Local-cluster fixes applied via Helm (upgrade/rollback) are reversible — apply obvious ones freely. Cluster-destructive ops (deleting PVCs, `helm uninstall`) need explicit confirmation first.

## Deliverable

One Markdown report at `.claude/reports/`, named `QA_AUDIT_REPORT_YYYYMMDD.md` (today's date). If a file with the same name already exists for today, add an incremental suffix (e.g., `QA_AUDIT_REPORT_YYYYMMDD_1.md`) so successive audits don't overwrite each other. The report should contain these sections in order:

1. **Executive Summary** — health, deployment status, major findings, readiness assessment
2. **Test Results** — executed / passed / failed / skipped, plus assumptions made
3. **Kubernetes Audit**
4. **Configuration Audit**
5. **Architecture Review** — diagram corrections
6. **Issues Found** — severity, affected module, description, root cause, recommended fix, auto-fixed y/n
7. **Improvements Backlog** — grouped Critical / High / Medium / Low / Nice-to-have, each with impact / complexity / effort estimate
8. **Changes Performed** — files modified, reason, expected impact

## Working principles

- Understand before changing; follow existing conventions over introducing new ones.
- Fix root causes, not symptoms; keep changes minimal — no drive-by refactors.
- Record every modification made, however small.
- If required info is missing or ambiguous, stop and ask concise clarifying questions before proceeding — don't guess scope.

## Common mistakes

| Mistake | Fix |
|---|---|
| Assuming a module is "probably not finished yet" and going easy on it | Every module is expected fully functional — audit all of them the same way; only note reduced scope if the module's own docs say so |
| Restricting the audit to a fixed list of named modules | Enumerate `labs64.io-*/` dynamically and audit everything found |
| Assuming one module's event/data flow shape applies to another | Check each module's own `AGENTS.md`/docs for its documented flow before verifying it |
| Re-evaluating where shared dev infra (e.g. the OIDC provider) should live | That's a one-time architecture decision, not a recurring audit task — just validate it works |
| Flagging OTLP export errors as a bug when no collector is deployed in the active profile | Check which `up` profile is running first |
| Overwriting a previous audit's report | Name the report `QA_AUDIT_REPORT_YYYYMMDD.md` with today's date |
| Running e2e/functional checks against checkout, payment-gateway, or customer-portal | Temporary exception (see Overview) — deploy them, but skip their Step 4 functional validation until the user lifts it |
