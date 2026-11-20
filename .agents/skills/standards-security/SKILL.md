---
name: standards-security
description: Use when a change touches authentication, authorization, scopes, tenants, X-Auth-* headers, input validation, queries or paths built from input, secrets, logging of payloads, dependency vulnerabilities, or anything going into a public repository. Part of the Labs64.IO engineering standards.
---

# Standards: Security by Design

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Least privilege and secure defaults; a default that is only safe locally must be set by the local stack, not the product
- **Fail closed** when authentication, authorization or redaction can't be established. The one deliberate exception: a license or entitlement check never drops an audit event
- The gateway removes caller-supplied `X-Auth-*` headers and creates the trusted context. Tenant comes from that context or verified domain state, never from a payload (see *Service-to-service communication* in `AGENTS.md`)
- Validate all external input, and never build a query, path or import from it: bind values, choose names from an allowlist
- Secrets live in environment variables or Kubernetes Secrets, never in values files, ConfigMaps or the repository
- Never log secrets or sensitive payloads. Exception messages count: parsers and stores quote the values they reject
- Public repositories are generic and never name a tenant (guardrail 10); no real customer data, and AWS only as a generic example. Ask: would a second tenant need a code change?
- Follow relevant OWASP guidance and address known vulnerabilities in dependencies
