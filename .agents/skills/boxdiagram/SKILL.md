---
name: boxdiagram
description: Create, update and fix architecture/flow diagrams kept in version control as `*.diagram.json` specs or ASCII `*.wire.txt` wireframes, auto-laid-out and rendered to SVG (committed next to the source). Use when the user asks for a diagram, pastes or describes an ASCII layout sketch, asks to change a diagram, or when code/infra changes make an existing `*.diagram.json` / `*.wire.txt` / its `.svg` out of date.
---

# boxdiagram: diagrams as text, SVG generated

A diagram is a **text source** describing nested boxes (row / col / grid) and connectors between them: either a
**JSON spec** (`foo.diagram.json`) or an **ASCII wireframe** (`foo.wire.txt`, see below). Pick one per diagram.
A script computes the layout, routes the connectors orthogonally (around boxes, container titles and
labels), and writes an SVG. You never touch coordinates and you **never edit the SVG by hand**: it is a
build artifact and is overwritten on the next run.

Convention: `docs/foo.diagram.json` (or `docs/foo.wire.txt`) -> `docs/foo.svg` (same folder, same name). Commit both.
Markdown embeds the SVG as a normal image: `![Architecture](docs/foo.svg)`.

The script lives in this skill's directory: `scripts/boxdiagram.py` (Python 3.8+, no dependencies).
Below, `$BD` means `python3 <this skill's directory>/scripts/boxdiagram.py`.

## Workflow

1. **Find what exists.** `git ls-files '*.diagram.json' '*.wire.txt'` (or Glob). To change a diagram, read its source.
   Create a new one only when asked or when nothing fits.
2. **Edit the JSON, minimally.** Keep existing `id`s and sibling order unless the change requires
   otherwise (stable specs give small SVG diffs). When adding a component add its leaf *and* its edges;
   when removing one, remove every edge that mentions it (unknown ids are a hard error).
3. **Render:** `$BD path/foo.diagram.json --png /tmp/bd-preview` writes `foo.svg` and a PNG preview.
4. **Look at it.** Open the PNG with the Read tool and actually inspect it: overlapping or clipped text,
   connectors that wander around the canvas, lines squeezed together, labels far from their line. Also
   read the printed stats (`crossings`, `overlaps`, `bends`) and every `warning:` line.
   If no PNG preview is possible, rely on stats and warnings and say so.
5. **Fix via the spec, then re-render** (table below). Two or three rounds is normal. Stop when it is clean,
   not when it is perfect.
6. **Verify and commit both files:** `$BD --check --strict $(git ls-files '*.diagram.json' '*.wire.txt')` must pass
   (exit 0 = SVGs match their specs, no warnings). Stage JSON and SVG together.

## Wireframe input (`.wire.txt`): when the user shows you the layout they want

Users can sketch the layout as ASCII art. Save their sketch **verbatim** as `docs/<name>.wire.txt` (do not redraw
it by hand) and render it. Structure is inferred from box positions only; distances are ignored (the tool
chooses gaps and padding), so a sketch only has to get containment, order and alignment right.

```
+-- Edge -------------------+
|  +-----+    +------------+|      Containers = boxes that contain boxes; text on the top
|  | CDN |    | WAF        ||      border is the title. Leaf text: line 1 = label, more lines
|  +-----+    | {external} ||      = sub text, `#id` sets the id, `{style}` the colour
|             +------------+|      (service, store, external, client, queue).
+---------------------------+      Side by side = row, stacked = column, aligned RxC block = grid.

+-- Backend ----------------+
|  +-----+    +------+      |      edges:
|  | API |    | Jobs |      |      CDN -> WAF
|  | #api|    +------+      |      WAF -> API : HTTPS       (solid arrow)
|  +-----+                  |      api ..> jobs : enqueue   (dashed)
+---------------------------+      a <-> b    a --- b       (both ends / no arrow)
                                   a.right -> b.left         (force attach sides)
```

### Short form: `[alias]` tokens + `legend:` (preferred when you write a wireframe yourself)

LLMs cannot count characters reliably, so avoid drawing borders around leaves. Write each leaf as a short
`[alias]` token and keep the texts in a legend table. Only containers are drawn (their borders still have to
line up; run `--fmt` afterwards). Aliases are the ids, so connectors use them too.

```
+-- Edge -------+
| [cdn]  [waf]  |
+---------------+

