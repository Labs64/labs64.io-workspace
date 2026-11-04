"""Tests for `{fill}` and `{grow:N}` in boxdiagram `.wire.txt` files (.agents/skills/boxdiagram).

`{fill}` gives a container's children equal shares of its spare main-axis space; `{grow:N}` gives
one box its own weight. Both map to JSON `grow` and survive `--fmt`, `--to-json` and `--to-wire`.

Run: pytest scripts/tests/test_boxdiagram_grow.py -q
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "boxdiagram"
BD = SKILL / "scripts" / "boxdiagram.py"
W = 46


def box(title, row):
    top = "+-- " + title + " "
    top += "-" * (W - 1 - len(top)) + "+"
    return [top, "| " + row.ljust(W - 4) + " |", "+" + "-" * (W - 2) + "+"]


def drawing(*bands):
    lines = []
    for title, row in bands:
        lines += box(title, row) + [""]
    return "\n".join(lines[:-1]) + "\n"


LEGEND = """
legend:
a = Alpha {service}
b = Beta {service}
c = Gamma {service}
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


def find(node, title):
    if node.get("title") == title:
        return node
    for c in node.get("children", []):
        hit = find(c, title)
        if hit:
            return hit
    return None


def grows(spec, title):
    band = find(spec, title)
    return {k["id"]: k.get("grow") for k in band["children"]}, band


def to_json(path):
    return json.loads(bd("--to-json", path).stdout)


def leaf_widths(svg_text):
    """Width of every leaf rect, keyed by its label text, from the generated SVG."""
    out = {}
    for m in re.finditer(r'<rect[^>]*width="(\d+)"[^>]*/>\s*<text[^>]*>([^<]+)</text>', svg_text):
        out[m.group(2)] = int(m.group(1))
    return out


def test_fill_gives_every_child_grow_1(wire):
    p = wire(drawing(("Band {fill}", "[a]  [b]  [c]")) + LEGEND)
    g, band = grows(to_json(p), "Band")
    assert g == {"a": 1, "b": 1, "c": 1}
    assert band["title"] == "Band"


def test_grow_on_a_legend_row_overrides_fill(wire):
    p = wire(drawing(("Band {fill}", "[a]  [b]  [c]")) + LEGEND.replace("Gamma {service}", "Gamma {service} {grow:0}"))
    g, _ = grows(to_json(p), "Band")
    assert g == {"a": 1, "b": 1, "c": 0}


def test_grow_in_a_drawn_box_and_on_a_container(wire):
    text = (
        "+-- Outer -------------------------------------+\n"
        "| +-- Inner {grow:2} --+  +------------------+ |\n"
        "| | [a]                |  | Beta {grow:1.5}  | |\n"
        "| +--------------------+  +------------------+ |\n"
        "+----------------------------------------------+\n"
    ) + LEGEND
    spec = to_json(wire(text))
    outer = find(spec, "Outer")
    inner = find(outer, "Inner")
    beta = next(c for c in outer["children"] if c.get("label") == "Beta")
    assert inner["grow"] == 2
    assert beta["grow"] == 1.5
    assert "{grow" not in beta["label"]


def test_fill_spreads_spare_width_equally(wire, tmp_path):
    # A wide second band makes the first band wider than its boxes; {fill} shares the rest.
    text = drawing(("Band {fill}", "[a]  [b]"), ("Wide", "[c]")) + LEGEND.replace(
        "Gamma {service}", "A label long enough to widen the whole diagram {service}")
    p = wire(text)
    bd(p)
    widths = leaf_widths((tmp_path / "d.svg").read_text())
    assert widths["Alpha"] == widths["Beta"]
    plain = wire(drawing(("Band", "[a]  [b]"), ("Wide", "[c]")) + LEGEND.replace(
        "Gamma {service}", "A label long enough to widen the whole diagram {service}"), "plain.wire.txt")
    bd(plain)
    assert widths["Alpha"] > leaf_widths((tmp_path / "plain.svg").read_text())["Alpha"]


def test_fmt_and_to_wire_keep_the_tags(wire):
    src = drawing(("Band {fill}", "[a]  [b]  [c]"), ("Weighted", "[a2]")) + LEGEND.replace(
        "Gamma {service}", "Gamma {service} {grow:3}") + "a2 = Alpha two {grow:2}\n"
    p = wire(src)
    before = to_json(p)
    bd("--fmt", p)
    text = p.read_text()
    assert "Band {fill}" in text
    assert "{grow:3}" in text and "{grow:2}" in text
    assert "{grow:1}" not in text  # implied by {fill}, not repeated
    assert to_json(p) == before


def test_grow_round_trips_from_json(tmp_path):
    spec = {"type": "col", "children": [
        {"type": "row", "title": "Band", "children": [
            {"id": "a", "label": "Alpha", "grow": 1},
            {"id": "b", "label": "Beta", "grow": 2},
        ]},
    ], "edges": []}
    j = tmp_path / "s.diagram.json"
    j.write_text(json.dumps(spec))
    wire_text = bd("--to-wire", "--compact", j).stdout
    assert "Band {fill}" in wire_text and "{grow:2}" in wire_text
    w = tmp_path / "s.wire.txt"
    w.write_text(wire_text)
    g, _ = grows(to_json(w), "Band")
    assert g == {"a": 1, "b": 2}


@pytest.mark.parametrize("tag, message", [
    ("{grow}", "needs a value"),
    ("{grow:-1}", "malformed tag"),  # a title turns '-' into a space
    ("{grow:x}", "number >= 0"),
    ("{fill:2}", "takes no value"),
])
def test_bad_title_tags_are_errors(wire, tag, message):
    r = bd(wire(drawing((f"Band {tag}", "[a]  [b]")) + LEGEND), check=False)
    assert r.returncode != 0
    assert message in r.stdout + r.stderr


def test_negative_grow_on_a_legend_row_is_an_error(wire):
    r = bd(wire(drawing(("Band", "[a]  [b]")) + LEGEND.replace("Beta {service}", "Beta {service} {grow:-1}")),
           check=False)
    assert r.returncode != 0
    assert "number >= 0" in r.stdout + r.stderr
