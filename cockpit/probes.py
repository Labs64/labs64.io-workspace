"""Everything Cockpit knows about a deployment comes from running that repo's own
`just reconcile` as a subprocess, from inside that repo's own directory, the same
way an operator would run it by hand. Cockpit adds no adapter logic of its own and
writes nothing back into the target repo; the reach is one-directional (Cockpit ->
repo), never the other way, and the target repo has no idea Cockpit exists.

`just reconcile` returns a standardized JSON object (kind, env, checkedAt, status,
issues, actions) that the repo's own script produced, because that repo, not
Cockpit, knows what healthy means for its own resources. See design/DESIGN.md.
"""
from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
from pathlib import Path

from . import registry

TIMEOUT_SECONDS = 30

RECONCILE_ARGS = {
    "terraform-aws": lambda env: ["reconcile", env],
    "local-k8s": lambda env: ["reconcile"],
}

logger = logging.getLogger("cockpit.probes")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run(command: list[str], cwd: Path) -> tuple[int, str, str]:
    cmdline = shlex.join(command)
    logger.info("running %s (cwd=%s)", cmdline, cwd)
    started = time.monotonic()
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
        )
        logger.info(
            "finished %s (exit %d, %.1fs)", cmdline, result.returncode, time.monotonic() - started
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        logger.warning("not found %s (cwd=%s)", cmdline, cwd)
        return 127, "", f"repo not found at {cwd}"
    except subprocess.TimeoutExpired:
        logger.warning("timed out %s (after %ds)", cmdline, TIMEOUT_SECONDS)
        return 124, "", f"timed out after {TIMEOUT_SECONDS}s"


def _fallback(entry: registry.Entry, message: str) -> dict:
    """Used when `just reconcile` itself couldn't be run or didn't return valid
    JSON. This is Cockpit's own guess at a status, only for that narrow failure case."""
    return {
        "kind": entry["kind"],
        "env": entry.get("env"),
        "checkedAt": _now_iso(),
        "status": "red",
        "issues": [message],
        "services": [],
        "actions": [],
    }


def check(entry: registry.Entry) -> dict:
    repo_path = registry.resolve_repo_path(entry)
    args = RECONCILE_ARGS[entry["kind"]](entry.get("env"))
    code, out, err = _run(["just", *args], repo_path)
    if code != 0 and not out.strip():
        return _fallback(entry, err.strip() or f"just {' '.join(args)} failed (exit {code})")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        detail = (out + err).strip()[:500] or "(no output)"
        return _fallback(entry, f"just {' '.join(args)} did not return valid JSON: {detail}")
    data.setdefault("issues", [])
    data.setdefault("services", [])
    data.setdefault("actions", [])
    return data


def run_action(entry: registry.Entry, command: list[str]) -> tuple[bool, str]:
    """Runs one action a reconcile result declared (already validated by the caller
    to be a `type: command` entry from that same result's own `actions` list)."""
    repo_path = registry.resolve_repo_path(entry)
    code, out, err = _run(command, repo_path)
    return code == 0, (out + err).strip() or "(no output)"
