"""Tests for comments in boxdiagram `.wire.txt` / JSON specs (.agents/skills/boxdiagram).

Comments never change the SVG, survive `--fmt`, and map to `_comment` / `_notes` / `_orphans` in JSON.

Run: pytest scripts/tests/test_boxdiagram_comments.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "boxdiagram"
BD = SKILL / "scripts" / "boxdiagram.py"

BASE = """\
+-- Backend ---+
| [api] [jobs] |
+--------------+

legend:
api  = API {service}
jobs = Jobs {queue}

edges:
api -> jobs : enqueue
"""

COMMENTED = """\
// free note
//@ diagram: Ops overview.
//@ diagram: One screen wide.

+-- Front ---+   +-- Backend ---+
| [web]      |   | [api] [jobs] |
+------------+   +--------------+

legend:
//@ api: Keep left of jobs.
web  = Web {client}
api  = API {service}
jobs = Jobs {queue}

edges:
//@ "Backend": bounded context
//@ api -> jobs: async on purpose
// trailer note
api -> jobs : enqueue
"""


def bd(*args, check=True):
    r = subprocess.run([sys.executable, str(BD), *map(str, args)], capture_output=True, text=True)
    if check:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


@pytest.fixture
def wire(tmp_path):
    def make(text, name="d.wire.txt"):
        p = tmp_path / name
        p.write_text(text)
        return p
    return make


def test_comments_do_not_change_the_svg(wire, tmp_path):
    bare = "\n".join(l for l in COMMENTED.split("\n") if not l.startswith("//"))
    plain, noted = wire(bare, "a.wire.txt"), wire(COMMENTED, "b.wire.txt")
    bd(plain)
    bd(noted)
    strip = lambda p: (tmp_path / p).read_text().split("\n", 1)[1]  # first line names the source file
    assert strip("a.svg") == strip("b.svg")


def test_to_json_maps_comments(wire):
    spec = json.loads(bd("--to-json", wire(COMMENTED)).stdout)
    assert spec["_comment"] == "Ops overview.\nOne screen wide."
    assert spec["_notes"] == ["free note", "trailer note"]
    assert spec["edges"][0]["_comment"] == "async on purpose"
    flat = json.dumps(spec)
    assert '"_comment": "Keep left of jobs."' in flat
    assert '"_comment": "bounded context"' in flat
    assert "_orphans" not in spec


def test_title_of_the_root_container_means_diagram(wire):
    spec = json.loads(bd("--to-json", wire(BASE.replace("edges:", 'edges:\n//@ "Backend": whole thing'))).stdout)
    assert spec["_comment"] == "whole thing"


def test_fmt_is_idempotent_and_keeps_comments(wire):
    p = wire(COMMENTED)
    bd("--fmt", p)
    first = p.read_text()
    bd("--fmt", p)
    assert p.read_text() == first
    for needle in ("//@ diagram: Ops overview.", "//@ diagram: One screen wide.", "// free note",
                   "// trailer note", "//@ api: Keep left of jobs.", '//@ "Backend": bounded context',
                   "//@ api -> jobs: async on purpose"):
        assert needle in first


def test_wire_json_wire_round_trip(wire, tmp_path):
    p = wire(COMMENTED)
    bd("--fmt", p)
    j = tmp_path / "d.diagram.json"
    j.write_text(bd("--to-json", p).stdout)
    again = bd("--to-wire", "--compact", j).stdout
    assert again == p.read_text().rstrip("\n") + "\n" or json.loads(
        bd("--to-json", wire(again, "e.wire.txt")).stdout) == json.loads(j.read_text())


def test_unknown_target_is_kept_and_warns(wire):
    p = wire(BASE + "//@ ghost -> api: stale\n")
    r = bd("--check", "--strict", p, check=False)
    assert "ghost -> api" in r.stdout + r.stderr
    assert r.returncode != 0
    bd("--fmt", p)
    assert "//@ ghost -> api: stale" in p.read_text()


def test_malformed_comment_is_an_error(wire):
    r = bd(wire(BASE + "//@ no colon here\n"), check=False)
    assert r.returncode == 2 and "cannot parse comment line" in r.stderr


def test_json_comment_types_are_checked(tmp_path):
    p = tmp_path / "d.diagram.json"
    p.write_text(json.dumps({"children": [{"id": "a", "label": "A", "_comment": 5}]}))
    assert bd(p, check=False).returncode == 2
    p.write_text(json.dumps({"children": [{"id": "a", "label": "A", "_comment": "ok"}], "_notes": ["x"]}))
    bd(p)


def test_existing_examples_still_render_identically():
    bd("--check", "--strict", *(SKILL / "examples").glob("*.wire.txt"), *(SKILL / "examples").glob("*.diagram.json"))
