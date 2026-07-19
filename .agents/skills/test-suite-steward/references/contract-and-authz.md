# Contract-Driven Test Coverage & Drift Detection

Gatekeeper mechanism, preserved from the skill this one replaces. Treats each module's OpenAPI
spec — specifically its `x-labs64-auth` annotations — as the single source of truth for both
**what to test** and **what auth the test should expect**. Those same annotations already drive
Cerbos policy generation at the authproxy edge, so this reads the same contract the enforcement
layer reads, not a parallel guess at it.

## When to use this

- Before writing new tests for a module, to know exactly which operations exist and what their auth requirements are.
- Periodically (or after an OpenAPI spec changes) to catch drift.
- When asked to "scaffold authz tests" for a module.

## Workflow

1. **Locate the spec.** Canonical path is `<module>-api/src/main/resources/openapi/openapi-<module>*.yaml`,
   or `<module>-be/src/main/resources/openapi/` if the module hasn't split out an `-api`
   submodule yet (see the `openapi-first-change` skill). Never read `target/generated-*` — it's
   a build artifact, not the source.

2. **Extract the operation table.** For every path × method, record: `operationId`, and from
   `x-labs64-auth`: `public: true`, or `tenant: true` + `scopes: [...]`. Treat an operation with
   no `x-labs64-auth` block at all as ambiguous — stop and ask rather than assuming public or
   protected.

3. **Diff against `labs64.io-tests/tests/<module>/`.** Three checks, all matter:
   - **Coverage gap** — an operation in the spec with no corresponding test anywhere in the module's test files.
   - **Drift** — a hardcoded path literal in a `.resource` or `.robot` file (e.g. `/audit/publish`, `/payment-providers/${id}`) that doesn't match any path in the current spec, accounting for path params. Treat any hit here as a real finding, not a style nit.
   - **Same-resource scope asymmetry** — group operations by path prefix and compare their required scopes. When two operations on the *same resource* require *different* scopes (e.g. `GET /payment-providers` needs `payment-provider:read` but `GET /payment-providers/{id}` needs `payment-provider:write` because the detail view exposes secrets), the "lower" scope must be explicitly proven to be **denied** on the "higher" operation. This asymmetry is invisible in a per-operation coverage count — a suite can have a test for every operation and still never prove that read-can-list-but-not-view. A missing denial test here is a real gap: silently widening the detail op to accept the read scope would leak, and nothing else would catch it.

4. **Report before writing.** Present the gap/drift table to the user first. Don't silently rewrite tests — drift often means the test was guarding something real that moved, not something to delete.

5. **Scaffold or update `tests/<module>/authz.robot`** following the extraction rules below,
   matching the conventions in `labs64.io-tests/AGENTS.md` (gateway-edge base URLs,
   `Create Session With Scope` from `resources/common.resource`, the tag taxonomy in
   `labs64.io-tests/README.md`). Reuse the existing file's `Test Teardown` / one-test-case-per-scenario shape — don't invent a new layout per module.

6. **If this is a brand-new module, register it** — add it to the service matrix in
   `.github/workflows/regression-suite.yml` and to `README.md`'s repository-structure and P0
   coverage tables. Skipping this step means the tests exist but CI never runs them; nothing
   else in this workflow catches that omission.

## Extraction rules for `x-labs64-auth`

| Annotation | Test cases to ensure exist |
|---|---|
| `public: true` | One case asserting success with **no** Authorization header. For a public route that lives on a resource whose *other* verbs are protected, also assert it stays 200 when called *with* an unrelated-scope token — proving "public" isn't accidentally gated. |
| `tenant: true`, `scopes: [s1, ...]` | The full deny/allow matrix, one test case each: **(1)** unauthenticated → 401; **(2)** malformed/invalid credential → 401 (not 403 — proves the token is rejected *before* any Cerbos decision); **(3)** wrong scope — a valid token carrying a *different, unrelated* scope → 403; **(4)** no scope — a validly-signed token carrying *zero* scopes (mock-oidc `no-access` persona) → 403 (distinct from #3: proves an empty scope set doesn't fall through to a default grant); **(5)** correct scope — a token carrying exactly the required scope(s) → the spec's declared success status; **(6)** superset scope — a token carrying the required scope *plus* extra irrelevant ones → success (proves the edge's `contains`/OR match isn't accidentally an exact-set match that a legitimate multi-scope caller would fail). Cases 1–5 are mandatory; case 6 is expected wherever real callers hold broad tokens. |
| No `x-labs64-auth` present | Flag as ambiguous; ask the module owner or check the backend's security config directly before writing a test that assumes an answer. |

Mint scope-specific tokens via `Create Session With Scope` (`resources/common.resource`), which
calls the local `mock-oidc` provider — it echoes any non-persona `scope` value verbatim into the
JWT (so a wrong-scope test can request precisely the scope that must fail), while the named
`no-access` persona yields a validly-signed token with an empty scope set for case #4, and
passing multiple space-separated scopes to one call covers case #6.

## Optional: local-k8s log corroboration

For the auth/authz path only, a test can *additionally* confirm the edge actually made the
decision it appears to have made (authproxy Cerbos decision log) and that an allowed request was
actually *delivered* past the gateway (backend log, matched on a per-event `correlationId` where
the module's schema has one). This is a deliberate, narrow exception to the suite's "gateway
edge only, no kubectl" rule — see `labs64.io-tests/AGENTS.md` "Local-only pod-log
corroboration". Rules if you add these:

- Tag the case `local-k8s-only` and call `Skip Unless Local Kubernetes` first, so it skips
  cleanly (never fails) in CI and anywhere the pinned local k3d context isn't active.
- It is *corroborating, never primary* — the paired HTTP-status case from the matrix above is
  still the actual contract check. Never replace an HTTP assertion with only a log assertion.
- If the module's request schema has no client-supplied correlation identifier (unlike
  AuditFlow's `correlationId`), don't force a backend-delivery check — a check that can't be
  attributed to one specific test call is worse than no check. Corroborating only the edge's
  Cerbos decision log is still meaningful on its own.
- Don't extend this pattern to ordinary functional tests; it exists only where the enforcement
  point and delivery effect are otherwise invisible to a black-box client.

## Non-goals

- Not a fuzzer or property-based generator — that's Schemathesis's job (once wired in); tests
  tagged `contract` are informational, not this workflow's output.
- Not a mocking framework — every generated test exercises the real gateway edge, never a
  stubbed backend.
- Read-only against OpenAPI specs and backend code; write-only into `labs64.io-tests`. Never
  edit a module's spec or generated sources from here.
