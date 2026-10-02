# Labs64.IO Cockpit

Local, view-only web GUI over known Labs64.IO deployments: `local-k8s` (a k3d cluster, driven from
`labs64.io-helm-charts`) and `terraform-aws` (one AWS account per environment, `dev`/`qa`/`prod`,
driven from `labs64.io-devops`). This covers why Cockpit is built this way; see `../README.md`
for what it is and `../AGENTS.md` for how to work in this directory.

## Principles

1. **CLI first.** Every deployment already works fully through its own tools (`just`,
   `terraform`, `kubectl`, `helm`, `aws`). Cockpit is a pure aggregator on top, never required.
2. **No cockpit-specific data in deployments.** A deployment repo has no idea Cockpit exists;
   Cockpit only runs that repo's own `just` recipes and reads their output.
3. **No extra infrastructure.** No cockpit server, login system, or role database. AWS IAM, the
   kube context, and the Terraform state lock remain the only source of who-can-do-what.
4. **Reconcile, not descriptor-driven, for now.** Cockpit derives what it shows from live state,
   nothing is written back into a deployment.
5. **Responsiveness.** Viewing the list or a deployment's page renders straight from the on-disk
   cache; browsing never blocks on a subprocess. `reconcile.sh` only runs from an explicit action
   (a Refresh button, or the detail page's opt-in auto-refresh poll).

## Architecture

![Cockpit architecture](architecture.svg)

- Blue boxes (Cockpit, its status cache, and both adapters) are what Cockpit itself added;
  everything else (git checkouts, Helm releases, the k3d cluster, the AWS account's own
  resources) already existed and is unchanged by it.
- Solid connectors are in scope and built, including Cockpit itself and its on-disk status cache.
- Dashed connectors are Cockpit's own connectors into each adapter: built, like everything else
  here, but each one is a live probe run only when triggered (below), not a standing integration.
- Each adapter prints its JSON to stdout only (`reconcile.sh`'s `stdout JSON`, above).
- Cockpit itself writes what it gets back into `registry/<id>/status.json` and reads that same
  file for every page view (see Caching, below).
- Cockpit calls each adapter directly; each deployment kind's adapter belongs entirely to that
  kind's own repo.

## Registry: the only thing Cockpit stores

`cockpit/registry/deployments.json` (gitignored: per-checkout local state, not shared config).
One entry per known deployment, bootstrap-only. `id` is an opaque, generated key for internal
lookups and URLs only, never typed by the user and never shown as-is; `label` is a human-readable
name computed from `kind` and `env`, kept unique across entries, and what the UI actually displays:

```json
{"id": "a1b2c3d4", "label": "dev-aws",       "kind": "terraform-aws", "repoPath": "../labs64.io-devops", "env": "dev"}
{"id": "e5f6a7b8", "label": "dev-local-k8s", "kind": "local-k8s",     "repoPath": "../labs64.io-helm-charts", "env": null}
```

This file and the per-deployment status cache (`registry/<id>/status.json`, see "Caching", below)
are both under `registry/`: one persisted location, not a file and a same-named directory split
across two places.

## Reach: one-directional, through each repo's own `reconcile`

Cockpit has no adapter code. Each kind's own repo has a small `scripts/reconcile.sh`, exposed as
`just reconcile <env>` (`terraform-aws`, in `labs64.io-devops`) or `just reconcile` (`local-k8s`,
in `labs64.io-helm-charts`), that prints one standardized JSON object to stdout and nothing else.
Cockpit's entire job is running that one command, with its working directory set to the repo
(`registry.repoPath`, resolved as a sibling of `labs64.io-workspace/`, the same convention the
rest of the ecosystem uses), and reading its output as-is:

```json
{
  "kind": "terraform-aws",
  "env": "dev",
  "checkedAt": "2026-09-29T12:00:00Z",
  "status": "yellow",
  "issues": ["pods not healthy in labs64io: checkout-be-xyz"],
  "services": [
    {"name": "checkout-be", "kind": "Deployment", "namespace": "labs64io", "ready": 1, "desired": 2}
  ],
  "actions": [
    {"id": "modules-status", "label": "Module status", "type": "command", "command": ["just", "modules-status", "dev"]},
    {"id": "grafana", "label": "Grafana", "type": "browser", "url": "http://gateway.localhost/grafana/"}
  ]
}
```

The repo's own script decides `status`, `issues` and `services`; it has real access to its own
resources (`kubectl -o json`, `helm list`, `aws sts get-caller-identity`) and knows what healthy
means for them. `services` is one entry per Kubernetes Deployment/StatefulSet the script finds in
the namespaces it already checks: `ready`/`desired` replica counts, not a health verdict. A
service short on replicas also shows up in `issues`. Cockpit falls back to a red status of its own
only if the command itself fails or doesn't return valid JSON.

The target repo never reaches back into Cockpit; it has no idea Cockpit's registry or process
exist.

Every such call is logged server-side with its full command line, working directory, and outcome
(exit code and duration, or why it didn't run). A `type: browser` action never goes through this
at all: it's a plain link the browser opens directly, with no backend call to log.

`reconcile.sh` never reads a secret value, by construction: `terraform-aws`'s only reads AWS
identity and `kubectl -o json` (pods, `ExternalSecrets`, `ClusterSecretStore`), never `terraform
show`/`output -json`, the one place `random_password` values in this repo's state would be
exposed (`labs64.io-devops/AGENTS.md` guardrail 2). Anything added to a `reconcile.sh` later
should keep that: read status, not secrets.

## Status: green / yellow / red

Decided entirely by the repo's own `reconcile.sh`, not by Cockpit:

- **Red** — the deployment isn't reachable at all (`labs64.io-devops`: AWS identity doesn't
  resolve; `labs64.io-helm-charts`: no cluster/namespace found).
- **Yellow** — reachable, but something looks wrong: unhealthy pods, an `ExternalSecret` or
  `ClusterSecretStore` not `Ready`, a Helm release not in `deployed` state, or (terraform-aws)
  the kube context not set up yet.
- **Green** — reachable, none of the above found.

Still a heuristic, not real drift detection against a descriptor; that stays deferred (see
"Explicitly out of scope", below). The heuristic is implemented in each repo's own script, which
can reach real structured state (`kubectl -o json`) rather than reading raw command output.

A deployment Cockpit has never checked shows a fourth, Cockpit-only state, **unknown** (grey),
rather than guessing at green/yellow/red; it clears the first time a check actually runs.

## Actions

`reconcile.sh`'s `actions` array is a menu the repo itself declares for its own kind; Cockpit
just renders it on the deployment's page, unchanged:

- **`type: "command"`** — a `just`/shell command (`["just", "modules-status", "dev"]`). Clicking it
  runs that exact command as a subprocess and shows its output on the page.
  Nothing is guessed or reconstructed; the array *is* the argv.
- **`type: "browser"`** — a `url`. Rendered as a plain link opening in a new tab (Grafana, the
  Traefik dashboard, ...); Cockpit never fetches or embeds it.

Adding or changing what shows up here is a one-line change in that repo's `reconcile.sh`; Cockpit
needs no update to pick up a new action.

## Caching

Each deployment's last `reconcile` result is written to its own gitignored subfolder:
`cockpit/registry/<id>/status.json`. The on-disk file *is* the cache.

The list and detail pages only ever read this file; they never call
`just reconcile` themselves, so opening either page is instant regardless of how slow a kind's own
check is. A deployment that has never been checked shows `unknown` until refreshed.

A fresh check comes only from an explicit trigger: the list view's per-row **Refresh**, the detail
page's **Refresh now**, or its auto-refresh toggle, which polls a small JSON endpoint
(`/api/deployment/<id>/status`) and re-runs `reconcile.sh` only once the cached result has gone
past 30 seconds; leaving a tab open with auto-refresh on doesn't itself trigger a subprocess
storm either.

## Getting started

```bash
just cockpit          # from labs64.io-workspace/
# -> http://localhost:8850
```

The port is in the devcontainer's explicit `forwardPorts` (`remote.autoForwardPorts` is off
ecosystem-wide, so an unlisted port would never reach the host browser). VS Code should offer
to open it; otherwise open the URL by hand or use the Ports tab. There is no separate CLI for
managing entries: the "Add deployment" form is on the page itself. Registering an environment
that isn't provisioned yet is fine: it shows as unreachable until it exists. Cockpit never
provisions or changes anything about how an environment is deployed.

## Explicitly out of scope for this PoC

- A full deployment descriptor: a declared, versioned shape for every tfvars/Helm-values option
  (not just status), diffed against live state to catch configuration drift rather than health
  issues. `reconcile.sh`'s `status`/`issues` are a cheap proxy for "is something wrong," not that.
- Editing, creating, or destroying deployments from the UI.
- Auth or multi-user anything: one local browser tab against one operator's own credentials,
  same access as running the CLI commands above by hand.
