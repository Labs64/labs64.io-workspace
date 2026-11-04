#!/usr/bin/env python3
"""
wireframe - ASCII wireframe <-> boxdiagram spec.

A `.wire.txt` file is plain text: a drawing of nested boxes, then a list of connectors.

    +-- Clients ----------------------+        +-- External --+
    |  +---------+  +------------+    |        |  +--------+  |
    |  | Web App |  | Mobile App |    |        |  | Stripe |  |
    |  +---------+  +------------+    |        |  +--------+  |
    +---------------------------------+        +--------------+

    edges:
    "Web App" -> "Stripe" : charge
    gap: 80

Drawing rules
  * Boxes are rectangles: corners + - | (or box-drawing characters ┌─┐│└┘╭╮╰╯). Keep them apart
    (do not share border lines). A box containing other boxes is a container; text on its top
    border is its title: `+-- Title --+`.
  * Leaf box text: line 1 = label, further lines = small sub text.
    `#id` anywhere sets the id (default: label lowercased, non-alphanumerics -> '-').
    `{style}` sets the colour class (service, store, external, client, queue).
    `{group}` in a container title makes it an invisible group: no border, no title, there
    purely to position its children (e.g. two unrelated columns that need to sit side by
    side with nothing of their own to say about it). `{gap:N}` / `{pad:N}` in a container's
    title fix that one container's own gap or padding, a group's or an ordinary framed
    box's, regardless of the document's `gap:`/`padding:` options or any ancestor's; `{pad:0}`
    (or an untagged `{group}`, which defaults to it) lets a group's children touch its own
    outer edge with no inset, and `{gap:0}` lets them touch each other. `{justify:V}`
    (start/center/end/between) packs that container's children along its main axis when
    they don't fill it, instead of the default `start`; most useful on a `{group}` row/col
    whose parent stretches it wider or taller than its children's own natural size.
    `{fill}` in a container's title lets its children share the container's spare main-axis
    space equally (each child `grow: 1`), so a row of boxes fills its band with equal shares
    instead of leaving the space empty. `{grow:N}` gives one box a weight N for that spare
    space in its parent: in a container's title, in a leaf box's text, or on its legend row
    (`api = API {service} {grow:2}`); it overrides the parent's `{fill}` for that box.
  * Structure is inferred from POSITION only: siblings side by side = row, stacked = column,
    an aligned R x C block = grid. Exact distances are ignored (the tool picks gaps/padding).
    Layouts must be "sliceable": you can split the siblings by a straight line, recursively.

Connector lines (after a line `edges:`)
    a -> b : label        solid arrow          a ..> b : label     dashed arrow
    a <-> b               arrows both ends     a --- b             plain line
    a.right -> b.left     force attach sides (left/right/top/bottom)
    a.bottom:0.6 -> b.top:0.33   also pin WHERE on that side: 0 = the side's first port
                                 (top-most on left/right, left-most on top/bottom), 1 = its
                                 last. Only meaningful alongside a `.side`; ordinary routing
                                 (no `.side` or no `:fraction`) already searches every port on
                                 every side for the cheapest path and is usually the better
                                 choice, so reach for this only to match a hand-specified point.
  References are ids or labels ("Web App" quoted, or web-app).
Comments (never drawn; kept by --fmt, --to-json and --to-wire)
  Allowed in a header block at the very top of the file and in the trailer (from the first
  `edges:`/`legend:` line on), never inside the drawing.
    // free note                  -> JSON root "_notes" (list, in order)
    //@ diagram: text             -> JSON root "_comment"
    //@ api: text                 -> "_comment" on the box with id/slug `api`
    //@ "Edge" : text             -> "_comment" on the container titled "Edge" (or leaf labelled so)
    //@ api -> jobs: text         -> "_comment" on the edge api -> jobs (any arrow form)
  Several `//@` lines for one target are joined with a newline. A `//@` target that no longer
  exists is kept (JSON "_orphans") and reported as a warning.
  Options: `gap: 80`, `padding: 20` (defaults: gap 80 if any connector has a label, else 40).
"""
import re
import sys

H, V = "-─━═", "|│┃║"
TL, TR, BL, BR = "+┌╭┏╔", "+┐╮┓╗", "+└╰┗╚", "+┘╯┛╝"
CORNERS = set(TL + TR + BL + BR)
STYLES = {"default", "service", "store", "external", "client", "queue"}


