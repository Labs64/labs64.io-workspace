# Labs64.IO Ecosystem: Engineering Standards

The baseline for every module, library, chart, workflow, script and document in the ecosystem. It applies to new work, enhancements, refactoring and architectural changes.

The objective is production-grade software that is reliable, secure, resilient, performant, maintainable, scalable and cost-efficient, without unnecessary complexity.

**How this fits with the other guidance:** the guardrails in [`AGENTS.md`](AGENTS.md) are non-negotiable and win over anything here. A module's own `AGENTS.md` adds what is specific to it. Sections 2 to 12 say what good looks like; every change is judged in [section 13](#13-quality-bar-and-definition-of-done).

## 1. Core Engineering Principles

Weigh these in every engineering decision, in proportion to the component's criticality:

1. **Reliability**: predictable behavior and stable operation
2. **Security**: secure by design and by default
3. **Resilience**: graceful handling of failure, and recovery
4. **Performance**: efficient use of resources, responsive systems
5. **Compatibility**: backward compatibility and no regressions
6. **Observability**: measurable, diagnosable, monitorable
7. **Maintainability**: simple, modular, consistent
8. **Cost efficiency**: the right balance between requirements and running costs

## 2. Reliability, Resilience & High Availability

- Design for failure: dependencies, networks and infrastructure will become unavailable
- Give every outbound call a timeout and bounded retries with backoff; use circuit breakers where a slow dependency could cascade
- Degrade visibly: a down broker, cache, IdP or policy service must show in metrics and logs, never as silently wrong data
- Be safe with more than one replica, across rolling updates and restarts; add no single point of failure where high availability is required
- Prevent data loss, corruption and inconsistent states during failure
- Make any operation that can be retried idempotent
- Liveness says the process works and never depends on another system. Readiness says this pod should get traffic: fail it only for what taking the pod out actually helps, because a shared dependency's outage would otherwise take out every pod at once

## 3. Performance & Scalability

- Nothing grows without bound per request or per tenant: queues, caches, logs, retries, result sets
- Consider latency, throughput, concurrency and limits on hot paths; avoid needless blocking, allocation and N+1 queries
- Scale horizontally where appropriate, and keep HPA headroom honest against pod requests and limits
- Apply backpressure instead of accepting work that can't be finished
- One tenant must not be able to use up what others need: per-tenant quotas and fair shares where one tenant can realistically exhaust a shared resource
- Avoid premature optimization: measure, then fix the real bottleneck

## 4. Security by Design

- Least privilege and secure defaults; a default that is only safe locally must be set by the local stack, not the product
- **Fail closed** when authentication, authorization or redaction can't be established. The one deliberate exception: a license or entitlement check never drops an audit event
- The gateway removes caller-supplied `X-Auth-*` headers and creates the trusted context. Tenant comes from that context or verified domain state, never from a payload (see *Service-to-service communication* in `AGENTS.md`)
- Validate all external input, and never build a query, path or import from it: bind values, choose names from an allowlist
- Secrets live in environment variables or Kubernetes Secrets, never in values files, ConfigMaps or the repository
- Never log secrets or sensitive payloads. Exception messages count: parsers and stores quote the values they reject
- Public repositories are generic and never name a tenant (guardrail 10); no real customer data, and AWS only as a generic example. Ask: would a second tenant need a code change?
- Follow relevant OWASP guidance and address known vulnerabilities in dependencies

## 5. Compatibility & Regression Prevention

- Other modules, charts, environments, tenants and published versions are consumers: they keep working unchanged unless explicitly decided otherwise
- APIs are OpenAPI-first and additive (skill `openapi-first-change`); a breaking change needs an RFC
- Chart values keys, secret keys, queue names and event fields are contracts. A published version is never edited, only superseded
- The previous release stays installable: rollback is a pin, not a rebuild
- Consider upgrade order, migrations, rollback and mixed versions during a rollout
- A changed default is a behavior change: prefer opt-in, or say it in the release notes
- Add dependencies only for a clear benefit. Versions have one owner (guardrail 6) and move through Renovate

## 6. Distributed Systems & Messaging

