---
name: standards-reliability
description: Use when writing or changing code, charts or config that must survive failure: outbound calls, timeouts, retries, circuit breakers, idempotency, readiness/liveness probes, replicas, rolling updates, restarts, or a dependency (broker, cache, IdP, policy service) going down. Part of the Labs64.IO engineering standards.
---

# Standards: Reliability, Resilience & High Availability

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Design for failure: dependencies, networks and infrastructure will become unavailable
- Give every outbound call a timeout and bounded retries with backoff; use circuit breakers where a slow dependency could cascade
- Degrade visibly: a down broker, cache, IdP or policy service must show in metrics and logs, never as silently wrong data
- Be safe with more than one replica, across rolling updates and restarts; add no single point of failure where high availability is required
- Prevent data loss, corruption and inconsistent states during failure
- Make any operation that can be retried idempotent
- Liveness says the process works and never depends on another system. Readiness says this pod should get traffic: fail it only for what taking the pod out actually helps, because a shared dependency's outage would otherwise take out every pod at once