class WireError(ValueError):
    pass


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ----------------------------------------------------------------------------- parsing
class Rect:
    def __init__(self, r0, c0, r1, c1, title):
        self.r0, self.c0, self.r1, self.c1, self.title = r0, c0, r1, c1, title
        self.children, self.parent = [], None

    @property
    def area(self):
        return (self.r1 - self.r0 + 1) * (self.c1 - self.c0 + 1)

    def contains(self, o):
        return self.r0 < o.r0 and self.c0 < o.c0 and self.r1 > o.r1 and self.c1 > o.c1

    def where(self):
        return f"box at line {self.r0 + 1}, column {self.c0 + 1}"


def find_rects(grid):
    def at(r, c):
        return grid[r][c] if 0 <= r < len(grid) and 0 <= c < len(grid[r]) else " "

    rects = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch not in TL:
                continue
            c2 = None
            for x in range(c + 1, len(row)):  # nearest corner char ends the top edge
                if row[x] in CORNERS:
                    c2 = x
                    break
            if c2 is None or row[c2] not in TR or c2 < c + 2:
                continue
            seg = row[c + 1:c2]
            if seg[0] not in H or seg[-1] not in H:
                continue
            r2 = None
            for y in range(r + 1, len(grid)):
                ch_l = at(y, c)
                if ch_l in CORNERS:
                    r2 = y
                    break
                if ch_l not in V:
                    break
            if r2 is None or at(r2, c) not in BL or r2 < r + 2:
                continue
            if at(r2, c2) not in BR:
                continue
            if not all(at(y, c2) in V for y in range(r + 1, r2)):
                continue
            if not all(at(r2, x) in H for x in range(c + 1, c2)):
                continue
            title = "".join(" " if k in H else k for k in seg).strip()
            rects.append(Rect(r, c, r2, c2, re.sub(r"\s+", " ", title)))
    return rects


def nest(rects):
    rects.sort(key=lambda x: x.area)
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if b.contains(a):
                a.parent = b
                b.children.append(a)
                break
        else:
            for b in rects:
                if b is not a and not (a.r1 < b.r0 or b.r1 < a.r0 or a.c1 < b.c0 or b.c1 < a.c0) \
                        and not a.contains(b) and not b.contains(a):
                    raise WireError(f"{a.where()} overlaps / shares a border with {b.where()}; keep boxes apart")
    return [r for r in rects if r.parent is None]


def interior_text(grid, rect):
    rows = []
    for r in range(rect.r0 + 1, rect.r1):
        chars = []
        for c in range(rect.c0 + 1, rect.c1):
            inside_child = any(k.r0 <= r <= k.r1 and k.c0 <= c <= k.c1 for k in rect.children)
            chars.append(" " if inside_child else grid[r][c] if c < len(grid[r]) else " ")
        rows.append("".join(chars).strip())
    return [x for x in rows if x]


TOKEN_RE = re.compile(r"\[([^\[\]]+)\]")


GROW_RE = re.compile(r"\s*\{grow:([^{}]*)\}")


def _grow_value(val, where):
    try:
        g = float(val)
    except ValueError:
        g = -1.0
    if g < 0:
        raise WireError(f"{{grow}} in {where} needs a number >= 0, e.g. {{grow:2}}, got {val!r}")
    return int(g) if g == int(g) else g


def split_tags(text, where="box"):
    """'Web App #web {client} {grow:2}' -> ('Web App', 'web', 'client', 2)"""
    grow = None
    m = GROW_RE.search(text)
    if m:
        grow = _grow_value(m.group(1), where)
        text = GROW_RE.sub("", text)
    m = re.search(r"#([\w.-]+)", text)
    tid = m.group(1) if m else None
    m = re.search(r"\{(\w+)\}", text)
    style = m.group(1) if m else None
    clean = re.sub(r"\s*#[\w.-]+", "", text)
    clean = re.sub(r"\s*\{\w+\}", "", clean).strip()
    return clean, tid, style, grow


def parse_legend_line(s):
    if "=" not in s:
        raise WireError(f"legend line needs 'alias = text': {s!r}")
    key, val = s.split("=", 1)
    key = key.strip()
    if not re.fullmatch(r"[\w.-]+", key):
        raise WireError(f"bad legend alias {key!r} (use letters, digits, '-', '_', '.')")
    val, tid, style, grow = split_tags(val, f"legend for {key!r}")
    parts = [p.strip() for p in val.split("|")]
    if not parts[0]:
        raise WireError(f"legend alias {key!r} has no label")
    if style and style not in STYLES:
        raise WireError(f"unknown style {{{style}}} in legend for {key!r} (known: {sorted(STYLES)})")
    ent = {"label": parts[0], "id": tid, "style": style, "grow": grow}
    if any(parts[1:]):
        ent["sub"] = "\n".join(p for p in parts[1:] if p)
    return key, ent


