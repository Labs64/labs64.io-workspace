# boxdiagram (Claude Code skill)

Diagrams as **JSON specs or ASCII wireframes in git**, SVGs **generated** next to them. Nested `row` / `col` / `grid`
boxes with automatic layout and orthogonal connector routing that avoids boxes, container titles and labels.

This folder is a complete skill: commit it as `.claude/skills/boxdiagram/` (project) or put it in
`~/.claude/skills/boxdiagram/` (personal). No install step and no runtime dependencies (Python 3.8+).
PNG previews (for Claude to look at its result) need `playwright` + chromium or `cairosvg`; optional.

    boxdiagram/
      SKILL.md            instructions for Claude (workflow, spec + wireframe notation, troubleshooting)
      scripts/            boxdiagram.py (CLI), wireframe.py (ASCII parser), metrics.json (font widths),
                          git-pre-commit (git hook, see below)
      examples/           architecture.diagram.json, shop.wire.txt, alias.wire.txt and their SVGs

## Use

Ask Claude in plain language. Examples:

*From a description:*

    Create a diagram docs/architecture.svg of our system: a "Clients" group (Web App, Mobile App), an "Edge"
    group (CDN, WAF), a "Backend" group (API Gateway, Auth Service, Job Queue) and a "Data" group (Postgres,
    Redis). Flow left to right: clients -> CDN -> WAF -> API Gateway; the gateway calls Auth Service and
    Postgres, the Job Queue (dashed, async) feeds a worker that writes Postgres. Label the gateway -> Auth
    connector "JWT". Use the boxdiagram skill.

*From a sketch (the layout is what you draw):*

    Use the boxdiagram skill to render this as docs/shop.svg. Save the sketch as docs/shop.wire.txt unchanged.

    +-- Edge --------+     +-- Backend --------+
    | [cdn]   [waf]  |     | [api]    [jobs]   |
    +----------------+     +-------------------+

    legend:
    cdn  = CDN {external}
    waf  = WAF | rate limits {service}
    api  = API Gateway {service}
    jobs = Job Queue | Redis {queue}

    edges:
    cdn -> waf
    waf -> api : HTTPS
    api ..> jobs : enqueue
    gap: 100

*From the code:*

    Read docker-compose.yml and the services under src/ and create docs/deployment.diagram.json showing the
    containers, their dependencies and the ports. Group them by network. Keep it under 20 boxes.

*Updating:*

    We added a Redis cache between the API and Postgres. Update docs/architecture.diagram.json (keep the existing
    ids), regenerate the SVG and check the result.

Tips: name the groups and the flow direction, say which connectors are async (dashed) or need a label, and mention
the target file so Claude puts the source and the SVG where you want them. Claude renders a preview, looks at it
and fixes cramped labels or tangled connectors before it hands over.

By hand (paths relative to this folder):

    python3 scripts/boxdiagram.py docs/architecture.diagram.json --png /tmp/preview   # -> docs/architecture.svg
    python3 scripts/boxdiagram.py docs/shop.wire.txt                                  # wireframe -> docs/shop.svg
    python3 scripts/boxdiagram.py --to-wire --compact x.diagram.json                  # JSON -> short-form wireframe
    python3 scripts/boxdiagram.py --fmt docs/shop.wire.txt                            # realign a wireframe
    python3 scripts/boxdiagram.py --check --strict $(git ls-files '*.diagram.json' '*.wire.txt')   # CI

Markdown embeds the result as a normal image: `![Architecture](docs/architecture.svg)`.

### Describing a layout in plain text

Draw containers as boxes (`+-- Title --+`), write leaves as short `[alias]` tokens (or draw them as boxes),
then add a `legend:` table (`alias = Label | sub {style}`) and the connectors (`a -> b : label`). Side by side
= row, stacked = column, aligned block = grid. The parser infers the structure from positions.
Full notation: `SKILL.md`. Examples: `examples/`.

## Git hook: keep SVGs in sync with their sources

`scripts/git-pre-commit` refuses a commit when any `*.diagram.json` / `*.wire.txt` tracked in the repo has a
missing or stale SVG, or produces layout warnings (`--check --strict`). The SVG output is deterministic
(bundled font metrics), so it is identical on every machine.

It looks for the skill in `<repo>/.claude/skills/boxdiagram`; set `BOXDIAGRAM_DIR` to use another location
(e.g. `~/.claude/skills/boxdiagram`).

**Plain git hook** (per clone; `.git/hooks` is not versioned):

    cp .claude/skills/boxdiagram/scripts/git-pre-commit .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
    # or keep it up to date with the skill:
    ln -sf ../../.claude/skills/boxdiagram/scripts/git-pre-commit .git/hooks/pre-commit

If you already have a `pre-commit` hook, call the script from it instead: add the line
`.claude/skills/boxdiagram/scripts/git-pre-commit || exit 1`.

**Versioned hooks for the whole team** (`core.hooksPath`):

    mkdir -p .githooks
    ln -s ../.claude/skills/boxdiagram/scripts/git-pre-commit .githooks/pre-commit
    git add .githooks && git config core.hooksPath .githooks     # each clone runs the config line once

**pre-commit framework** (`.pre-commit-config.yaml`):

    repos:
      - repo: local
        hooks:
          - id: boxdiagram
            name: boxdiagram SVGs up to date
            entry: .claude/skills/boxdiagram/scripts/git-pre-commit
            language: script
            pass_filenames: false
            files: '\.(diagram\.json|wire\.txt)$'

When the hook fails, regenerate (`python3 .claude/skills/boxdiagram/scripts/boxdiagram.py <source>`), `git add` the
SVG and commit again. Skip once with `git commit --no-verify`. The same check works in CI:
`python3 .claude/skills/boxdiagram/scripts/boxdiagram.py --check --strict $(git ls-files '*.diagram.json' '*.wire.txt')`.
