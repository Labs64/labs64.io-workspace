"""The registry: a minimal, bootstrap-only pointer per known deployment.

Cockpit stores only enough here to reach a deployment: which repo, which kind,
which environment. Everything else is read live from the deployment itself on
every view (see probes.py).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional, TypedDict

WORKSPACE = Path(__file__).resolve().parents[1]
# Under registry/ (store.py's own root, one status.json subfolder per id): one
# "registry" location, not a file and a directory of the same name in two places.
REGISTRY_PATH = Path(__file__).resolve().parent / "registry" / "deployments.json"

KINDS = ("terraform-aws", "local-k8s")

# Each kind has exactly one repo in this ecosystem (labs64.io-workspace's own sibling
# convention, ROOT := ".."), so repoPath is derived from kind, never asked for.
REPO_PATH_BY_KIND = {
    "terraform-aws": "../labs64.io-devops",
    "local-k8s": "../labs64.io-helm-charts",
}

# What a kind is called wherever it's shown. The internal kind string stays the key
# used everywhere else (registry/deployments.json, probes.py); this dict only changes
# the display, never the key.
KIND_DISPLAY = {
    "terraform-aws": "aws",
    "local-k8s": "local-k8s",
}


class Entry(TypedDict, total=False):
    id: str  # opaque, generated; for internal lookups/URLs only, never shown as-is
    label: str  # human-facing name, computed from kind + env, see _compute_label
    kind: str
    repoPath: str  # relative to WORKSPACE; derived from kind, see REPO_PATH_BY_KIND
    env: Optional[str]  # required for terraform-aws, absent for local-k8s


def available_envs(kind: str) -> list[str]:
    """Environments this kind actually supports, read from the repo's own layout
    rather than hardcoded, so a new environment shows up without touching Cockpit."""
    if kind != "terraform-aws":
        return []
    envs_dir = (WORKSPACE / REPO_PATH_BY_KIND[kind] / "terraform" / "environments").resolve()
    if not envs_dir.is_dir():
        return []
    return sorted(p.name for p in envs_dir.iterdir() if p.is_dir())


def _compute_label(kind: str, env: Optional[str]) -> str:
    if kind == "terraform-aws":
        return f"{env}-aws"
    if kind == "local-k8s":
        # There is exactly one local cluster in this ecosystem (helm-charts'
        # justfile ENV is the constant "local"); "dev" names the role it plays
        # (the helm-charts README's own "Local Development" deployment mode),
        # not a value read from anywhere.
        return "dev-local-k8s"
    return kind


def _dedupe_label(label: str, taken: set[str]) -> str:
    if label not in taken:
        return label
    n = 1
    while f"{label} ({n})" in taken:
        n += 1
    return f"{label} ({n})"


def load() -> list[Entry]:
    if not REGISTRY_PATH.exists():
        return []
    return json.loads(REGISTRY_PATH.read_text())


def save(entries: list[Entry]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(entries, indent=2) + "\n")


def get(entry_id: str) -> Optional[Entry]:
    return next((e for e in load() if e["id"] == entry_id), None)


def add(kind: str, env: Optional[str] = None) -> Entry:
    if kind not in KINDS:
        raise ValueError(f"Unknown kind: {kind}")
    if kind == "terraform-aws" and not env:
        raise ValueError("terraform-aws entries need an env")
    entries = load()

    label = _dedupe_label(_compute_label(kind, env), {e["label"] for e in entries})
    internal_id = uuid.uuid4().hex[:8]
    while any(e["id"] == internal_id for e in entries):  # astronomically unlikely, cheap to guard
        internal_id = uuid.uuid4().hex[:8]

    entry: Entry = {
        "id": internal_id,
        "label": label,
        "kind": kind,
        "repoPath": REPO_PATH_BY_KIND[kind],
        "env": env if kind == "terraform-aws" else None,
    }
    entries.append(entry)
    save(entries)
    return entry


def resolve_repo_path(entry: Entry) -> Path:
    """The repo's absolute path on disk, exactly as `just` recipes already resolve
    siblings from labs64.io-workspace (ROOT := ".." in the justfile)."""
    return (WORKSPACE / entry["repoPath"]).resolve()
