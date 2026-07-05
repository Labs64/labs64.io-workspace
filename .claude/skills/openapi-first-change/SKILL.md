---
name: openapi-first-change
description: Use when changing an API contract (adding/renaming a field, endpoint, or model) for any Labs64.IO Java backend module. Triggers include "add a field to the API", "change the endpoint", "add a new API model", or any edit landing under a module's target/generated-sources.
---

# OpenAPI-First API Changes

## Overview

Every Java backend module in this ecosystem is OpenAPI-first: the YAML spec is the source of truth, and Java interfaces/models are generated from it at build time via `openapi-generator-maven-plugin`, bound to the Maven `generate-sources` phase. **Never hand-edit anything under `target/generated-sources` or `target/classes` — it's overwritten on every build and diverges silently from the spec.** This is guardrail #1 in the root `AGENTS.md`.

## Where the spec lives

The standard layout is a dedicated `<module>-api` submodule (e.g. `auditflow-api`):

```
<module>-api/src/main/resources/openapi/openapi-<module>.yaml
```

`<module>-api` generates the Java models/client from that spec and is published as a versioned library to the **Labs64 Nexus** and **Maven Central** repositories — other services (in this ecosystem or external) consume the API contract as a dependency instead of copying types by hand. The module's own backend (`<module>-be`) also generates its server-side interfaces from the same spec file, so a spec change regenerates both consistently.

If a module doesn't yet have a dedicated `-api` submodule, the spec may still live under `<module>-be/src/main/resources/openapi/`. Treat that as the module not having split out its client library yet, not as a different convention — the target layout is always the `-api` submodule pattern.

## Workflow

1. **Edit the YAML spec** in `<module>-api`, not generated code.
2. **Regenerate** by building the module(s) that read the spec — the plugin is bound to `generate-sources`, so either of these trigger it:
   ```bash
   mvn -B clean generate-sources --file <module>-api/pom.xml   # regenerate only
   mvn -B clean package -DskipTests --file <module>-api/pom.xml  # regenerate + compile
   ```
   Check the module's `justfile` first — most modules have a build recipe that wraps this.
3. **Implement against the regenerated interface.** For Spring-generated server interfaces (`interfaceOnly: true`), your `@RestController` implements the generated `*Api` interface — the compiler fails loudly if your controller drifts from the spec, which is the point.
4. **If the API client library needs a new release** (external consumers depend on it), bump its version and publish to Nexus/Maven Central per the module's release process — don't let consumers pick up contract changes only via a snapshot.
5. **Update the Helm chart / config binding** if the change affects request/response validation, defaults, or new required config — see the `helm-config-binding-check` skill if it touches `values.yaml`.
6. **Never commit anything under `target/`** — it's a build artifact, not source. If you see edits staged there, that's a sign the spec wasn't the actual source of the change.

## Common mistakes

| Mistake | Fix |
|---|---|
| Editing a generated model/interface directly under `target/generated-sources` to "quickly" fix a field | Edit the YAML spec and rebuild — the generated code is discarded and regenerated every build |
| Forgetting to rebuild after a spec edit, then wondering why the IDE still shows the old model | Rebuild the `-api` module; IDEs often cache stale generated sources until then |
| Assuming model changes alone are enough when a field also needs config wiring | Cross-check whether the new field needs a matching `values.yaml`/config key — see `helm-config-binding-check` |
| Changing the spec without considering published-client consumers | If `<module>-api` is already published, treat the spec as a versioned public contract, not an internal file |
| Putting a new module's spec directly under `-be` instead of a `-api` submodule | Follow the `<module>-api` layout so the client can be generated and published consistently |
