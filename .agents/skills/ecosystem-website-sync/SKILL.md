---
name: ecosystem-website-sync
description: Use when major architectural or ecosystem changes occur in Labs64.IO (e.g. adding a new microservice, deprecating a module, major repo restructuring). Ensures the marketing website and ecosystem docs remain in sync. Triggers include "add a new microservice", "we are deprecating a module", "sync the ecosystem".
---

# Ecosystem Website Sync

## Overview
When the structure of the Labs64.IO ecosystem changes, the public-facing documentation and marketing website (`labs64.io-website`) must be updated to reflect reality. This skill ensures agents do not forget to update the public representation when working on backend or infrastructure changes.

## Sync Checklist

Whenever a major ecosystem change is made, execute the following updates in the `labs64.io-website` repository:

1. **Add the module to `_data/modules.yml`**: This is the single source of truth for module identity and status. Add an entry with `id`, `name`, `tagline`, `url`, `repo`, `status`, `group`, and `known_gaps`.
   - `status` must be honest and one of `beta`, `alpha`, `planned`, `exploring` — there is deliberately **no GA tier**.
   - `version` is optional: include it only if there is a real release tag. Never fabricate one — omit the field if there isn't.
   - `group` is `available` (shipped, usable today) or `planned` (not yet).
2. **Add the module's id to `_data/navigation.yml`**: Add it to the appropriate `groups:` list under the "Modules" nav entry — `Available now` or `Planned` — matching the `group` you set in `modules.yml`. Do not hand-author a new dropdown or nav entry.
3. **Update `llms.txt`**: Add or remove the service from the "Service Catalog" section in `labs64.io-website/llms.txt`. Ensure its description accurately reflects its role (e.g. abstraction layer, core service).
4. **Draft an Announcement Post**: Use `just new-post "Post Title"` to create a draft blog post announcing the new architecture, microservice, or deprecation. Follow the rules in `labs64.io-website/AGENTS.md` (e.g., ensure `layout: post`).
5. **Update global `AGENTS.md`**: Verify that the global `AGENTS.md` at the workspace root correctly counts the number of independent git repos and lists the new module in the common changes table.

**Never hand-write a status, version, or module display name into a page or into `navigation.yml`.** These render from `_data/modules.yml` via `_includes/module-status.html` and `_includes/module-banner.html` — editing them anywhere else creates a second source of truth that will drift.

## Content Guidelines
- **Modularity First**: Position new services as independently adoptable modules, not monolithic requirements.
- **Audience**: Remember that the website targets developers, DevOps engineers, and CTOs. Use factual, technical language over generic marketing fluff.
- **Verification**: Run `just build` inside the `labs64.io-website` folder to ensure your YAML changes didn't break the Jekyll build (do not run `just serve` — it starts a long-running dev server).
