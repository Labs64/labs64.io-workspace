---
name: rfc-writing
description: Use when the developer wants to propose an architectural or cross-module change in the Labs64.IO Ecosystem — writing, filing, or updating an RFC. Triggers include "write an RFC", "propose this change", "draft a design doc for X", "how do I get this change reviewed".
---

# Writing an RFC

## Overview

Architectural or high-risk changes go through an RFC in `labs64.io-docs-internal/rfc/`, not directly into code. An RFC is a **decision document**, not an implementation log or a tutorial.

## Writing principles (non-negotiable)

1. **Be specific.** Name the module, file, header, entity, operator, phase. "Route through the edge PEP" beats "handle auth centrally." Every claim points at something concrete.
2. **No fluff. Less with more.** Cut adjectives, hedging, and restated context. One sharp sentence beats a paragraph. If a line doesn't change a reader's decision, delete it. Prefer tables and lists over prose.
3. **Follow the template.** Keep each section to its stated purpose — Context is the *problem*, Proposal is the *change*, implementation detail belongs in the PR, not the RFC. Don't pad an RFC into a design encyclopedia.
4. **Diagram whenever it helps** (see below). A diagram that replaces three paragraphs is a win.
5. **Always evaluate alternatives** (see below). An RFC with no rejected option looks like a decision already made off-doc.
6. **State decisions to persist them.** When the point of the change is to stop re-litigating something ("X is a router, not a store"), write it as a flat invariant the reader can't miss, and mirror it into the affected module's `AGENTS.md`/`README` so agents don't reopen it.

Length is a feature. A focused 200-line RFC gets read and decided; a 600-line one gets skimmed. When updating an existing RFC, cut the implementation trail down to a status summary — the RFC records the *decision and its evidence*, not every commit.

## Diagrams

Use them wherever structure, flow, or comparison is easier seen than read:

- **Architecture / layering** → Mermaid `flowchart TB` (subgraphs per tier).
- **Request / message sequence** → Mermaid `sequenceDiagram`.
- **Pipelines, data flow, directory shape** → a small ASCII diagram inline (renders everywhere, diffs cleanly).
- **Trade-offs / option comparison / threat→mitigation** → a Markdown table, not prose.

Keep each diagram to the one thing it shows. A diagram is documentation, so it must stay correct — update it when the design changes.

## Alternatives Considered

Every RFC names at least one rejected alternative, **including "do nothing"** when relevant. For a real engine/tech choice, use a comparison table so the trade is legible:

```
| Consideration | Option A (rejected) | Option B (chosen) |
| --- | --- | --- |
| <the axis that decides it> | … | … |
```

Rules:
- Lead each rejected option with the **one decisive reason** it lost, then any secondary points.
- Answer the strongest objection to your choice, not a strawman.
- If an alternative is partially adopted, say which part and which part is declined.
- "Do nothing" earns its place when the cost of inaction is the real driver.

## Lifecycle

`draft → review → accepted → rejected`

1. Branch from `master` in `labs64.io-docs-internal`: `rfc/<author>/<slug>` (e.g. `rfc/RVA/payment-retry-semantics`).
2. Copy `rfc/RFC_TEMPLATE.md` to a new file (see naming below) and fill in `Context` + `Proposal`. Leave `Decision` blank.
3. Set `Status: draft` in the frontmatter.
4. Open a PR — CI (`validate-docs`, markdownlint) runs and posts a review checklist comment.
5. Once ready for feedback, set `Status: review`.
6. After a decision, set `Status: accepted` or `Status: rejected` and fill in `Decision`; merge.
7. If implementation surfaces defects, follow-ups, or open questions, record them concisely in `Implementation Notes`.

## Filename convention

Existing RFCs use `YYYY-MM-DD_RFC_<NN>_<kebab-slug>.md`, e.g. `2026-06-16_RFC_02_payment-retry-semantics.md`. **Check the highest existing `RFC_<NN>` in `labs64.io-docs-internal/rfc/` and increment it** — don't reuse or guess a number.

## Template structure

```
---
Title: <Short descriptive title>
Author: <github-handle>
Reviewers: <team or handles>
Date: YYYY-MM-DD
Updated: YYYY-MM-DD
Status: draft
Tags: <comma-separated domain tags>
---

## Context              <!-- The problem, and why now. Not the fix. -->
## Proposal             <!-- The specific change. Diagrams + tables. -->
## Alternatives Considered  <!-- What else, and the decisive reason each lost. -->
## Decision             <!-- Blank until accepted. -->
## Implementation Notes <!-- Defects/follow-ups found during implementation. Keep it a status summary. -->
```

Full template: `labs64.io-docs-internal/rfc/RFC_TEMPLATE.md`.

## Common mistakes

| Mistake | Fix |
|---|---|
| Prose where a table or diagram is clearer | Convert trade-offs, mappings, and layers to tables/diagrams |
| Padding with restated context and adjectives | Cut to concrete points; length is not credibility |
| Writing code first, RFC after, as a formality | RFC comes before implementation for architectural/high-risk changes — that's the gate |
| Filling in `Decision` while still in draft | Leave `Decision` blank until the RFC is actually accepted/rejected |
| Guessing the next RFC number | Check the highest `RFC_<NN>` already present and increment |
| Committing the RFC alongside unrelated code changes in a module repo | RFCs live only in `labs64.io-docs-internal` — separate repo, separate history |
| Skipping "Alternatives Considered" for a change that clearly had options | Always name at least one rejected alternative, including "do nothing" |
| Letting Implementation Notes grow into a commit-by-commit log | Condense to what's done / pending / decided; detail lives in the PRs |
