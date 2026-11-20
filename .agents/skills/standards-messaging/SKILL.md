---
name: standards-messaging
description: Use when working on message brokers, queues, event consumers or producers, dead-letter queues, retries and replay, acknowledgements, or calls between independently deployable services. Part of the Labs64.IO engineering standards.
---

# Standards: Distributed Systems & Messaging

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Assume at-least-once delivery, never exactly-once: consumers are idempotent, keyed on a stable event ID
- Acknowledge a message only after its outcome is stored; answer a producer only after the broker stored its message
- Poison goes to a dead-letter queue, never dropped. State retries, maximum age and replay explicitly
- Prevent retry storms and unbounded backlogs; a failing tenant or pipeline must not delay another
- Broker specifics stay behind a port (as AuditFlow's `MessageBroker`)
- Avoid synchronous dependencies between independently deployable services unless the caller truly needs the answer
- Calls between modules in one cluster use the target's Kubernetes Service, not the gateway
