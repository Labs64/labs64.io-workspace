---
name: standards-cost
description: Use when adding services, replicas, storage, network traffic, background work or infrastructure, or choosing between architectures where running cost matters. Part of the Labs64.IO engineering standards.
---

# Standards: Cost Efficiency & Trade-offs

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- The simplest architecture that meets the requirements for the actual workload, not a hypothetical one
- Consider infrastructure, operations, licensing and maintenance costs
- Avoid needless services, replicas, storage, network traffic and background work; development environments should cost little while idle
- Justify expensive infrastructure or architectural complexity by its value
- Optimize the system as a whole rather than any one quality in isolation