+-- Backend ----+
| [api]  [jobs] |
+---------------+

legend:
cdn  = CDN {external}
waf  = WAF | rate limits {service}
api  = API Gateway {service}
jobs = Job Queue | Redis {queue}

edges:
cdn -> waf
waf -> api : HTTPS
api ..> jobs : enqueue
gap: 80
```

- `alias = Label | sub text | more sub text {style}` (`#id` is optional; the alias is the id). A `[token]` with
  no legend entry simply uses its text as the label (`[Web App]`). Aliases also work as box text
  (`| gw |`) and as container titles.
- Stacked rows of tokens that line up in columns become a grid; otherwise rows/columns as drawn.
- Alignment (start/center/end/stretch) is inferred from how siblings line up in the drawing.
- `$BD --to-wire --compact foo.diagram.json` prints an existing spec in this form. Roughly 3x smaller than
  the fully boxed drawing and smaller than the JSON, so use it to show structure cheaply.

- Connectors go in the `edges:` list below the drawing, never as ASCII arrows. References are ids, labels
  (`"Web App"`) or slugs (`web-app`). Options: `gap: 80`, `padding: 20` (default gap 80 when connectors
  have labels, else 40).
- Boxes must not share border lines; corners must line up. Unicode box characters work too.
- The layout must be sliceable (some straight line splits the siblings, recursively). Interlocking
  "pinwheel" layouts are rejected with an explanation; put some boxes in a bigger box.
- Errors name the line and column. After editing a `.wire.txt` by hand, `$BD --fmt file.wire.txt` rewrites it
  aligned and normalized (keeps the short form if the file has a `legend:`; this also fixes sloppy spacing
  that still parses).
- `$BD --to-wire [--compact] foo.diagram.json` prints any JSON spec as a wireframe: a cheap way to show the
  user (or yourself) the current structure. `$BD --to-json foo.wire.txt` converts the other way when you need
  options a wireframe cannot express (`align`, `justify`, `grow`, a grid's `cols`). After converting, delete
  the `.wire.txt` so there is one source.
- Edit an existing `.wire.txt` like any diagram: change the drawing or the edges, keep ids stable, render, look.
- Do not keep `foo.wire.txt` and `foo.diagram.json` side by side (both would write `foo.svg`).

### Invisible layout boxes: grouping with nothing to say about it

Some boxes exist only to position their children (two unrelated columns that need to sit side by side,
with no shared title or meaning of their own); drawing a visible border around them would just be noise.

- **JSON:** `"frame": false` on any container suppresses its border and title (even if one is set) while it
  keeps sizing and placing its children exactly as a framed container would; `"gap": 0` / `"padding": 0` are
  valid on it like on any container, letting children sit flush against each other and against its own edge.
- **`.wire.txt`:** put `{group}` in the container's title to get the same thing: draw the box (so the file
  still shows the grouping and its order) but render it invisibly. `{gap:N}` and `{pad:N}` in that same title
  fix that one container's own gap or padding regardless of the document's `gap:`/`padding:` options or any
  ancestor's; combine them, e.g. `+-- {group} {gap:0} {pad:0} ---+`, to make the children touch each other
  and the group's own outer edge. These two tags work on an ordinary framed, titled box too, not only on a
  `{group}` one.
- A named `{group}` (title text alongside the tag, e.g. `{group} Deployments`) keeps its name and its box
  through `--to-wire`/`--fmt`; an anonymous one (bare `{group}`, or no box drawn at all and left to position
  inference) renders as plain, undecorated rows/columns in the text, same as any other auto-inferred wrapper.

## Fixing problems: symptom -> spec change

| Symptom | Fix |
|---|---|
| `label ... is cramped: widen the gap ...` | Increase `gap` of the row/col/grid between those boxes to the suggested value. Gaps are the routing channels, so they must fit the labels. |
| Connector loops around the outside or through unrelated containers | Reorder siblings so connected things are neighbours and flow in one direction (e.g. left to right); put the hub in the middle; widen the gap it has to pass through. |
| Many connectors converge on one box, arrowheads pile up | Give that box more room (a taller/wider neighbour, `align`), split the node, or drop redundant edges. Combine "A->X, B->X, C->X" into a group container only if that reads better. |
| Lines run tight against a container border | Increase `padding` of that container (default 20). |
| Two connectors overlap (`overlaps` > 0) | Widen the gap they share. |
| Too many crossings | Reorder siblings; move a node to the other side of its main partner; consider two diagrams. |
| Ugly stretched boxes | Set `align: "start"` or `"center"` on the container; `justify` for the main axis. |
| A connector must leave a specific side | `from_side` / `to_side` (left/right/top/bottom). Use sparingly. |