def make_leaf(lines, legend, where):
    """Leaf spec from the text lines of a box, or from a single [alias] token."""
    ids, styles, clean, grows = [], [], [], []
    for ln in lines:
        c, tid, st, gr = split_tags(ln, where)
        if gr is not None:
            grows.append(gr)
        if tid:
            ids.append(tid)
        if st:
            styles.append(st)
        if c:
            clean.append(c)
    if not clean:
        raise WireError(f"empty {where}: give it a label")
    tid = ids[-1] if ids else None
    style = styles[-1] if styles else None
    grow = grows[-1] if grows else None
    if len(clean) == 1 and clean[0] in legend:
        ent = legend[clean[0]]
        leaf = {"id": tid or ent.get("id") or clean[0], "label": ent["label"]}
        if ent.get("sub"):
            leaf["sub"] = ent["sub"]
        style = style or ent.get("style")
        grow = grow if grow is not None else ent.get("grow")
    else:
        leaf = {"id": tid or slug(clean[0]), "label": clean[0]}
        if len(clean) > 1:
            leaf["sub"] = "\n".join(clean[1:])
    if style and style not in STYLES:
        raise WireError(f"unknown style {{{style}}} in {where} (known: {sorted(STYLES)})")
    if style and style != "default":
        leaf["style"] = style
    if grow is not None:
        leaf["grow"] = grow
    return leaf


def area_tokens(grid, r0, r1, c0, c1, masks):
    """[alias] tokens in a region, ignoring areas covered by the given rects -> [(text, bbox)]"""
    out = []
    for r in range(r0, r1 + 1):
        chars = []
        for c in range(c0, c1 + 1):
            masked = any(k.r0 <= r <= k.r1 and k.c0 <= c <= k.c1 for k in masks)
            chars.append(" " if masked else (grid[r][c] if c < len(grid[r]) else " "))
        for m in TOKEN_RE.finditer("".join(chars)):
            out.append((m.group(1).strip(), (r, c0 + m.start(), r, c0 + m.end() - 1)))
    return out


def _groups(items, lo, hi):
    """Partition items into groups separated by empty strips along one axis (index lo/hi in bbox)."""
    items = sorted(items, key=lambda it: it[1][lo])
    out, end = [], None
    for it in items:
        if end is None or it[1][lo] > end:
            out.append([it])
            end = it[1][hi]
        else:
            out[-1].append(it)
            end = max(end, it[1][hi])
    return out


def _union(items):
    return (min(i[1][0] for i in items), min(i[1][1] for i in items),
            max(i[1][2] for i in items), max(i[1][3] for i in items))


def _align(groups, horizontal):
    """Cross-axis alignment implied by how the sibling groups line up in the drawing."""
    bbs = [_union(g) for g in groups]
    lo, hi = (0, 2) if horizontal else (1, 3)
    starts, ends = {b[lo] for b in bbs}, {b[hi] for b in bbs}
    if len(starts) == 1 and len(ends) == 1:
        return "stretch"
    if len(starts) == 1:
        return "start"
    if len(ends) == 1:
        return "end"
    cs = [(b[lo] + b[hi]) / 2 for b in bbs]
    return "center" if max(cs) - min(cs) <= 1 else "start"


def infer(items, gap):
    """items: [(spec, (r0,c0,r1,c1))] -> (spec, bbox) by recursive slicing."""
    if len(items) == 1:
        return items[0]
    hg, vg = _groups(items, 0, 2), _groups(items, 1, 3)  # horizontal bands / vertical bands
    bbox = _union(items)
    if len(hg) > 1 and len(vg) > 1 and len(hg) * len(vg) == len(items):
        cells = {}
        for ri, band in enumerate(hg):
            for it in band:
                ci = next(i for i, g in enumerate(vg) if any(it is x for x in g))
                cells.setdefault((ri, ci), []).append(it)
        if len(cells) == len(items) and all(len(v) == 1 for v in cells.values()):
            ordered = [cells[(r, c)][0][0] for r in range(len(hg)) for c in range(len(vg))]
            return ({"type": "grid", "cols": len(vg), "gap": gap, "padding": 0, "frame": False,
                     "children": ordered}, bbox)
    if len(hg) > 1:
        return ({"type": "col", "gap": gap, "padding": 0, "frame": False, "align": _align(hg, False),
                 "children": [infer(g, gap)[0] for g in hg]}, bbox)
    if len(vg) > 1:
        return ({"type": "row", "gap": gap, "padding": 0, "frame": False, "align": _align(vg, True),
                 "children": [infer(g, gap)[0] for g in vg]}, bbox)
    names = ", ".join(i[0].get("label") or i[0].get("title") or "group" for i in items)
    raise WireError(f"cannot infer a layout for: {names}. The boxes interlock so no straight line separates "
                    f"them (pinwheel); simplify or group some of them in a bigger box")


