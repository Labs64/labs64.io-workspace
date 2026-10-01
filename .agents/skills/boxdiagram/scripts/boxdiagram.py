#!/usr/bin/env python3
"""
boxdiagram - nested row/col/grid layout + orthogonal connector routing -> SVG.

Spec (JSON)
-----------
Every node is an object. Containers have "children"; leaves do not.

  type      "row" | "col" | "grid" | "box"   (default: "col" if it has children, else "box")
  id        unique id (needed for leaves that edges refer to)
  label     leaf text (\\n for multiple lines), "sub" = smaller second text
  style     leaf colour class: default | service | store | external | client | queue
  title     container title (drawn top-left, edges are kept away from it)
  cols      grid only: number of columns (children fill row by row)
  gap       space between children (px, default 40 - this is the routing channel)
  padding   container inner padding (px, default 20)
  align     cross-axis: stretch (default) | start | center | end
  justify   main-axis: start (default) | center | end | between
  grow      weight for taking extra main-axis space (row/col children)
  frame     containers: draw the border box? (default true, root: only if it has a title)

A container with "frame": false is purely structural: it still sizes and positions its
children (gap, padding, align, justify, grow, cols all still apply), but draws no border and
no title, and never blocks a connector's route the way a framed container's border does.
"gap": 0 and "padding": 0 are valid on any container, framed or not, and most useful on one
that's "frame": false: children can then sit flush against each other and against the box's
own outer edge, as if the wrapper weren't there at all except for the positions it assigns.

Top level is a node (the root) plus:
  edges: [{"from": id, "to": id, "label": str?, "from_side": left|right|top|bottom?,
           "to_side": ...?, "from_at": 0..1?, "to_at": ...?,
           "dashed": bool?, "arrow": "end"|"both"|"none"?}]
  transparent: bool   (no background rect)

"from_at"/"to_at" each require their "_side" to be given alongside them: they pin the exact
point along that side (0 = its first port, i.e. top-most on left/right or left-most on
top/bottom; 1 = its last), instead of leaving the router to choose among every port on every
side by cost. Ordinary routing already searches ports and sides jointly and is usually a
better choice; reach for "_at" only when you need one specific connector to land at an exact,
named point (matching a hand-specified layout, or forcing two routes to read as parallel).

All sizes are snapped to a 10px grid; connectors run on the same grid.
"""
import argparse
import heapq
import json
import math
import os
import sys
from collections import Counter, defaultdict
from xml.sax.saxutils import escape

G = 10  # grid unit in px
FONT_FAMILY = '"DejaVu Sans", Verdana, "Segoe UI", sans-serif'


def snap_up(v):
    return int(math.ceil(v / G - 1e-9)) * G


# ----------------------------------------------------------------------------- text
# Text is measured from a bundled advance-width table (DejaVu Sans, in em) instead of the
# installed fonts, so the same JSON yields byte-identical SVG on every machine.
_metrics = None


def text_w(s, size, bold=False):
    global _metrics
    if _metrics is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics.json")) as f:
                _metrics = json.load(f)
        except OSError:
            _metrics = {"regular": {}, "bold": {}}
    table = _metrics["bold" if bold else "regular"]
    return sum(table.get(ch, 0.62) for ch in s) * size


