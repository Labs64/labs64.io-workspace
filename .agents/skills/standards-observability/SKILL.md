---
name: standards-observability
description: Use when adding or changing logs, metrics, traces, alerts, dashboards, business telemetry, or error and degraded-state handling that an operator must be able to see. Part of the Labs64.IO engineering standards.
---

# Standards: Observability & Operability

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Observability is infrastructure-owned (guardrail 4): no OTel SDKs in services. Business signals go through a thin module-owned abstraction (AuditFlow's `BusinessTelemetry` is the reference); Java metrics through Micrometer
- Structured logs at meaningful levels, carrying the `X-Request-ID` and trace context
- Metric labels are bounded: per operation and tenant, never per customer, event or request
- Make errors, degraded states and resource exhaustion detectable, and alert on what someone would act on
- An operator can see a change failing and can undo it