TITLE_TAG_RE = re.compile(r"\s*\{(group|gap|pad|padding|justify|fill|grow)(?::([\w.+-]+))?\}")
JUSTIFY_VALUES = {"start", "center", "end", "between"}


def _consume_title_tags(title, where):
    """Strip {group}, {gap:N}, {pad:N}/{padding:N} and {justify:V} tags from a container title.

    {group} makes the box invisible: no border, no title, drawn purely to position its
    children (gap/padding default to 0 unless overridden below). {gap:N} / {pad:N} fix
    that one container's own gap or padding, independent of the document default and of
    any sibling or ancestor container; they work on a visible container too. {justify:V}
    (V one of start/center/end/between) controls how that container packs its children
    along its main axis when they don't fill it, the one layout knob otherwise JSON-only.
    {fill} gives each child that sets no grow of its own a weight of 1 for the container's spare
    main-axis space; {grow:N} is this container's own weight in its parent.
    Returns (clean_title, frame, own_gap, own_pad, own_justify, fill, own_grow).
    """
    frame = True
    fill = False
    own_gap = own_pad = own_justify = own_grow = None

    def repl(m):
        nonlocal frame, own_gap, own_pad, own_justify, fill, own_grow
        name, val = m.group(1), m.group(2)
        if name == "fill":
            if val is not None:
                raise WireError(f"{{fill}} in {where} takes no value; use {{grow:N}} on a child for its own weight")
            fill = True
        elif name == "grow":
            if val is None:
                raise WireError(f"{{grow}} in {where} needs a value, e.g. {{grow:2}}")
            own_grow = _grow_value(val, where)
        elif name == "group":
            if val is not None:
                raise WireError(f"{{group}} in {where} takes no value")
            frame = False
        elif name == "gap":
            if val is None:
                raise WireError(f"{{gap}} in {where} needs a value, e.g. {{gap:0}}")
            own_gap = int(val)
        elif name == "justify":
            if val not in JUSTIFY_VALUES:
                raise WireError(f"{{justify}} in {where} needs one of {sorted(JUSTIFY_VALUES)}, got {val!r}")
            own_justify = val
        else:  # pad / padding
            if val is None:
                raise WireError(f"{{{name}}} in {where} needs a value, e.g. {{pad:0}}")
            own_pad = int(val)
        return ""

    clean = TITLE_TAG_RE.sub(repl, title).strip()
    bad = re.search(r"\{\s*(group|gap|pad|padding|justify|fill|grow)\b[^}]*\}?", clean)
    if bad:
        raise WireError(f"malformed tag {bad.group(0)!r} in {where} (a title turns '-' into spaces; "
                        f"write e.g. {{grow:2}}, {{gap:0}}, {{fill}})")
    return clean, frame, own_gap, own_pad, own_justify, fill, own_grow


def build_node(rect, grid, gap, legend):
    toks = area_tokens(grid, rect.r0 + 1, rect.r1 - 1, rect.c0 + 1, rect.c1 - 1, rect.children)
    if not rect.children and not toks:
        return make_leaf(interior_text(grid, rect), legend, rect.where()), None
    title, frame, own_gap, own_pad, own_justify, fill, own_grow = _consume_title_tags(rect.title, rect.where())
    if title in legend:
        title = legend[title]["label"]
    stray = [re.sub(TOKEN_RE, "", ln).strip() for ln in interior_text(grid, rect)]
    stray = [x for x in stray if x]
    warn = f"text {stray[0]!r} inside {rect.where()} is ignored (only box titles and [aliases] count)" if stray else None
    kids = [(build_node(k, grid, gap, legend)[0], (k.r0, k.c0, k.r1, k.c1)) for k in rect.children]
    kids += [(make_leaf([t], legend, f"[{t}] in {rect.where()}"), bb) for t, bb in toks]
    spec, _ = infer(kids, gap) if len(kids) > 1 else (None, None)
    if spec is None:
        spec = {"type": "col", "children": [kids[0][0]]}
    node = dict(spec)
    node["gap"] = gap if own_gap is None else own_gap
    node["frame"] = frame
    node.pop("padding", None) if frame else None
    if own_pad is not None:
        # Marks this container's padding as a fixed, per-container choice: a document-wide
        # `padding:` option (below) must not overwrite it. The marker never reaches the
        # caller; parse() strips every `_explicit_pad` key before returning the tree.
        node["padding"], node["_explicit_pad"] = own_pad, True
    elif not frame:
        node["padding"] = 0
    if own_justify is not None:
        node["justify"] = own_justify
    if fill:
        if node.get("type") == "grid":
            raise WireError(f"{{fill}} in {rect.where()} has no effect on a grid; arrange the children in one row or column")
        for c in node["children"]:
            c.setdefault("grow", 1)
    if own_grow is not None:
        node["grow"] = own_grow
    if title and frame:
        node["title"] = title
    return node, warn


