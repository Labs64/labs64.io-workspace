"""On-disk cache of each deployment's last reconcile result. One JSON file per
entry, in its own gitignored subfolder (cockpit/registry/<id>/status.json). It is
the only cache; freshness is judged from the file's own `checkedAt`.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "registry"


def _path(entry_id: str) -> Path:
    return ROOT / entry_id / "status.json"


def read(entry_id: str) -> dict | None:
    path = _path(entry_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def write(entry_id: str, data: dict) -> None:
    path = _path(entry_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