- Assume at-least-once delivery, never exactly-once: consumers are idempotent, keyed on a stable event ID
- Acknowledge a message only after its outcome is stored; answer a producer only after the broker stored its message
- Poison goes to a dead-letter queue, never dropped. State retries, maximum age and replay explicitly
- Prevent retry storms and unbounded backlogs; a failing tenant or pipeline must not delay another
- Broker specifics stay behind a port (as AuditFlow's `MessageBroker`)
- Avoid synchronous dependencies between independently deployable services unless the caller truly needs the answer
- Calls between modules in one cluster use the target's Kubernetes Service, not the gateway

## 7. Kubernetes & Infrastructure

- Use the shared `chart-libs` and the conventions of the charts around you; no wrapper charts for third-party tools (guardrail 12)
- Set CPU and memory requests and limits from observed use, with startup, readiness and liveness probes
- Support graceful termination, connection draining and rolling updates
- Run as non-root (guardrail 3) with a read-only root filesystem where the runtime allows (writable paths as `emptyDir`), dropped capabilities and no mounted service account token unless needed
- NetworkPolicies state each path explicitly (guardrail 7); never open them wide to make something work, and say which hosts, ports and credentials a new dependency needs
- PodDisruptionBudgets, topology spread and extra replicas where availability requires them, not by reflex
- Public charts work on someone else's infrastructure; environment specifics belong in the deployment repository
- Keep configuration declarative and reproducible, with safe upgrades and rollbacks

## 8. Observability & Operability

- Observability is infrastructure-owned (guardrail 4): no OTel SDKs in services. Business signals go through a thin module-owned abstraction (AuditFlow's `BusinessTelemetry` is the reference); Java metrics through Micrometer
- Structured logs at meaningful levels, carrying the `X-Request-ID` and trace context
- Metric labels are bounded: per operation and tenant, never per customer, event or request
- Make errors, degraded states and resource exhaustion detectable, and alert on what someone would act on
- An operator can see a change failing and can undo it

## 9. Maintainability & Architecture

- Follow the established architecture, technology choices and conventions; the smallest change that does the job, in the style of the code around it
- Keep module boundaries explicit, with loose coupling and clear ownership. Shared Java and Python code belongs in `labs64.io-commons`, only once it really is shared
- **Settled decisions stay settled unless an RFC reopens them.**
- Spikes and experiments are welcome on a branch or behind an off-by-default flag; these standards apply once something is meant to ship. A new technology comes in through an RFC
- Community code is never edition-aware (guardrail 11): commercial editions are additive, through extension points
- Keep a module to its purpose: a feature waits for a named consumer
- Prefer existing ecosystem capabilities and proven solutions over custom ones; add no abstraction, technology or dependency without a justified benefit
- One owner per value. Generated files are regenerated, never hand-edited. No dead configuration
- Update the `AGENTS.md`, README or runbook that describes a change in the same change, and record non-obvious decisions and their reasons

## 10. Data Integrity & Lifecycle

- Database per service (guardrail 9); persistence responsibilities are explicit
- Respect transaction boundaries and state consistency expectations
- Make schema changes backward-compatible where practical, with safe migrations and a rollback path; remember a store may lag the code writing to it
- Silently losing data is a defect: if a tolerance can drop a value, it is documented and can be turned into a failure
- Handle retention, cleanup, backup and restore explicitly, and know which store is the system of record

## 11. Testing & Quality Assurance

- A fix comes with the test that failed before it; moved behavior moves its test in the same change
- Prove things at the right level: unit and contract tests in the module (including its `AuthEnforcementContractTest`), black-box at the gateway edge with Robot Framework (module `tests/e2e/`, shared keywords in `labs64.io-tests`), and `just ci` for charts, scripts and workflows
- Keep logic where it can be tested, not in a workflow step or template
- Cover invalid input, failure paths and denial, not only success: another tenant's data, a missing scope, a dependency down. Test concurrency and idempotency where they apply
- A gate nobody tests reports "clean" forever: check that a new check can fail
- **A skipped test is not a passed test.** Integration tests skip themselves without Docker and look green, so report them as not run
- Never claim that a test or verification passed unless it was actually executed, and say what was not verified

## 12. Cost Efficiency & Trade-offs

- The simplest architecture that meets the requirements for the actual workload, not a hypothetical one
- Consider infrastructure, operations, licensing and maintenance costs
- Avoid needless services, replicas, storage, network traffic and background work; development environments should cost little while idle
- Justify expensive infrastructure or architectural complexity by its value
- Optimize the system as a whole rather than any one quality in isolation

## 13. Quality Bar and Definition of Done

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

## 14. Engineering Decision Rule

**Prefer the simplest production-grade solution that satisfies the requirements and these standards.**

- Do not sacrifice reliability, security, maintainability or compatibility for speed
- Do not overengineer for hypothetical scenarios
- When two concerns pull against each other, make the choice explicitly and write it in the pull request, with its impact on reliability, performance, scalability and cost
- If a requirement conflicts with these standards or can't be met, say so and propose an alternative before proceeding. When in doubt, ask