EDGE_RE = re.compile(
    r'^\s*(?:"([^"]+)"|([\w-]+))(?:\.(left|right|top|bottom)(?::([\d.]+))?)?\s*'
    r'(<\.\.>|<->|\.\.>|->|---)\s*'
    r'(?:"([^"]+)"|([\w-]+))(?:\.(left|right|top|bottom)(?::([\d.]+))?)?\s*(?::\s*(.*?))?\s*$')


COMMENT_RE = re.compile(
    r'^//@\s*("[^"]+"|[\w.-]+(?:\s*(?:<\.\.>|<->|\.\.>|->|---)\s*(?:"[^"]+"|[\w.-]+))?)\s*:(?:\s?(.*))?$')
EDGE_TARGET_RE = re.compile(r'^("[^"]+"|[\w.-]+?)\s*(?:<\.\.>|<->|\.\.>|->|---)\s*("[^"]+"|[\w.-]+)$')


def _take_comment(s, comments, notes):
    """Sort one stripped `//...` line into targeted comments (`//@ target: text`) or free notes."""
    if s.startswith("//@"):
        m = COMMENT_RE.match(s)
        if not m:
            raise WireError(f"cannot parse comment line: {s!r} (expected: //@ target: text, "
                            f"target = diagram, an id, \"Title\" or a -> b)")
        comments.append((m.group(1).strip(), (m.group(2) or "").rstrip()))
    else:
        body = s[2:]
        notes.append((body[1:] if body.startswith(" ") else body).rstrip())


def _attach_comments(root, comments, resolve):
    """Store `//@` comments as `_comment` on their target; unknown targets go to root `_orphans`."""
    warnings = []

    def put(node, text):
        node["_comment"] = node["_comment"] + "\n" + text if "_comment" in node else text

    def find(n, name):
        if "children" in n and n.get("title") == name:
            return n
        for c in n.get("children", []):
            f = find(c, name)
            if f:
                return f
        return None

    def leaf_by(n, name):
        if "children" not in n:
            return n if n.get("label") == name else None
        for c in n["children"]:
            f = leaf_by(c, name)
            if f:
                return f
        return None

    def leaf_by_id(n, i):
        if "children" not in n:
            return n if n["id"] == i else None
        for c in n["children"]:
            f = leaf_by_id(c, i)
            if f:
                return f
        return None

    for target, text in comments:
        dest = None
        try:
            if target == "diagram":
                dest = root
            elif target.startswith('"') and not EDGE_TARGET_RE.match(target):
                name = target[1:-1]
                dest = find(root, name) or leaf_by(root, name)
            else:
                m = EDGE_TARGET_RE.match(target)
                if m:
                    a = resolve(m.group(1).strip('"') if m.group(1).startswith('"') else None,
                                None if m.group(1).startswith('"') else m.group(1))
                    b = resolve(m.group(2).strip('"') if m.group(2).startswith('"') else None,
                                None if m.group(2).startswith('"') else m.group(2))
                    dest = next((e for e in root["edges"] if e["from"] == a and e["to"] == b), None)
                else:
                    dest = leaf_by_id(root, resolve(None, target))
        except WireError:
            dest = None
        if dest is None:
            root.setdefault("_orphans", []).append({"target": target, "text": text})
            warnings.append(f"comment target {target!r} does not exist (//@ {target}: ...): "
                            f"update or remove the comment")
        else:
            put(dest, text)
    return warnings


