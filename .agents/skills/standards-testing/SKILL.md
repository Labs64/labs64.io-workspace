---
name: standards-testing
description: Use when writing, fixing or reviewing tests, fixing a bug, adding a gate or CI check, or about to report that tests or verification passed. Part of the Labs64.IO engineering standards.
---

# Standards: Testing & Quality Assurance

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- A fix comes with the test that failed before it; moved behavior moves its test in the same change
- Prove things at the right level: unit and contract tests in the module (including its `AuthEnforcementContractTest`), black-box at the gateway edge with Robot Framework (module `tests/e2e/`, shared keywords in `labs64.io-tests`), and `just ci` for charts, scripts and workflows
- Keep logic where it can be tested, not in a workflow step or template
- Cover invalid input, failure paths and denial, not only success: another tenant's data, a missing scope, a dependency down. Test concurrency and idempotency where they apply
- A gate nobody tests reports "clean" forever: check that a new check can fail
- **A skipped test is not a passed test.** Integration tests skip themselves without Docker and look green, so report them as not run
- Never claim that a test or verification passed unless it was actually executed, and say what was not verified
