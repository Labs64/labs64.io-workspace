---
name: standards-kubernetes
description: Use when editing Helm charts, chart-libs, Dockerfiles, Kubernetes manifests, resource requests/limits, probes, NetworkPolicies, PodDisruptionBudgets, pod security settings, or infrastructure configuration. Part of the Labs64.IO engineering standards.
---

# Standards: Kubernetes & Infrastructure

What good looks like in this work area, for every module, library, chart, workflow, script and document in the ecosystem. The guardrails in `AGENTS.md` win over anything here; a module's own `AGENTS.md` adds what is specific to it. Before calling the change done, judge it against the quality bar in the `standards-quality-bar` skill.

- Use the shared `chart-libs` and the conventions of the charts around you; no wrapper charts for third-party tools (guardrail 12)
- Set CPU and memory requests and limits from observed use, with startup, readiness and liveness probes
- Support graceful termination, connection draining and rolling updates
- Run as non-root (guardrail 3) with a read-only root filesystem where the runtime allows (writable paths as `emptyDir`), dropped capabilities and no mounted service account token unless needed
- NetworkPolicies state each path explicitly (guardrail 7); never open them wide to make something work, and say which hosts, ports and credentials a new dependency needs
- PodDisruptionBudgets, topology spread and extra replicas where availability requires them, not by reflex
- Public charts work on someone else's infrastructure; environment specifics belong in the deployment repository
- Keep configuration declarative and reproducible, with safe upgrades and rollbacks
