---
name: standards-compatibility
description: Use when changing an API, chart values key, secret key, queue name, event field, a default, a dependency, or a published version, or planning an upgrade, migration or rollback. Part of the Labs64.IO engineering standards.
---

# Standards: Compatibility & Regression Prevention

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Other modules, charts, environments, tenants and published versions are consumers: they keep working unchanged unless explicitly decided otherwise
- APIs are OpenAPI-first and additive (skill `openapi-first-change`); a breaking change needs an RFC
- Chart values keys, secret keys, queue names and event fields are contracts. A published version is never edited, only superseded
- The previous release stays installable: rollback is a pin, not a rebuild
- Consider upgrade order, migrations, rollback and mixed versions during a rollout
- A changed default is a behavior change: prefer opt-in, or say it in the release notes
- Add dependencies only for a clear benefit. Versions have one owner (guardrail 6) and move through Renovate
