---
name: rfc-writing
description: Use when the developer wants to propose an architectural or cross-module change in the Labs64.IO Ecosystem — writing, filing, or updating an RFC. Triggers include "write an RFC", "propose this change", "draft a design doc for X", "how do I get this change reviewed".
---

# Writing an RFC

## Overview

Architectural or high-risk changes go through an RFC in `labs64.io-docs-internal/rfc/`, not directly into code.

## Lifecycle

`draft → review → accepted → rejected`

1. Branch from `master` in `labs64.io-docs-internal`: `rfc/<author>/<slug>` (e.g. `rfc/RVA/payment-retry-semantics`).
2. Copy `rfc/RFC_TEMPLATE.md` to a new file (see naming below) and fill in `Context` + `Proposal`. Leave `Decision` blank.
3. Set `Status: draft` in the frontmatter.
4. Open a PR — CI (`validate-docs`, markdownlint) runs and posts a review checklist comment.
5. Once ready for feedback, set `Status: review`.
6. After a decision, set `Status: accepted` or `Status: rejected` and fill in `Decision`; merge.
7. If implementation surfaces defects, follow-ups, or open questions, record them in `Implementation Notes`.

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

## Context              <!-- What problem, why now -->
## Proposal             <!-- Specific proposed change -->
## Alternatives Considered  <!-- What else was evaluated, and why rejected -->
## Decision             <!-- Blank until accepted -->
## Implementation Notes <!-- Defects/follow-ups found during implementation -->
```

Full template: `labs64.io-docs-internal/rfc/RFC_TEMPLATE.md`. Keep each section to its stated purpose — Context is the problem, not the fix; don't pad an RFC with implementation detail that belongs in the PR instead.

## Common mistakes

| Mistake | Fix |
|---|---|
| Writing code first, RFC after, as a formality | RFC comes before implementation for architectural/high-risk changes — that's the point of the gate |
| Filling in `Decision` while still in draft | Leave `Decision` blank until the RFC is actually accepted/rejected |
| Guessing the next RFC number | Check the highest `RFC_<NN>` already in `labs64.io-docs-internal/rfc/` and increment |
| Committing the RFC alongside unrelated code changes in a module repo | RFCs live only in `labs64.io-docs-internal` — separate repo, separate history |
| Skipping "Alternatives Considered" for a change that clearly had options | Always name at least one rejected alternative, including "do nothing" if relevant |
