---
name: ecosystem-website-sync
description: Use when major architectural or ecosystem changes occur in Labs64.IO (e.g. adding a new microservice, deprecating a module, major repo restructuring). Ensures the marketing website and ecosystem docs remain in sync. Triggers include "add a new microservice", "we are deprecating a module", "sync the ecosystem".
---

# Ecosystem Website Sync

## Overview
When the structure of the Labs64.IO ecosystem changes, the public-facing documentation and marketing website (`labs64.io-website`) must be updated to reflect reality. This skill ensures agents do not forget to update the public representation when working on backend or infrastructure changes.

## Sync Checklist

Whenever a major ecosystem change is made, execute the following updates in the `labs64.io-website` repository:

1. **Update `llms.txt`**: Add or remove the service from the "Service Catalog" section in `labs64.io-website/llms.txt`. Ensure its description accurately reflects its role (e.g. abstraction layer, core service).
2. **Update Navigation (`_data/navigation.yml`)**: If a new user-facing service or major component is added, add it to the "Solutions" dropdown in `labs64.io-website/_data/navigation.yml`.
3. **Draft an Announcement Post**: Use `just new-post "Post Title"` to create a draft blog post announcing the new architecture, microservice, or deprecation. Follow the rules in `labs64.io-website/AGENTS.md` (e.g., ensure `layout: post`).
4. **Update global `AGENTS.md`**: Verify that the global `AGENTS.md` at the workspace root correctly counts the number of independent git repos and lists the new module in the common changes table.

## Content Guidelines
- **Modularity First**: Position new services as independently adoptable modules, not monolithic requirements.
- **Audience**: Remember that the website targets developers, DevOps engineers, and CTOs. Use factual, technical language over generic marketing fluff.
- **Verification**: Run `just build` or `just serve` inside the `labs64.io-website` folder to ensure your YAML changes didn't break the Jekyll build.