# ----------------------------------------------------------------------------- layout
def main_axis(sizes, gap, avail, justify, grows):
    n = len(sizes)
    used = sum(sizes) + gap * (n - 1)
    extra = max(0, (avail - used) // G)
    sizes = list(sizes)
    tot = sum(grows)
    if tot > 0 and extra > 0:
        shares = [int(extra * g / tot) for g in grows]
        rem = extra - sum(shares)
        idx = [i for i, g in enumerate(grows) if g > 0]
        k = 0
        while rem > 0:
            shares[idx[k % len(idx)]] += 1
            rem -= 1
            k += 1
        sizes = [s + sh * G for s, sh in zip(sizes, shares)]
        extra = 0
    gaps = [gap] * (n - 1)
    cur = 0
    if justify == "center":
        cur = (extra // 2) * G
    elif justify == "end":
        cur = extra * G
    elif justify == "between" and n > 1:
        base, rem = divmod(extra, n - 1)
        gaps = [gap + (base + (1 if i < rem else 0)) * G for i in range(n - 1)]
    out = []
    for i, s in enumerate(sizes):
        out.append((cur, s))
        cur += s + (gaps[i] if i < n - 1 else 0)
    return out


def cross_axis(nat, avail, align):
    if align == "start":
        return 0, nat
    if align == "end":
        return avail - nat, nat
    if align == "center":
        return ((avail - nat) // 2 // G) * G, nat
    return 0, avail


class Node:
    def __init__(self, spec, depth=0):
        self.spec = spec
        self.depth = depth
        self.children = [Node(c, depth + 1) for c in spec.get("children", [])]
        t = spec.get("type") or ("col" if "children" in spec else "box")
        if t not in ("box", "row", "col", "grid"):
            raise ValueError(f"unknown type {t!r}")
        self.type = t
        self.id = spec.get("id")
        self.label = spec.get("label", "")
        self.sub = spec.get("sub", "")
        self.title = spec.get("title", "")
        self.style = spec.get("style", "default")
        self.gap = snap_up(spec.get("gap", 40))
        self.pad = snap_up(spec.get("padding", 20))
        self.cols = max(1, int(spec.get("cols", 2)))
        self.align = spec.get("align", "stretch")
        self.justify = spec.get("justify", "start")
        self.grow = spec.get("grow", 0)
        self.frame = spec.get("frame", depth > 0 or bool(self.title))

    def top_inset(self):
        return self.pad + 30 if self.title else self.pad

    def measure(self):
        if self.type == "box":
            lines = self.label.split("\n") if self.label else []
            subs = self.sub.split("\n") if self.sub else []
            tw = max([text_w(l, 14, True) for l in lines] + [text_w(s, 11) for s in subs] + [0])
            self.nw = max(snap_up(tw + 28), 80)
            self.nh = max(snap_up(len(lines) * 18 + len(subs) * 15 + 20), 40)
            return
        ch = self.children
        for c in ch:
            c.measure()
        n = len(ch)
        if n == 0:
            iw = ih = 0
        elif self.type == "row":
            iw = sum(c.nw for c in ch) + self.gap * (n - 1)
            ih = max(c.nh for c in ch)
        elif self.type == "col":
            iw = max(c.nw for c in ch)
            ih = sum(c.nh for c in ch) + self.gap * (n - 1)
        else:
            cols = self.cols
            rows = math.ceil(n / cols)
            self.colw = [0] * cols
            self.rowh = [0] * rows
            for k, c in enumerate(ch):
                r, cc = divmod(k, cols)
                self.colw[cc] = max(self.colw[cc], c.nw)
                self.rowh[r] = max(self.rowh[r], c.nh)
            iw = sum(self.colw) + self.gap * (cols - 1)
            ih = sum(self.rowh) + self.gap * (rows - 1)
        tt = snap_up(text_w(self.title, 12, True) + 28) if self.title else 0
        self.nw = max(iw + 2 * self.pad, tt)
        self.nh = ih + self.pad + self.top_inset()

    def place(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        if self.type == "box" or not self.children:
            return
        ix, iy = x + self.pad, y + self.top_inset()
        iw, ih = w - 2 * self.pad, h - self.top_inset() - self.pad
        ch = self.children
        if self.type in ("row", "col"):
            horiz = self.type == "row"
            sizes = [c.nw if horiz else c.nh for c in ch]
            pos = main_axis(sizes, self.gap, iw if horiz else ih, self.justify, [c.grow for c in ch])
            cross = ih if horiz else iw
            for c, (off, sz) in zip(ch, pos):
                coff, csz = cross_axis(c.nh if horiz else c.nw, cross, self.align)
                if horiz:
                    c.place(ix + off, iy + coff, sz, csz)
                else:
                    c.place(ix + coff, iy + off, csz, sz)
        else:
            cp = main_axis(self.colw, self.gap, iw, "start", [1] * len(self.colw))
            rp = main_axis(self.rowh, self.gap, ih, "start", [1] * len(self.rowh))
            for k, c in enumerate(ch):
                r, cc = divmod(k, self.cols)
                (cx, cw), (ry, rh) = cp[cc], rp[r]
                xo, wsz = cross_axis(c.nw, cw, self.align)
                yo, hsz = cross_axis(c.nh, rh, self.align)
                c.place(ix + cx + xo, iy + ry + yo, wsz, hsz)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


# ----------------------------------------------------------------------------- routing
DX = [1, 0, -1, 0]  # east, south, west, north
DY = [0, 1, 0, -1]
SIDE_DIR = {"right": 0, "bottom": 1, "left": 2, "top": 3}


def seg_key(u, v):
    if u[1] == v[1]:
        return (min(u[0], v[0]), u[1], 0)
    return (u[0], min(u[1], v[1]), 1)


def rect_hits_seg(r, a, b, pad=0):
    rx0, ry0, rx1, ry1 = r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return not (x1 < rx0 or x0 > rx1 or y1 < ry0 or y0 > ry1)


def rects_hit(a, b, pad=0):
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


class Router:
    BEND, RING, CROSS, ALONG = 5, 2, 6, 8
    OVERLAP, TOUCH, PORTUSE, PORTADJ, OUTSIDE, UNREL = 30, 10, 20, 14, 4, 40

    def __init__(self, W, H, leaves, framed, titles, inner, anc):
        self.W, self.H = W, H
        self.anc = anc  # leaf id -> set of framed-container indexes containing it
        self.cont_lines = []
        self._hv = self._hh = frozenset()
        self.inner = inner  # root rect in grid units; routing outside it is discouraged
        self.blocked = set()
        self.boxes = {}
        self.leaf_px = []
        for n in leaves:
            x0, y0, x1, y1 = n.x // G, n.y // G, (n.x + n.w) // G, (n.y + n.h) // G
            self.boxes[n.id] = (x0, y0, x1, y1)
            self.leaf_px.append((n.x, n.y, n.x + n.w, n.y + n.h))
            for i in range(x0, x1 + 1):
                for j in range(y0, y1 + 1):
                    self.blocked.add((i, j))
        self.ring = set()
        for (x0, y0, x1, y1) in self.boxes.values():
            for i in range(x0 - 1, x1 + 2):
                for j in range(y0 - 1, y1 + 2):
                    if (i, j) not in self.blocked:
                        self.ring.add((i, j))
        self.title_px = []
        for (x, y, w, h) in titles:
            self.title_px.append((x, y, x + w, y + h))
            for i in range(int(math.floor((x - 4) / G)), int(math.ceil((x + w + 4) / G)) + 1):
                for j in range(int(math.floor((y - 4) / G)), int(math.ceil((y + h + 4) / G)) + 1):
                    if x - 4 <= i * G <= x + w + 4 and y - 4 <= j * G <= y + h + 4:
                        self.blocked.add((i, j))
        self.vlines, self.hlines, self.border_segs = set(), set(), set()
        self.border_px = []  # segments of framed containers in px
        for c in framed:
            x0, y0, x1, y1 = c.x // G, c.y // G, (c.x + c.w) // G, (c.y + c.h) // G
            cv, ch_ = set(), set()
            for j in range(y0, y1 + 1):
                cv.add((x0, j)); cv.add((x1, j))
            for i in range(x0, x1 + 1):
                ch_.add((i, y0)); ch_.add((i, y1))
            self.cont_lines.append((cv, ch_))
            for j in range(y0, y1 + 1):
                self.vlines.add((x0, j))
                self.vlines.add((x1, j))
            for i in range(x0, x1 + 1):
                self.hlines.add((i, y0))
                self.hlines.add((i, y1))
            for j in range(y0, y1):
                self.border_segs.add((x0, j, 1))
                self.border_segs.add((x1, j, 1))
            for i in range(x0, x1):
                self.border_segs.add((i, y0, 0))
                self.border_segs.add((i, y1, 0))
            px = (c.x, c.y, c.x + c.w, c.y + c.h)
            self.border_px += [((px[0], px[1]), (px[2], px[1])), ((px[0], px[3]), (px[2], px[3])),
                               ((px[0], px[1]), (px[0], px[3])), ((px[2], px[1]), (px[2], px[3]))]
        self.ports = {}
        for nid, (x0, y0, x1, y1) in self.boxes.items():
            self.ports[nid] = {
                "right": [((x1, j), 0) for j in range(y0 + 1, y1)],
                "bottom": [((i, y1), 1) for i in range(x0 + 1, x1)],
                "left": [((x0, j), 2) for j in range(y0 + 1, y1)],
                "top": [((i, y0), 3) for i in range(x0 + 1, x1)],
            }
        self.seg_use = Counter()
        self.vuse = Counter()
        self.port_use = Counter()
        self.lblock = Counter()

    # -- state helpers
    def is_blocked(self, v):
        return v in self.blocked or self.lblock.get(v, 0) > 0

    def free(self, v):
        return 0 <= v[0] <= self.W and 0 <= v[1] <= self.H and not self.is_blocked(v)

    def apply(self, path, sign):
        for a, b in zip(path, path[1:]):
            k = seg_key(a, b)
            self.seg_use[k] += sign
            if self.seg_use[k] <= 0:
                del self.seg_use[k]
            for v in (a, b):
                vk = (v, k[2])
                self.vuse[vk] += sign
                if self.vuse[vk] <= 0:
                    del self.vuse[vk]
        for p in (path[0], path[-1]):
            self.port_use[p] += sign
            if self.port_use[p] <= 0:
                del self.port_use[p]

    def block_rect(self, r, sign):
        for i in range(int(r[0] // G), int(math.ceil(r[2] / G)) + 1):
            for j in range(int(r[1] // G), int(math.ceil(r[3] / G)) + 1):
                self.lblock[(i, j)] += sign
                if self.lblock[(i, j)] <= 0:
                    del self.lblock[(i, j)]

    def port_pen(self, p):
        pen = 0
        if p in self.port_use:
            pen += self.PORTUSE
        for d in range(4):
            if (p[0] + DX[d], p[1] + DY[d]) in self.port_use:
                pen += self.PORTADJ
        return pen

    def step_cost(self, u, v, nd, pd):
        c = 1
        if pd != nd:
            c += self.BEND
        if v in self.ring:
            c += self.RING
        ix0, iy0, ix1, iy1 = self.inner
        if not (ix0 <= v[0] <= ix1 and iy0 <= v[1] <= iy1):
            c += self.OUTSIDE
        k = seg_key(u, v)
        if k in self.border_segs:
            c += self.ALONG
        horiz = nd in (0, 2)
        if (horiz and v in self._hv) or (not horiz and v in self._hh):
            c += self.UNREL
        elif (horiz and v in self.vlines) or (not horiz and v in self.hlines):
            c += self.CROSS
        if k in self.seg_use:
            c += self.OVERLAP
        if (v, 0) in self.vuse or (v, 1) in self.vuse:
            c += self.TOUCH
        return c

    @staticmethod
    def _pin(lst, at):
        """Narrow a side's candidate ports to the single one nearest fraction `at`
        (0 = the side's first port, 1 = its last), or return `lst` unchanged if `at`
        is None. Used for an edge's explicit from_at/to_at, never for ordinary routing."""
        if at is None or not lst:
            return lst
        idx = round(max(0.0, min(1.0, at)) * (len(lst) - 1))
        return [lst[idx]]

    # -- A*
    def route(self, a, b, fs=None, ts=None, fa=None, ta=None):
        bx0, by0, bx1, by1 = self.boxes[b]
        related = self.anc[a] | self.anc[b]
        self._hv = set().union(*[cv for k, (cv, _) in enumerate(self.cont_lines) if k not in related])
        self._hh = set().union(*[chh for k, (_, chh) in enumerate(self.cont_lines) if k not in related])

        def h(i, j):
            return max(bx0 - i, 0, i - bx1) + max(by0 - j, 0, j - by1)

        goalmap = defaultdict(list)
        for side, lst in self.ports[b].items():
            if ts and side != ts:
                continue
            lst = self._pin(lst, ta)
            for k, (p, d) in enumerate(lst):
                q1 = (p[0] + DX[d], p[1] + DY[d])
                q2 = (p[0] + 2 * DX[d], p[1] + 2 * DY[d])
                if not (self.free(q1) and self.free(q2)):
                    continue
                pen = 0.3 * abs(k - (len(lst) - 1) / 2) + self.port_pen(p)
                goalmap[q2].append((p, (d + 2) % 4, pen, q1))
        heap, best, parent, cnt = [], {}, {}, 0
        for side, lst in self.ports[a].items():
            if fs and side != fs:
                continue
            lst = self._pin(lst, fa)
            for k, (p, d) in enumerate(lst):
                q1 = (p[0] + DX[d], p[1] + DY[d])
                q2 = (p[0] + 2 * DX[d], p[1] + 2 * DY[d])
                if not (self.free(q1) and self.free(q2)):
                    continue
                g = 2 + 0.3 * abs(k - (len(lst) - 1) / 2) + self.port_pen(p) + self.RING
                st = (q2[0], q2[1], d)
                if g < best.get(st, 1e18):
                    best[st] = g
                    parent[st] = ("S", p, q1)
                    cnt += 1
                    heapq.heappush(heap, (g + h(*q2), g, cnt, st))
        while heap:
            f, g, _, st = heapq.heappop(heap)
            if st[0] == "G":
                _, pg, q1g, last = st
                chain = []
                s = last
                while s[0] != "S":
                    chain.append((s[0], s[1]))
                    s = parent[s]
                chain.reverse()
                return [s[1], s[2]] + chain + [q1g, pg]
            if g > best.get(st, 1e18):
                continue
            i, j, d = st
            if (i, j) in goalmap:
                for p, ind, pen, q1 in goalmap[(i, j)]:
                    if d == (ind + 2) % 4:
                        continue
                    total = g + (0 if d == ind else self.BEND) + 2 + pen
                    cnt += 1
                    heapq.heappush(heap, (total, total, cnt, ("G", p, q1, st)))
            for nd in range(4):
                if nd == (d + 2) % 4:
                    continue
                v = (i + DX[nd], j + DY[nd])
                if not self.free(v):
                    continue
                ng = g + self.step_cost((i, j), v, nd, d)
                ns = (v[0], v[1], nd)
                if ng < best.get(ns, 1e18):
                    best[ns] = ng
                    parent[ns] = st
                    cnt += 1
                    heapq.heappush(heap, (ng + h(*v), ng, cnt, ns))
        return None


def simplify(path):
    pts = [path[0]]
    for k in range(1, len(path) - 1):
        a, b, c = path[k - 1], path[k], path[k + 1]
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            pts.append(b)
    pts.append(path[-1])
    return [(x * G, y * G) for x, y in pts]


# ----------------------------------------------------------------------------- build
def build(spec):
    root = Node(spec)
    root.measure()
    root.place(0, 0, root.nw, root.nh)
    margin = 40
    # shift everything by margin
    for n in root.walk():
        n.x += margin
        n.y += margin
    W_px, H_px = root.w + 2 * margin, root.h + 2 * margin

    all_nodes = list(root.walk())
    leaves = [n for n in all_nodes if n.type == "box"]
    ids = [n.id for n in leaves if n.id]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate ids: {sorted(dup)}")
    for n in leaves:
        if not n.id:
            n.id = f"_anon{id(n)}"
    byid = {n.id: n for n in leaves}
    edges = spec.get("edges", [])
    for e in edges:
        for k in ("from", "to"):
            if e[k] not in byid:
                raise ValueError(f"edge refers to unknown leaf id {e[k]!r} (known: {sorted(byid)})")
        for side_key, at_key in (("from_side", "from_at"), ("to_side", "to_at")):
            if at_key in e and side_key not in e:
                raise ValueError(f"edge {e['from']}->{e['to']} has {at_key!r} but no {side_key!r} "
                                  f"(a fraction is only meaningful along a side you've pinned)")
    framed = [n for n in all_nodes if n.type != "box" and n.frame]
    titles = [(n.x + 10, n.y + 6, text_w(n.title, 12, True) + 12, 20) for n in framed if n.title]

    anc = {n.id: set() for n in leaves}
    for k, c in enumerate(framed):
        for l in c.walk():
            if l.type == "box":
                anc[l.id].add(k)
    R = Router(W_px // G, H_px // G, leaves, framed, titles,
               (root.x // G, root.y // G, (root.x + root.w) // G, (root.y + root.h) // G), anc)
    nedges = len(edges)
    paths = {}   # idx -> px points
    labels = {}  # idx -> (rect, text)
    warnings = {}

    def label_size(text):
        return text_w(text, 11) + 12, 16

    def place_label(idx, pts, text):
        w, hh = label_size(text)
        segs = [(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
        order = sorted(range(len(segs)), key=lambda k: -(abs(segs[k][0][0] - segs[k][1][0]) + abs(segs[k][0][1] - segs[k][1][1])))
        on_line, beside = [], []
        for k in order:
            a, b = segs[k]
            L = abs(a[0] - b[0]) + abs(a[1] - b[1])
            horiz = a[1] == b[1]
            for frac in (0.5, 0.35, 0.65, 0.2, 0.8):
                cx, cy = a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac
                if L >= (w if horiz else hh) + 16:
                    on_line.append((cx - w / 2, cy - hh / 2, cx + w / 2, cy + hh / 2))
                if L >= 24:
                    if horiz:
                        beside.append((cx - w / 2, cy - hh - 4, cx + w / 2, cy - 4))
                        beside.append((cx - w / 2, cy + 4, cx + w / 2, cy + hh + 4))
                    else:
                        beside.append((cx + 5, cy - hh / 2, cx + 5 + w, cy + hh / 2))
                        beside.append((cx - 5 - w, cy - hh / 2, cx - 5, cy + hh / 2))
        cands = on_line + beside

        def ok(r, level):
            leafpad = 10 if level < 3 else 3
            if any(rects_hit(r, lp, leafpad) for lp in R.leaf_px):
                return False
            if any(rects_hit(r, tp, 4) for tp in R.title_px):
                return False
            if any(rects_hit(r, lr[0], 4) for j, lr in labels.items() if j != idx):
                return False
            if level < 1 and any(rect_hits_seg(r, a, b, 3) for a, b in R.border_px):
                return False
            if level < 2:
                for j, pp in paths.items():
                    if j == idx:
                        continue
                    if any(rect_hits_seg(r, pp[k], pp[k + 1], 3) for k in range(len(pp) - 1)):
                        return False
            # the label must not sit on top of another connector's own line either (own line is fine)
            return True

        for level in range(4):
            for r in cands:
                if ok(r, level):
                    if level >= 2:
                        warnings[idx] = (f"label {text!r} ({edges[idx]['from']}->{edges[idx]['to']}) is cramped: "
                                         f"widen the gap around those boxes to >= {int(w) + 30}px")
                    return r
        warnings[idx] = f"label {text!r} could not be placed cleanly: widen the gap around it to >= {int(w) + 30}px"
        a, b = segs[order[0]]
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        return (cx - w / 2, cy - hh / 2, cx + w / 2, cy + hh / 2)

    def do_route(idx):
        e = edges[idx]
        warnings.pop(idx, None)
        args = (e["from"], e["to"], e.get("from_side"), e.get("to_side"), e.get("from_at"), e.get("to_at"))
        path = R.route(*args)
        if path is None:  # retry ignoring label reservations
            saved = R.lblock
            R.lblock = Counter()
            path = R.route(*args)
            R.lblock = saved
        if path is None:
            warnings[idx] = f"no route for edge {e['from']}->{e['to']}"
            return
        R.apply(path, +1)
        pts = simplify(path)
        paths[idx] = pts
        if e.get("label"):
            r = place_label(idx, pts, e["label"])
            labels[idx] = (r, e["label"])
            R.block_rect(r, +1)
        raw_paths[idx] = path

    raw_paths = {}

    def undo(idx):
        if idx in raw_paths:
            R.apply(raw_paths.pop(idx), -1)
        paths.pop(idx, None)
        if idx in labels:
            R.block_rect(labels.pop(idx)[0], -1)

    def dist(i):
        a, b = byid[edges[i]["from"]], byid[edges[i]["to"]]
        return abs(a.x + a.w / 2 - b.x - b.w / 2) + abs(a.y + a.h / 2 - b.y - b.h / 2)

    order = sorted(range(nedges), key=dist)
    for i in order:
        do_route(i)
    for _ in range(2):  # rip-up & reroute: early edges get to see later ones
        for i in order:
            undo(i)
            do_route(i)

    return dict(root=root, W=W_px, H=H_px, leaves=leaves, framed=framed, edges=edges,
                paths=paths, labels=labels, warnings=list(warnings.values()), spec=spec)


# ----------------------------------------------------------------------------- svg
CSS = """
:root{--bg:#ffffff;--text:#0f172a;--muted:#64748b;--edge:#475569;
--default-f:#ffffff;--default-s:#64748b;--service-f:#dbeafe;--service-s:#2563eb;
--store-f:#d1fae5;--store-s:#059669;--external-f:#fef3c7;--external-s:#d97706;
--client-f:#ede9fe;--client-s:#7c3aed;--queue-f:#fce7f3;--queue-s:#db2777}
@media (prefers-color-scheme: dark){:root{--bg:#0b1220;--text:#e5e7eb;--muted:#94a3b8;--edge:#94a3b8;
--default-f:#1e293b;--default-s:#94a3b8;--service-f:#1e3a5f;--service-s:#60a5fa;
--store-f:#064e3b;--store-s:#34d399;--external-f:#4a3410;--external-s:#fbbf24;
--client-f:#2e1f5e;--client-s:#a78bfa;--queue-f:#500724;--queue-s:#f472b6}}
text{font-family:%s}
.bg{fill:var(--bg)}
.cont{fill:var(--text);fill-opacity:.035;stroke:var(--text);stroke-opacity:.28;stroke-width:1.2}
.ctitle{font-size:12px;font-weight:700;fill:var(--muted);letter-spacing:.3px}
.node{stroke-width:1.5}
.lbl{font-size:14px;font-weight:600;fill:var(--text);text-anchor:middle}
.sub{font-size:11px;fill:var(--muted);text-anchor:middle}
.edge{fill:none;stroke:var(--edge);stroke-width:1.5;stroke-linejoin:round}
.dashed{stroke-dasharray:6 4}
.arrow{fill:var(--edge)}
.elbg{fill:var(--bg)}
.el{font-size:11px;fill:var(--muted);text-anchor:middle}
""" % FONT_FAMILY


def rounded_path(pts, r=6):
    d = f"M{pts[0][0]},{pts[0][1]}"
    for k in range(1, len(pts) - 1):
        p0, p1, p2 = pts[k - 1], pts[k], pts[k + 1]
        l1 = math.dist(p0, p1)
        l2 = math.dist(p1, p2)
        rr = min(r, l1 / 2, l2 / 2)
        a = (p1[0] - (p1[0] - p0[0]) / l1 * rr, p1[1] - (p1[1] - p0[1]) / l1 * rr)
        b = (p1[0] + (p2[0] - p1[0]) / l2 * rr, p1[1] + (p2[1] - p1[1]) / l2 * rr)
        d += f" L{a[0]:.1f},{a[1]:.1f} Q{p1[0]},{p1[1]} {b[0]:.1f},{b[1]:.1f}"
    d += f" L{pts[-1][0]},{pts[-1][1]}"
    return d


def to_svg(res, source=None):
    W, H, root = res["W"], res["H"], res["root"]
    o = []
    if source:
        o.append(f"<!-- Generated by boxdiagram from {escape(source)}. Do not edit: change the JSON and re-run. -->")
    o += [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
         f"<style>{CSS}</style>",
         '<defs><marker id="ah" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" '
         'markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path class="arrow" d="M0,1 L10,5 L0,9 z"/></marker></defs>']
    if not res["spec"].get("transparent"):
        o.append(f'<rect class="bg" width="{W}" height="{H}"/>')
    for n in res["framed"]:  # parents first (walk order)
        o.append(f'<rect class="cont" x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="12"/>')
        if n.title:
            o.append(f'<text class="ctitle" x="{n.x + 16}" y="{n.y + 22}">{escape(n.title)}</text>')
    for i, e in enumerate(res["edges"]):
        pts = res["paths"].get(i)
        if not pts:
            continue
        arrow = e.get("arrow", "end")
        attrs = ""
        if arrow in ("end", "both"):
            attrs += ' marker-end="url(#ah)"'
        if arrow == "both":
            attrs += ' marker-start="url(#ah)"'
        cls = "edge dashed" if e.get("dashed") else "edge"
        o.append(f'<path class="{cls}" d="{rounded_path(pts)}"{attrs}/>')
    for i, (r, text) in sorted(res["labels"].items()):
        o.append(f'<rect class="elbg" x="{r[0]:.1f}" y="{r[1]:.1f}" width="{r[2]-r[0]:.1f}" height="{r[3]-r[1]:.1f}" rx="3"/>')
        o.append(f'<text class="el" x="{(r[0]+r[2])/2:.1f}" y="{(r[1]+r[3])/2 + 3.8:.1f}">{escape(text)}</text>')
    for n in res["leaves"]:
        st = n.style if n.style in ("default", "service", "store", "external", "client", "queue") else "default"
        o.append(f'<rect class="node" x="{n.x}" y="{n.y}" width="{n.w}" height="{n.h}" rx="8" '
                 f'style="fill:var(--{st}-f);stroke:var(--{st}-s)"/>')
        lines = n.label.split("\n") if n.label else []
        subs = n.sub.split("\n") if n.sub else []
        total = len(lines) * 18 + len(subs) * 15
        y = n.y + (n.h - total) / 2
        cx = n.x + n.w / 2
        for l in lines:
            o.append(f'<text class="lbl" x="{cx}" y="{y + 9 + 5:.1f}">{escape(l)}</text>')
            y += 18
        for s in subs:
            o.append(f'<text class="sub" x="{cx}" y="{y + 7.5 + 4:.1f}">{escape(s)}</text>')
            y += 15
    o.append("</svg>")
    return "\n".join(o)


def stats(res):
    """Crossings / overlaps between connectors, for a quick quality readout."""
    segs = []
    for i, pts in res["paths"].items():
        for a, b in zip(pts, pts[1:]):
            segs.append((i, a, b))
    cross = overlap = 0
    for x in range(len(segs)):
        for y in range(x + 1, len(segs)):
            i, a, b = segs[x]
            j, c, d = segs[y]
            if i == j:
                continue
            h1, h2 = a[1] == b[1], c[1] == d[1]
            if h1 != h2:
                (hy, hx0, hx1), (vx, vy0, vy1) = ((a[1], *sorted((a[0], b[0]))), (c[0], *sorted((c[1], d[1])))) if h1 \
                    else ((c[1], *sorted((c[0], d[0]))), (a[0], *sorted((a[1], b[1]))))
                if hx0 < vx < hx1 and vy0 < hy < vy1:
                    cross += 1
            elif h1 and a[1] == c[1] and max(min(a[0], b[0]), min(c[0], d[0])) < min(max(a[0], b[0]), max(c[0], d[0])):
                overlap += 1
            elif (not h1) and a[0] == c[0] and max(min(a[1], b[1]), min(c[1], d[1])) < min(max(a[1], b[1]), max(c[1], d[1])):
                overlap += 1
    bends = sum(max(0, len(p) - 2) for p in res["paths"].values())
    return dict(edges=len(res["paths"]), crossings=cross, overlaps=overlap, bends=bends)


WIRE_SUFFIXES = (".wire.txt", ".wire")  # .wire kept as a legacy alias


def load_spec(path):
    """JSON spec or ASCII wireframe (.wire.txt) -> (spec, warnings)."""
    with open(path) as f:
        text = f.read()
    if path.endswith(WIRE_SUFFIXES):
        import wireframe
        try:
            return wireframe.parse(text)
        except wireframe.WireError as e:
            raise ValueError(f"wireframe: {e}")
    return json.loads(text), []


def out_path(spec_path):
    for suf in (".diagram.json", ".wire.txt", ".wire", ".json"):
        if spec_path.endswith(suf):
            return spec_path[: -len(suf)] + ".svg"
    return spec_path + ".svg"


def render_png(svg_file, png_file):
    """Preview only (not meant for version control). Needs playwright+chromium or cairosvg."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(device_scale_factor=1.5)
            pg.goto("file://" + os.path.abspath(svg_file))
            pg.locator("svg").screenshot(path=png_file)
            b.close()
        return True
    except Exception:
        pass
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_file, write_to=png_file, scale=1.5, background_color="white")
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("specs", nargs="+", help="spec files (foo.diagram.json or foo.wire.txt) -> foo.svg next to it")
    ap.add_argument("--out", help="output file (single spec only)")
    ap.add_argument("--check", action="store_true", help="don't write; exit 1 if an SVG is missing or stale")
    ap.add_argument("--strict", action="store_true", help="exit 1 if there are layout warnings")
    ap.add_argument("--png", metavar="DIR", help="also write a PNG preview into DIR (not for committing)")
    ap.add_argument("--to-wire", action="store_true", help="print the spec as an ASCII wireframe (structure only) and exit")
    ap.add_argument("--to-json", action="store_true", help="print a .wire.txt file as JSON spec and exit")
    ap.add_argument("--fmt", action="store_true", help="rewrite .wire.txt files in normalized, aligned form")
    ap.add_argument("--compact", action="store_true", help="with --to-wire/--fmt: use [alias] tokens + legend table")
    a = ap.parse_args()
    if a.out and len(a.specs) != 1:
        sys.exit("--out needs exactly one spec")
    rc = 0
    if a.to_wire or a.to_json or a.fmt:
        import wireframe
        for path in a.specs:
            try:
                spec, warns = load_spec(path)
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                print(f"{path}: spec error: {e}", file=sys.stderr)
                sys.exit(2)
            for w in warns:
                print(f"{path}: warning: {w}", file=sys.stderr)
            if a.to_json:
                print(json.dumps(spec, indent=1))
            elif a.to_wire:
                sys.stdout.write(wireframe.to_wire(spec, a.compact))
            else:
                import re
                compact = a.compact or bool(re.search(r"^\s*legend\s*:", open(path).read(), re.M | re.I))
                with open(path, "w") as f:
                    f.write(wireframe.to_wire(spec, compact))
                print(f"{path}: normalized")
        sys.exit(0)
    for path in a.specs:
        try:
            spec, pre_warn = load_spec(path)
            res = build(spec)
            res["warnings"] = pre_warn + res["warnings"]
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"{path}: spec error: {e!r}" if isinstance(e, KeyError) else f"{path}: spec error: {e}", file=sys.stderr)
            rc = 2
            continue
        svg = to_svg(res, source=os.path.basename(path)) + "\n"
        out = a.out or out_path(path)
        st = stats(res)
        if a.check:
            old = open(out).read() if os.path.exists(out) else None
            if old != svg:
                print(f"{path}: {out} is {'missing' if old is None else 'stale'}; run boxdiagram.py {path}")
                rc = rc or 1
            else:
                print(f"{path}: up to date")
        else:
            with open(out, "w") as f:
                f.write(svg)
            print(f"{path} -> {out}  ({res['W']}x{res['H']})  {st}")
            if a.png:
                os.makedirs(a.png, exist_ok=True)
                pf = os.path.join(a.png, os.path.basename(out)[:-4] + ".png")
                print(f"  preview: {pf}" if render_png(out, pf) else "  preview unavailable (install playwright+chromium or cairosvg)")
        for w in res["warnings"]:
            print(f"{path}: warning: {w}")
        if res["warnings"] and a.strict:
            rc = rc or 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
