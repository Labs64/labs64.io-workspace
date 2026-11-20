---
name: standards-quality-bar
description: Use before calling any change done, when writing or reviewing a pull request description, when judging a change in review, or when two concerns pull against each other (speed vs reliability, cost vs availability) and a trade-off must be made explicit. Holds the Labs64.IO engineering principles, the quality-bar table every PR answers, the definition of done and the decision rule.
---

# Standards: Quality Bar and Definition of Done

The baseline for every module, library, chart, workflow, script and document in the ecosystem; it applies to new work, enhancements, refactoring and architectural changes. The guardrails in `AGENTS.md` are non-negotiable and win over anything here; a module's own `AGENTS.md` adds what is specific to it. The detailed standards per work area are the other `standards-*` skills.

## Core Engineering Principles

Weigh these in every engineering decision, in proportion to the component's criticality:

1. **Reliability**: predictable behavior and stable operation
2. **Security**: secure by design and by default
3. **Resilience**: graceful handling of failure, and recovery
4. **Performance**: efficient use of resources, responsive systems
5. **Compatibility**: backward compatibility and no regressions
6. **Observability**: measurable, diagnosable, monitorable
7. **Maintainability**: simple, modular, consistent
8. **Cost efficiency**: the right balance between requirements and running costs

## Quality Bar and Definition of Done

Before a change is called done it is judged against this table, and its pull request answers the rows that apply; the rest go in one line (`n/a: docs only`). A row is never skipped silently.

| Concern | The question |
| --- | --- |
| **Stability of the ecosystem** | Does everything that consumes this still work, unchanged? |
| **No regression** | Which test fails if this breaks again? |
| **Security** | Who can now do or see what they could not before, and does it fail closed? |
| **No network surprises** | What new connection does this open, and what does it need to reach? |
| **Performance** | What does this cost at load, and what grows without bound? |
| **HA and resilience** | What happens with two replicas, a rolling update, a restart, a dependency down? |
| **Data integrity** | Can this lose, duplicate or corrupt data, and is any loss visible? |
| **Observability** | How would an operator see this failing, and how would they undo it? |
| **Testability** | Is it proven at the right level, automatically? |
| **Maintainability** | Will the next person find and change it in one place? |
| **Cost** | What does this add to the running cost, and is it worth it? |

A change is done when:

- It works as requested, and existing functionality and contracts remain intact
- The repository's gates (`just ci`) and relevant tests were run and are green
- The system is left in a better or equal state, and what is deployed, documented and tested says the same thing. An intermediate state (flag, parallel run, held rollout) is fine when it is safe, documented and its next step is written down; nothing is left half-done silently
- No known critical security, reliability or performance issue is introduced
- Deployment, configuration, upgrade order and rollback are addressed where they apply
- Limitations, assumptions, remaining risks and anything not verified are stated

## Engineering Decision Rule

**Prefer the simplest production-grade solution that satisfies the requirements and these standards.**

- Do not sacrifice reliability, security, maintainability or compatibility for speed
- Do not overengineer for hypothetical scenarios
- When two concerns pull against each other, make the choice explicitly and write it in the pull request, with its impact on reliability, performance, scalability and cost
- If a requirement conflicts with these standards or can't be met, say so and propose an alternative before proceeding. When in doubt, ask
