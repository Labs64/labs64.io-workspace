"""Labs64.IO Cockpit: a local, view-only GUI over known deployments.

Run with `just cockpit` from labs64.io-workspace/. See design/DESIGN.md.
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import probes, registry, store

HERE = Path(__file__).resolve().parent

# uvicorn's own logging config (see `just cockpit`) only sets up its own "uvicorn.*"
# loggers, not the root logger. Without this call, `probes`'s command-line logging
# would propagate to a handler-less root and never reach the terminal.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Labs64.IO Cockpit")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
templates = Jinja2Templates(directory=str(HERE / "templates"))


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """Static assets get no Cache-Control header from Starlette by default, so a browser
    can serve a stale, already-cached CSS/JS file on an ordinary reload without asking
    this server whether it changed. Every edit here would then need a hard refresh to
    show up; `no-store` makes it visible on the very next page load instead."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response

STATUS_TTL = 30  # seconds; shared by the list view, the detail view and its auto-refresh poll

# Kubernetes workload kinds a service in `reconcile.sh`'s output can be, and what each means.
# Shown as a tooltip since the distinction isn't obvious from the name alone.
KIND_EXPLAIN = {
    "Deployment": "Stateless workload; replicas are interchangeable.",
    "StatefulSet": "Stateful workload; each replica keeps a stable identity and its own storage.",
}


def _checked_at(data: dict) -> datetime.datetime:
    return datetime.datetime.fromisoformat(data["checkedAt"])


def _age_seconds(data: dict) -> float:
    return (datetime.datetime.now(datetime.timezone.utc) - _checked_at(data)).total_seconds()


def _row(entry: registry.Entry, data: dict) -> dict:
    return {
        **entry,
        **data,
        "checked_at_fmt": _checked_at(data).astimezone().strftime("%H:%M:%S"),
        "kind_display": registry.KIND_DISPLAY.get(entry["kind"], entry["kind"]),
    }


def _status(entry: registry.Entry, force: bool = False) -> dict:
    cached = None if force else store.read(entry["id"])
    if cached is None or _age_seconds(cached) >= STATUS_TTL:
        cached = probes.check(entry)
        store.write(entry["id"], cached)
    return _row(entry, cached)


def _status_view(entry: registry.Entry) -> dict:
    """Whatever `reconcile.sh` last reported for this entry, read straight off disk.
    This never triggers a fresh run. GET routes render this, so browsing the list or a
    deployment's page is never blocked on a subprocess, however slow that kind's own
    check is or however stale the cache has gone."""
    cached = store.read(entry["id"])
    if cached is None:
        return {
            **entry,
            "status": "unknown",
            "checked_at_fmt": "never",
            "issues": [],
            "services": [],
            "actions": [],
            "kind_display": registry.KIND_DISPLAY.get(entry["kind"], entry["kind"]),
        }
    return _row(entry, cached)


@app.get("/")
def index(request: Request):
    rows = [_status_view(e) for e in registry.load()]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "rows": rows,
            "kinds": registry.KINDS,
            "kind_display": registry.KIND_DISPLAY,
            "envs_by_kind": {k: registry.available_envs(k) for k in registry.KINDS},
        },
    )


@app.post("/add")
def add(kind: str = Form(...), env: str = Form("")):
    try:
        registry.add(kind, env.strip() or None)  # shows as unknown until explicitly refreshed
    except ValueError:
        pass  # PoC: an invalid submission just leaves the row missing, no error page
    return RedirectResponse("/", status_code=303)


@app.post("/deployment/{entry_id}/refresh")
def refresh_list(entry_id: str):
    entry = registry.get(entry_id)
    if entry:
        _status(entry, force=True)
    return RedirectResponse("/", status_code=303)


@app.get("/deployment/{entry_id}")
def detail(request: Request, entry_id: str):
    entry = registry.get(entry_id)
    if not entry:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"row": _status_view(entry), "ttl": STATUS_TTL, "kind_explain": KIND_EXPLAIN},
    )


@app.post("/deployment/{entry_id}/detail-refresh")
def detail_refresh(entry_id: str):
    entry = registry.get(entry_id)
    if entry:
        _status(entry, force=True)
    return RedirectResponse(f"/deployment/{entry_id}", status_code=303)


@app.get("/api/deployment/{entry_id}/status")
def api_status(entry_id: str):
    """Polled by detail.html's auto-refresh toggle; serves the on-disk cache,
    refilling it only once it's gone stale, so polling doesn't itself trigger a
    subprocess storm."""
    entry = registry.get(entry_id)
    if not entry:
        return {"error": "not found"}
    return _status(entry)


@app.post("/deployment/{entry_id}/action/{action_id}")
def run_action(request: Request, entry_id: str, action_id: str):
    entry = registry.get(entry_id)
    if not entry:
        return RedirectResponse("/", status_code=303)
    row = _status(entry)
    action = next(
        (a for a in row.get("actions", []) if a["id"] == action_id and a["type"] == "command"),
        None,
    )
    if action is None:
        return RedirectResponse(f"/deployment/{entry_id}", status_code=303)
    ok, output = probes.run_action(entry, action["command"])
    return templates.TemplateResponse(
        request,
        "action_result.html",
        {"entry_id": entry_id, "row": row, "action": action, "ok": ok, "output": output},
    )