def parse(text):
    """-> (spec dict, warnings list)"""
    text = text.expandtabs(4)
    lines = text.split("\n")
    h = 0  # header block: leading blank / `//` lines are comments, not part of the drawing
    while h < len(lines) and (not lines[h].strip() or lines[h].lstrip().startswith("//")):
        h += 1
    comments, notes = [], []
    for l in lines[:h]:
        if l.strip():
            _take_comment(l.strip(), comments, notes)
    lines = lines[h:]
    cut = next((i for i, l in enumerate(lines) if re.match(r"^\s*(edges|connectors|legend)\s*:\s*$", l, re.I)), None)
    drawing, trailer = (lines[:cut], lines[cut + 1:]) if cut is not None else (lines, [])
    width = max((len(l) for l in drawing), default=0)
    grid = [list(l.ljust(width)) for l in drawing]

    first = re.match(r"^\s*(edges|connectors|legend)", lines[cut], re.I).group(1).lower() if cut is not None else "edges"
    opts, edge_lines, legend, section = {}, [], {}, ("legend" if first == "legend" else "edges")
    for l in trailer:
        s_ = l.strip()
        if not s_:
            continue
        if s_.startswith("//"):
            _take_comment(s_, comments, notes)
            continue
        m = re.match(r"^(edges|connectors|legend)\s*:\s*$", s_, re.I)
        if m:
            section = "legend" if m.group(1).lower() == "legend" else "edges"
            continue
        m = re.match(r"^(gap|padding)\s*:\s*(\d+)$", s_, re.I)
        if m:
            opts[m.group(1).lower()] = int(m.group(2))
        elif section == "legend":
            k, ent = parse_legend_line(s_)
            legend[k] = ent
        else:
            edge_lines.append(s_)

    rects = find_rects(grid)
    used = set()
    for x in rects:
        used |= {(x.r0, x.c0), (x.r0, x.c1), (x.r1, x.c0), (x.r1, x.c1)}
    bad = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch in CORNERS and (r, c) not in used:
                near = [grid[rr][cc] for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                        if 0 <= rr < len(grid) and 0 <= cc < len(grid[rr])]
                if ch != "+" or any(k in H + V for k in near):
                    bad.append((r + 1, c + 1))
    if bad:
        where = "; ".join(f"line {r}, column {c}" for r, c in bad[:4])
        raise WireError(f"unclosed or misaligned box near {where}: borders must be straight, corners must "
                        f"line up and every row of a box needs both side borders")
    tops = nest(rects)
    top_toks = area_tokens(grid, 0, len(grid) - 1, 0, width - 1, tops) if grid else []
    if not rects and not top_toks:
        raise WireError("no boxes found: draw rectangles with + - | corners, or write [alias] tokens")

    parsed = []
    for s in edge_lines:
        m = EDGE_RE.match(s)
        if not m:
            raise WireError(f"cannot parse connector line: {s!r} (expected: a -> b : label)")
        parsed.append(m)
    has_labels = any(m.group(10) for m in parsed)
    gap = opts.get("gap", 80 if has_labels else 40)

    warnings = []
    items = []
    for t in tops:
        node, warn = build_node(t, grid, gap, legend)
        if warn:
            warnings.append(warn)
        items.append((node, (t.r0, t.c0, t.r1, t.c1)))
    for tok, bb in top_toks:
        items.append((make_leaf([tok], legend, f"[{tok}]"), bb))

    def collect_warn(rect):
        for k in rect.children:
            if k.children:
                _, w = build_node(k, grid, gap, legend)
                if w:
                    warnings.append(w)
                collect_warn(k)
    for t in tops:
        collect_warn(t)

    if len(items) == 1:
        root = items[0][0]
    else:
        root, _ = infer(items, gap)
        root = dict(root)
        root["padding"] = 10
    if "padding" in opts:
        def setpad(n):
            if "children" in n and n.get("frame", True) is not False and not n.get("_explicit_pad"):
                n["padding"] = opts["padding"]
            for c in n.get("children", []):
                setpad(c)
        setpad(root)

    def strip_marker(n):
        n.pop("_explicit_pad", None)
        for c in n.get("children", []):
            strip_marker(c)
    strip_marker(root)

    leaves = []

    def walk(n):
        if "children" in n:
            for c in n["children"]:
                walk(c)
        else:
            leaves.append(n)
    walk(root)
    ids = [l["id"] for l in leaves]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise WireError(f"duplicate box ids {dup}: give the boxes distinct labels or add #id tags")
    by_id = {l["id"]: l["id"] for l in leaves}
    by_slug = {slug(l["label"]): l["id"] for l in leaves}

    def resolve(quoted, bare):
        ref = quoted or bare
        if ref in by_id:
            return by_id[ref]
        if slug(ref) in by_slug:
            return by_slug[slug(ref)]
        if slug(ref) in by_id:
            return by_id[slug(ref)]
        raise WireError(f"connector refers to unknown box {ref!r}; known: {sorted(ids)}")

    edges = []
    for m in parsed:
        e = {"from": resolve(m.group(1), m.group(2)), "to": resolve(m.group(6), m.group(7))}
        if m.group(10):
            e["label"] = m.group(10)
        if m.group(3):
            e["from_side"] = m.group(3)
        if m.group(4):
            e["from_at"] = float(m.group(4))
        if m.group(8):
            e["to_side"] = m.group(8)
        if m.group(9):
            e["to_at"] = float(m.group(9))
        op = m.group(5)
        if op in ("..>", "<..>"):
            e["dashed"] = True
        if op in ("<->", "<..>"):
            e["arrow"] = "both"
        elif op == "---":
            e["arrow"] = "none"
        edges.append(e)
    root["edges"] = edges
    if notes:
        root["_notes"] = notes
    warnings += _attach_comments(root, comments, resolve)
    return root, warnings


