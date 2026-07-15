---
name: gatekeeper
description: Use when adding, auditing, or updating the auth/authz or contract-coverage test matrix for any Labs64.IO module in labs64.io-tests. Triggers include "add tests for X module", "check test coverage against the OpenAPI spec", "does our test suite match the contract", "scaffold authz tests", "why did an endpoint change break tests silently".
---

# Gatekeeper — Contract-Driven Test Coverage & Drift Detection

## Overview

`labs64.io-tests` is a black-box regression suite. Its biggest failure mode isn't missing tests — it's tests that quietly stop matching the real API. This exact thing happened before this skill existed: the auditflow and payment-gateway suites asserted against endpoints (`GET /events`, `GET /health`, `GET /payment-methods`) that were never in the OpenAPI contract, and had been silently wrong for a long time because nothing cross-checked test code against the spec.

Gatekeeper treats each module's OpenAPI spec — specifically its `x-labs64-auth` annotations — as the single source of truth for both **what to test** and **what auth the test should expect**. Those same annotations already drive Cedar policy generation at the authproxy edge, so this skill is reading the same contract the enforcement layer reads, not a parallel guess at it.

## When to use this

- Before writing new tests for a module, to know exactly which operations exist and what their auth requirements are.
- Periodically (or after an OpenAPI spec changes) to catch drift: tests referencing paths/verbs no longer in the spec, or new operations with no test coverage at all.
- When asked to "scaffold authz tests" for a module.

## Workflow

1. **Locate the spec.** Canonical path is `<module>-api/src/main/resources/openapi/openapi-<module>*.yaml`, or `<module>-be/src/main/resources/openapi/` if the module hasn't split out an `-api` submodule yet (see the `openapi-first-change` skill). Never read `target/generated-*` — it's a build artifact, not the source.

2. **Extract the operation table.** For every path × method, record: `operationId`, and from `x-labs64-auth`: `public: true`, or `tenant: true` + `scopes: [...]`. Treat an operation with no `x-labs64-auth` block at all as ambiguous — stop and ask rather than assuming public or protected.

3. **Diff against `labs64.io-tests/tests/<module>/`.** Two checks, both matter:
   - **Coverage gap** — an operation in the spec with no corresponding test anywhere in the module's test files.
   - **Drift** — a hardcoded path literal in a `.resource` or `.robot` file (e.g. `/audit/publish`, `/payment-providers/${id}`) that doesn't match any path in the current spec, accounting for path params. This is the bug class described above; treat any hit here as a real finding, not a style nit.

4. **Report before writing.** Present the gap/drift table to the user first. Don't silently rewrite tests — drift often means the test was guarding something real that moved, not something to delete.

5. **Scaffold or update `tests/<module>/authz.robot`** following the extraction rules below, matching the file structure and conventions already in `labs64.io-tests/AGENTS.md` (gateway-edge base URLs, `Create Session With Scope` from `resources/common.resource`, the tag taxonomy in `labs64.io-tests/README.md`). Reuse the existing file's `Suite Teardown` / one-test-case-per-scenario shape — don't invent a new layout per module.

## Extraction rules for `x-labs64-auth`

| Annotation | Test cases to ensure exist |
|---|---|
| `public: true` | One case asserting success with **no** Authorization header. |
| `tenant: true`, `scopes: [s1, ...]` | Unauthenticated → 401. Malformed/invalid credential → 401. A token minted with a scope **other than** any required one → 403. A token minted with the exact required scope(s) → the spec's declared success status. |
| No `x-labs64-auth` present | Flag as ambiguous; ask the module owner or check the backend's security config directly before writing a test that assumes an answer. |

Mint scope-specific tokens via `Create Session With Scope` (`resources/common.resource`), which calls the local `mock-oidc` provider — it echoes any non-persona `scope` value verbatim into the JWT, so a wrong-scope test can request precisely the scope that must fail.

## Non-goals

- Not a fuzzer or property-based generator — that's Schemathesis's job (tests tagged `contract` are informational, not this skill's output).
- Not a mocking framework — every generated test exercises the real gateway edge, never a stubbed backend.
- Read-only against OpenAPI specs and backend code; write-only into `labs64.io-tests`. Never edit a module's spec or generated sources from here.
