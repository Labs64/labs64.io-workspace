# AGENTS.md — Cockpit

This file is for how to work in this directory. See `README.md` for what Cockpit is and
`design/DESIGN.md` for why it's built this way.

## Layout

```
README.md         # what Cockpit is, quickstart
AGENTS.md         # this file
design/           # why it's built this way (DESIGN.md, architecture.svg)
app.py            # FastAPI routes
registry.py       # registry/deployments.json + id/label computation
probes.py         # runs `just reconcile` in each kind's own repo, parses its JSON
store.py          # on-disk status cache: registry/<id>/status.json
templates/        # Jinja2, server-rendered, no build step
static/           # plain CSS + a couple of small inline-scoped scripts, no framework
```

Everything Cockpit persists is under one `registry/` folder (gitignored): the list of known
deployments in `registry/deployments.json`, each one's last status in its own
`registry/<id>/status.json` subfolder. One location, not a file and a same-named directory
split across two places.

Each kind's own repo provides the other half of this: `scripts/reconcile.sh` + a `just reconcile`
recipe (`labs64.io-devops`, `labs64.io-helm-charts`) that prints the standardized status JSON
`probes.py` consumes. That script is not part of this directory; see `design/DESIGN.md`'s "Reach".

## Guardrails

1. **No adapter logic here.** Cockpit runs exactly one command per kind (`probes.py`'s
   `RECONCILE_ARGS`: `just reconcile <env>` / `just reconcile`) and parses its JSON. Any logic
   about what "healthy" means for a kind's resources belongs in that repo's own
   `scripts/reconcile.sh`, never reimplemented or guessed at here.
2. **`registry/deployments.json` holds bootstrap pointers only** (`id`, `label`, `kind`,
   `repoPath`, `env`). Live results belong only under that same id's own `registry/<id>/`
   subfolder (`store.py`), never inside `deployments.json` itself.
3. **The reach is one-directional: Cockpit -> repo.** Never write into a target repo, and never
   assume a target repo knows Cockpit exists.
4. **An action is exactly the argv the reconcile JSON declared.** `probes.run_action` executes a
   `type: command` action's `command` list verbatim (no shell string building, no reconstruction);
   the repo's own script is the only thing that decides what's runnable.
5. **Stay dependency-light.** FastAPI + Jinja2 + Uvicorn (`requirements.txt`) only, no frontend
   build step, no SPA framework. Server-rendered HTML plus small inline `<script>` blocks where
   needed, as in `templates/index.html`.
6. **Environments and repo paths are read from the target repo's own layout**
   (`REPO_PATH_BY_KIND`, `available_envs`), never hardcoded as a list. A new environment directory
   should show up without a Cockpit change.
7. **GUI copy stays user-facing.** No internal mechanics in on-page text: not the repo it's
   shelling into, not the id/label format, not caching details. Say what the person can do, not
   how the tool does it.
8. **Browsing never triggers a reconcile.** `GET /` and `GET /deployment/{id}` render `app.py`'s
   `_status_view`, the on-disk cache as-is, never `probes.check()`, so opening a page is never
   blocked on a subprocess; an entry with no cache yet shows `unknown` rather than forcing a check.
   Only an explicit action (a Refresh button, or the detail page's auto-refresh poll) may call
   `probes.check()` (`_status`).
9. **Every one of those explicit actions shows a spinner while it's in flight.** A form submit
   (refresh, running a declared action) gets one from `static/app.js`'s generic `btn-form` submit
   handler; the auto-refresh poll gets one from `detail.html`'s own `poll()`. Add to both, not just
   one, if a new kind of long-running call is added; see `design/DESIGN.md`'s Responsiveness
   principle.
10. **Every call to an external tool is logged with its full command line.** `probes._run` is the
    one place Cockpit shells out from. Log a new kind of external call there, not at its caller,
    so nothing bypasses it.

## Build, run, test

```bash
just cockpit   # from labs64.io-workspace/; installs deps, starts uvicorn on :8850
```

## Where to make common changes

| Goal | Where |
|---|---|
| Add or change a kind | `registry.py` (`REPO_PATH_BY_KIND`, `_compute_label`) + `probes.py` (`RECONCILE_ARGS`) + that kind's own `scripts/reconcile.sh` |
| Change what counts as yellow, or what actions are offered | that kind's own `scripts/reconcile.sh`, never in this directory |
| Change what the list or detail page shows | `templates/index.html`, `templates/detail.html` |
| Change caching behaviour | `store.py`, `STATUS_TTL` in `app.py` |
| Change what triggers a fresh reconcile | `app.py`: `_status_view` (read-only) vs. `_status` (may run `probes.check()`) |
| Design rationale, principles, architecture | `design/DESIGN.md` |