# ----------------------------------------------------------------------------- printing
def _ntype(n):
    return n.get("type") or ("col" if "children" in n else "box")


def _pad(lines, w, h):
    return [l.ljust(w) for l in lines] + [" " * w] * (h - len(lines))


def _framed(lines):
    return len(lines) >= 2 and lines[0][:1] == "+" and lines[-1][:1] == "+"


def _stretch(lines, w, h):
    """Stretch a framed block (box/container) to w x h like align=stretch; unframed blocks are padded."""
    cw, ch = _size(lines)
    if not _framed(lines):
        return _pad(lines, max(w, cw), max(h, ch))
    w, h = max(w, cw), max(h, ch)
    out = []
    for i, l in enumerate(lines):
        if w > cw:
            fill = "-" if i in (0, len(lines) - 1) else " "
            l = l[:-1] + fill * (w - cw) + l[-1]
        out.append(l)
    blank = "|" + " " * (w - 2) + "|"
    return out[:-1] + [blank] * (h - ch) + out[-1:]


def _size(lines):
    return max((len(l) for l in lines), default=0), len(lines)


def _grow_tag(g):
    return f"{{grow:{g}}}"


def _mark_grow(n, parent_fill=False):
    """Annotate a copy of the tree with what --to-wire writes: `_wfill` on a container whose
    children all set grow (written as {fill}), `_wgrow` on a node whose own grow must be
    written as {grow:N} (any grow its parent's {fill} does not already imply)."""
    g = n.get("grow")
    if g is not None and not (parent_fill and g == 1):
        n["_wgrow"] = g
    kids = n.get("children") or []
    fill = bool(kids) and n.get("type") != "grid" and all("grow" in c for c in kids) \
        and any(c["grow"] == 1 for c in kids)
    if fill:
        n["_wfill"] = True
    for c in kids:
        _mark_grow(c, fill)


def _box(n, compact=False):
    if compact:
        return ["[" + n["id"] + "]"]
    first = n["label"].split("\n")[0]
    rest = n["label"].split("\n")[1:] + (n.get("sub", "").split("\n") if n.get("sub") else [])
    if slug(first) != n["id"]:
        first += f"  #{n['id']}"
    if n.get("style", "default") != "default":
        first += f"  {{{n['style']}}}"
    if n.get("_wgrow") is not None:
        first += "  " + _grow_tag(n["_wgrow"])
    text = [first] + rest
    w = max(len(t) for t in text) + 2
    return ["+" + "-" * w + "+"] + ["| " + t.ljust(w - 1) + "|" for t in text] + ["+" + "-" * w + "+"]


