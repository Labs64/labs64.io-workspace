---
name: standards-maintainability
description: Use when designing or refactoring a module, deciding where shared code lives, adding an abstraction, technology or dependency, reopening a settled decision, or updating docs (AGENTS.md, README, runbook) alongside a change. Part of the Labs64.IO engineering standards.
---

# Standards: Maintainability & Architecture

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Follow the established architecture, technology choices and conventions; the smallest change that does the job, in the style of the code around it
- Keep module boundaries explicit, with loose coupling and clear ownership. Shared Java and Python code belongs in `labs64.io-commons`, only once it really is shared
- **Settled decisions stay settled unless an RFC reopens them.**
- Spikes and experiments are welcome on a branch or behind an off-by-default flag; these standards apply once something is meant to ship. A new technology comes in through an RFC
- Community code is never edition-aware (guardrail 11): commercial editions are additive, through extension points
- Keep a module to its purpose: a feature waits for a named consumer
- Prefer existing ecosystem capabilities and proven solutions over custom ones; add no abstraction, technology or dependency without a justified benefit
- One owner per value. Generated files are regenerated, never hand-edited. No dead configuration
- Update the `AGENTS.md`, README or runbook that describes a change in the same change, and record non-obvious decisions and their reasons
