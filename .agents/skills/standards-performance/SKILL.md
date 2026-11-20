---
name: standards-performance
description: Use when touching hot paths, queues, caches, result sets, retries, HPA/resources, per-tenant limits or quotas, backpressure, or anything that could grow without bound per request or per tenant. Part of the Labs64.IO engineering standards.
---

# Standards: Performance & Scalability

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Nothing grows without bound per request or per tenant: queues, caches, logs, retries, result sets
- Consider latency, throughput, concurrency and limits on hot paths; avoid needless blocking, allocation and N+1 queries
- Scale horizontally where appropriate, and keep HPA headroom honest against pod requests and limits
- Apply backpressure instead of accepting work that can't be finished
- One tenant must not be able to use up what others need: per-tenant quotas and fair shares where one tenant can realistically exhaust a shared resource
- Avoid premature optimization: measure, then fix the real bottleneck