## Writing good specs

- **Structure first.** Containers = real groupings (a deployment unit, a layer, a bounded context), with a
  `title`. Leaves = components. Nest at most 2-3 levels. Aim for <= ~20 leaves; split bigger systems.
- **Flow direction.** Arrange rows/cols so most edges point the same way (top to bottom or left to right).
- **Labels** on connectors are short (<= 12 characters: protocol, verb, data). Leave unlabeled what is obvious.
- **Gap sizing rule:** any gap that a labeled connector must pass through should be >= widest label in px
  + 30. Roughly 7px per character + 30 (so 80 for an 8-character label). Default gap is 40 (only fits
  unlabeled lines); default padding is 20.
- **Styles** (`style` on leaves): `default`, `service` (blue, your own services), `store` (green,
  databases/storage), `external` (amber, third parties), `client` (violet, users/clients), `queue` (pink,
  brokers/streams). Use them consistently across the project's diagrams.
- **Dashed** connectors (`"dashed": true`) for async/optional flows; `"arrow": "both"` or `"none"` if needed.

## Spec reference

Every node is an object. A node with `children` is a container, otherwise a leaf.

```json
{
  "type": "row",
  "gap": 60, "padding": 10,
  "children": [
    {"type": "col", "title": "Backend", "gap": 50, "children": [
      {"id": "api", "label": "API", "sub": "FastAPI", "style": "service"},
      {"type": "grid", "cols": 2, "title": "Workers", "children": [
        {"id": "w1", "label": "Worker 1", "style": "service"},
        {"id": "w2", "label": "Worker 2", "style": "service"}
      ]}
    ]},
    {"id": "db", "label": "Postgres", "style": "store"}
  ],
  "edges": [
    {"from": "api", "to": "db", "label": "SQL"},
    {"from": "api", "to": "w1", "dashed": true}
  ]
}
```

| Key | On | Meaning |
|---|---|---|
| `type` | any | `row`, `col`, `grid`, `box`. Default: `col` if it has children, else `box`. |
| `id` | leaf | Unique; edges refer to it. |
| `label`, `sub` | leaf | Main text (`\n` for lines) and smaller second text. |
| `style` | leaf | See styles above. |
| `title` | container | Drawn top-left; connectors keep away from it. |
| `cols` | grid | Number of columns; children fill row by row. |
| `gap` | container | Space between children (px, default 40; 0 is valid). |
| `padding` | container | Inner padding (px, default 20; 0 is valid). |
| `align` | container | Cross axis: `stretch` (default), `start`, `center`, `end`. |
| `justify` | row/col | Main axis: `start` (default), `center`, `end`, `between`. |
| `grow` | child | Weight for receiving extra main-axis space. |
| `frame` | container | Draw the border box and title (default true; the root only if it has a title). `false` makes a purely structural, invisible box: it still sizes and places its children, and routes connectors through it with no border to avoid, but draws nothing of its own. |
| `edges[]` | root | `from`, `to` (leaf ids), optional `label`, `from_side`, `to_side`, `dashed`, `arrow` (`end`/`both`/`none`). |
| `transparent` | root | No background rectangle. |

All sizes snap to a 10px grid. Connectors attach to **leaves only** (not to containers).

## Limits to be honest about

- Routing is heuristic: no guarantee of a clean result when many connectors must share one gap.
  Spec changes (ordering, gaps) fix almost everything; report remaining issues rather than hacking the SVG.
- Text is measured with bundled DejaVu Sans metrics so output is identical on every machine; the SVG asks
  for DejaVu Sans/Verdana, and other fonts may render slightly narrower (never wider).
- Not for sequence diagrams, timelines, or charts.

## CI / pre-commit

`python3 <path>/scripts/boxdiagram.py --check --strict $(git ls-files '*.diagram.json' '*.wire.txt')` exits 1 when an SVG
is missing or stale, or a layout warning exists. Suitable as a git pre-commit hook (see README.md) or CI step.