def _vfit(lines, w, h, align):
    """Fit a block into height h according to the row's cross-axis alignment."""
    cw = _size(lines)[0]
    if align == "stretch":
        return _stretch(lines, w, h)
    extra = h - len(lines)
    top = {"start": 0, "end": extra, "center": extra // 2}.get(align, 0)
    return [" " * cw] * top + [l.ljust(cw) for l in lines] + [" " * cw] * (extra - top)


def _hfit(lines, w, align):
    if align == "stretch":
        return _stretch(lines, w, len(lines))
    f = {"start": str.ljust, "end": str.rjust, "center": str.center}.get(align, str.ljust)
    return [f(l, w) for l in lines]


def _render(n, depth, compact=False, gap_chars=2):
    t = _ntype(n)
    if t == "box":
        return _box(n, compact)
    kids = [_render(c, depth + 1, compact) for c in n.get("children", [])]
    if not kids:
        return []
    align = n.get("align", "stretch")
    if t == "row":
        h = max(len(k) for k in kids)
        parts = [_vfit(k, _size(k)[0], h, align) for k in kids]
        body = [(" " * gap_chars).join(p[i] for p in parts) for i in range(h)]
    elif t == "col":
        w = max(_size(k)[0] for k in kids)
        body = []
        for k in kids:
            body += _hfit(k, w, align) + [""]
        body = [l.ljust(w) for l in body[:-1]]
    else:
        cols = max(1, int(n.get("cols", 2)))
        rows = [kids[i:i + cols] for i in range(0, len(kids), cols)]
        cw = [max(_size(r[c])[0] for r in rows if c < len(r)) for c in range(cols)]
        body = []
        for r in rows:
            h = max(len(k) for k in r)
            cells = [_stretch(k, cw[i], h) for i, k in enumerate(r)] + [[" " * cw[i]] * h for i in range(len(r), cols)]
            body += [(" " * gap_chars).join(c[j] for c in cells) for j in range(h)] + [""]
        body = body[:-1]
    framed = n.get("frame", depth > 0 or bool(n.get("title")))
    title = n.get("title", "")
    tags = (" {fill}" if n.get("_wfill") else "") + \
        (" " + _grow_tag(n["_wgrow"]) if n.get("_wgrow") is not None else "")
    if tags and depth == 0 and not framed and not title:
        # The implicit root has no box to carry a tag, and it has no parent to grow in.
        if n.get("_wfill"):
            print("warning: {fill} on the root cannot be written to a .wire.txt; draw a box around "
                  "the root's children to keep it", file=sys.stderr)
        tags = ""
    title = (title + tags).strip()
    if not framed:
        if not title:
            return body
        # A named invisible group still needs a box drawn around it so the name (and the
        # fact that it's deliberately grouped rather than an incidental sibling pairing)
        # survives a --to-wire/--fmt round-trip; an anonymous one has nothing to lose by
        # flattening, so it stays invisible in the text too.
        title = f"{title} {{group}}"
    w = max(_size(body)[0] + 2, len(title) + 6)
    top = "+-- " + title + " " if title else "+"
    top = top + "-" * (w + 1 - len(top)) + "+"
    out = [top] + ["| " + l.ljust(w - 1) + "|" for l in body] + ["+" + "-" * w + "+"]
    return out


def _comment_lines(target, text):
    """`//@ target: line` for each line of a comment (none if there is no comment)."""
    if text is None or text == "":
        return []
    return [f"//@ {target}: {ln}".rstrip() for ln in str(text).split("\n")]


def to_wire(spec, compact=False):
    import copy
    spec = copy.deepcopy(spec)
    _mark_grow(spec)
    lines = _render(spec, 0, compact)
    ids = {}

    def walk(n):
        if "children" in n:
            for c in n["children"]:
                walk(c)
        elif n.get("id"):
            ids[n["id"]] = n
    walk(spec)
    out = [l.rstrip() for l in lines] + [""]
    head = _comment_lines("diagram", spec.get("_comment"))
    head += [("// " + n).rstrip() for n in spec.get("_notes", [])]
    for o in spec.get("_orphans", []):
        head += _comment_lines(o["target"], o["text"])
    if head:
        out = head + [""] + out
    node_cm = {}  # target text -> comment lines, for boxes and containers, in tree order

    def collect(n):
        if n.get("_comment"):
            if "children" not in n:
                node_cm[n["id"]] = _comment_lines(n["id"], n["_comment"])
            elif n.get("title"):
                node_cm['"%s"' % n["title"]] = _comment_lines('"%s"' % n["title"], n["_comment"])
            else:
                print("warning: _comment on an untitled container cannot be written to a .wire.txt; dropped",
                      file=sys.stderr)
        for c in n.get("children", []):
            collect(c)
    for c in spec.get("children", []):
        collect(c)
    if compact:
        rows = []
        for i, n in ids.items():
            label = n["label"].replace("\n", " ")
            subs = [x for x in (n.get("sub", "").split("\n") if n.get("sub") else []) if x]
            style = n.get("style", "default")
            gtag = (" " + _grow_tag(n["_wgrow"])) if n.get("_wgrow") is not None else ""
            if label != i or subs or style != "default" or gtag:
                rows.append((i, " | ".join([label] + subs) + (f" {{{style}}}" if style != "default" else "") + gtag))
        if rows:
            kw = max(len(k) for k, _ in rows)
            out += ["legend:"]
            for k, v in rows:
                out += node_cm.pop(k, []) + [f"{k.ljust(kw)} = {v}"]
            out += [""]
    out += ["edges:"]
    for lns in node_cm.values():
        out += lns
    for e in spec.get("edges", []):
        op = "..>" if e.get("dashed") else "->"
        if e.get("arrow") == "both":
            op = "<..>" if e.get("dashed") else "<->"
        elif e.get("arrow") == "none":
            op = "---"
        a = e["from"] + (f".{e['from_side']}" if e.get("from_side") else "")
        if e.get("from_side") and e.get("from_at") is not None:
            a += f":{e['from_at']}"
        b = e["to"] + (f".{e['to_side']}" if e.get("to_side") else "")
        if e.get("to_side") and e.get("to_at") is not None:
            b += f":{e['to_at']}"
        out += _comment_lines(f"{e['from']} -> {e['to']}", e.get("_comment"))
        out.append(f"{a} {op} {b}" + (f" : {e['label']}" if e.get("label") else ""))

    def first_gap(n):
        if "children" in n:
            return n.get("gap")
        return None
    g = first_gap(spec)
    if g is not None:
        out.append(f"gap: {g}")
    return "\n".join(out) + "\n"
