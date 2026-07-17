---
name: test-suite-steward
description: Use when creating, auditing, running, or evaluating tests in labs64.io-tests — adding coverage for a module, checking tests match the OpenAPI contract, deciding which test level or file a scenario belongs in, choosing CI-gating tags, diagnosing a failing or flaky Robot Framework run, or scaffolding a new module's suites.
---

# Test Suite Steward

## Overview

`labs64.io-tests` is a black-box, API-edge Robot Framework suite — one layer of the Labs64.IO
ecosystem's test pyramid, not the whole thing. This skill covers that layer's full lifecycle:
deciding what to test and where it belongs, scaffolding it, running it, and judging whether a
result — or the suite itself — is healthy. It replaces the narrower `gatekeeper` skill, which
covered only the auth/authz half of this.

## Where this suite sits

| Level | Owner | Tooling | This skill's role |
|---|---|---|---|
| Unit / component | Each module's own repo | JUnit5, pytest, Vitest | Out of scope — see `<module>/AGENTS.md` |
| Contract | This repo, tag `contract` | Schemathesis-mirrored paths | Informational only; **Schemathesis itself isn't wired in yet** — the tag is reserved, not a running tool |
| **Integration / API-edge (this suite)** | `labs64.io-tests` | Robot Framework via `gateway.localhost` | Primary remit: smoke, authz, functional regression |
| Cross-service E2E | This repo, tag `e2e` | — | Reserved, not yet populated |
| Manual / exploratory | Developer | swagger-ui, `just generate-jwt` | Outside automation |

## Deciding what to add and where

| You want to... | Goes in | Tag at least |
|---|---|---|
| Cover a new module end to end | New `tests/<module>/{smoke,authz}.robot` + `resources/<module>.resource` — **then also register it**: add to the service matrix in `.github/workflows/regression-suite.yml` and to `README.md`'s structure/P0 tables, or CI silently never runs it | — |
| Add an auth/authz scenario | `tests/<module>/authz.robot` | `regression`, `auth` |
| Add a fast PR-gating check | `tests/<module>/smoke.robot` | `smoke` |
| Add a multi-step functional flow | `tests/<module>/<feature>.robot`, only if genuinely load-bearing | `regression` |
| Add a reusable step for one module | `resources/<module>.resource` | — |
| Add something generic (kubectl, mock-oidc, session helpers) | `resources/common.resource` | — |

Don't scaffold every CRUD permutation up front — start with smoke + authz, add functional
regression only for flows that have actually broken or are genuinely load-bearing.

## Creating: contract-first, always

**REQUIRED READING:** `references/contract-and-authz.md` — the OpenAPI `x-labs64-auth`
extraction workflow, the full deny/allow test matrix (including the no-scope, superset-scope,
and same-resource scope-asymmetry cases), and the local-k8s log-corroboration exception. This is
the load-bearing discipline of the whole suite: tests must map to real spec operations, not
conventional-sounding guesses — that exact drift (`GET /events`, `GET /health`,
`GET /payment-methods`) went undetected for a long time before this skill existed.

## Running and evaluating

**REQUIRED READING:** `references/running-and-auditing.md` — tag-based invocation, targeting a
different environment, reading `log.html` on failure, the CI gating shape (PR vs. nightly), and
the periodic health-audit checklist (drift, coverage gaps, duplication, flaky handling).

## Industry practices this suite leans on

- **Test pyramid discipline** — this layer stays thin; don't re-implement unit-level checks here.
- **Arrange-Act-Assert, one behavior per case** — a test case name states the single behavior it proves.
- **Test isolation** — fresh session per test case, no shared mutable state across cases.
- **Assert at the real enforcement point** — gateway edge only; a backend hit directly makes an authz test meaningless.
- **Fast feedback / slow confidence** — `smoke` gates every PR; full `regression` runs nightly.
- **Quarantine, don't delete** — a flaky case gets tagged `flaky`, not removed; the coverage still matters.
- **Corroborate, don't replace** — log-based checks (kubectl) support an HTTP assertion, never substitute for one.

## Non-goals

- Not a fuzzer or generator — Schemathesis (once wired in) owns that; `contract`-tagged tests are informational.
- Not a mocking framework — every test exercises the real gateway edge, never a stubbed backend.
- Read-only against OpenAPI specs and backend code; write-only into `labs64.io-tests`. Never edit a module's spec or generated sources from here.
- Doesn't prescribe per-module unit-test conventions — those live in each module's own `AGENTS.md`.
