# Running and Auditing labs64.io-tests

## Running

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

robot --include smoke tests/                    # fast, every-PR subset
robot tests/auditflow/                          # one module, everything
robot tests/auditflow/authz.robot               # one file
robot --test "Publish With Correct Scope Is Allowed" tests/auditflow/authz.robot
robot --include p0-blocker tests/                # never-skipped guard tests
robot --include regression --exclude flaky tests/  # full nightly shape
robot --include auth tests/                      # auth/authz matrix only, cross-module
```

A running Labs64.IO stack reachable through its gateway edge is required — the local k3d cluster
(`just local-up` from `labs64.io-helm-charts/`) or an equivalent with `gateway.localhost` and
`mock-oidc.localhost` resolvable. Robot writes `output.xml`, `log.html`, `report.html` to the
current directory (or `--outputdir <dir>`) — **read `log.html` first** on any failure; it has
full request/response detail per keyword, which is almost always enough to diagnose without
re-running.

Targeting a different environment overrides base URLs via env vars (see
`resources/common.resource`); if `mock-oidc` isn't reachable there, `API_TOKEN` is a fallback for
tests that don't need a specific scope combination — the scope-matrix cases in `authz.robot`
always need `mock-oidc` itself, since they mint several distinct scope combinations per suite.

## CI shape

| Trigger | Scope | Gates merge? |
|---|---|---|
| Every PR | `smoke` per service (parallel) + `p0-blocker` | Yes |
| Nightly | `regression`, excluding `flaky` | No (informational) |
| Manual (`workflow_dispatch`) | Same as nightly | No |

Keep `smoke` fast and few — it's on the critical path for every PR. Full scope-matrix depth
belongs in `regression`, not `smoke`.

## Auditing suite health

Run this periodically, after a spec change, or when asked to "audit the test suite":

1. **Drift** — for each module, diff hardcoded paths in `.resource`/`.robot` files against the
   current OpenAPI spec (see `contract-and-authz.md`). Any mismatch is a real finding.
2. **Coverage gaps** — any spec operation with zero tests anywhere in the module's files.
3. **Same-resource scope asymmetry** — see `contract-and-authz.md`; this is the bug class a
   flat per-operation coverage count can't see.
4. **Cross-module consistency** — the same authentication-vs-authorization boundary (e.g.
   malformed-bearer → 401, no-scope → 403) should be asserted the same way in every module's
   `authz.robot` unless there's a documented reason one module differs. Divergence is usually an
   oversight, not a deliberate design choice — confirm before leaving it.
5. **Duplication** — a fast subset of a scenario appearing in both `smoke.robot` (tag `smoke`)
   and the full matrix in `authz.robot` (tag `regression`) is *intentional* (fast PR feedback vs.
   full nightly depth) and not a finding. Duplication *within* the matrix itself — two test cases
   in `authz.robot` proving the same deny/allow fact — is a finding; consolidate or clarify what
   each is actually proving.
6. **Flaky handling** — a genuinely flaky case gets the `flaky` tag (excluded from gating, still
   runs nightly) rather than deletion or a `Sleep`-based band-aid. Investigate root cause before
   quarantining; quarantine is a triage state, not a resolution.
7. **Maintainability smells** — repeated per-test `[Teardown]` boilerplate (hoist to a single
   `Test Teardown` suite setting); a keyword duplicated across two modules' `.resource` files
   that could live once in `common.resource`; every test missing both `smoke` and `regression`
   tags (required — see `README.md`'s tag taxonomy); README/AGENTS.md claims that no longer
   match the code (e.g. a tag documented as unused that a new test just adopted).

Report findings before rewriting — the same "report before writing" discipline as the
contract-diff workflow. A gap or a piece of duplication may be intentional; confirm before
touching it.
