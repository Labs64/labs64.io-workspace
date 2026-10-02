# Labs64.IO Cockpit

Local, view-only web GUI over known Labs64.IO deployments: `local-k8s` (a k3d cluster, driven from
`labs64.io-helm-charts`) and `terraform-aws` (one AWS account per environment, `dev`/`qa`/`prod`,
driven from `labs64.io-devops`).

```bash
just cockpit          # from labs64.io-workspace/
# -> http://localhost:8850
```

- [`design/DESIGN.md`](design/DESIGN.md) explains why it's built this way: principles,
  architecture, the reconcile contract, status rules, caching.
- [`AGENTS.md`](AGENTS.md) explains how to work in this directory: layout, guardrails, where to
  make common changes.
