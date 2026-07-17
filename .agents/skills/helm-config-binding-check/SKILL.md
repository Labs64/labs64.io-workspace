---
name: helm-config-binding-check
description: Use when adding, renaming, or restructuring a Helm chart's values.yaml / applicationYaml config for any Labs64.IO module, or when a deployed service isn't picking up a config value that looks correctly set. Triggers include "add a config option", "wire a new setting into the chart", "why isn't my config taking effect", "add values to the chart".
---

# Helm Config-Binding Check

## Overview

A Helm value only does something if its rendered path matches exactly what the consuming service reads. Nesting it one level off renders fine, passes `helm lint`, and fails **silently** — no error, just a default or empty value at runtime.

**Rendering successfully is not evidence the value is read.** Only checking the binding path or observing runtime behavior is.

## Binding mechanisms in this ecosystem

| Consumer | Binding mechanism | Where to find the real key path |
|---|---|---|
| Java Spring services (`*-be`) | `@ConfigurationProperties(prefix = "...")` on a `@Configuration` class | `grep -rn "@ConfigurationProperties" <module>-be/src/main/java` — the prefix is the required top-level key under `applicationYaml` |
| Python FastAPI services | pydantic `BaseSettings`/env vars, or a framework-specific runtime config injection (e.g. a plugin module that receives a `properties` dict at call time) | Check the service's own source — don't assume one pattern applies ecosystem-wide; some services bind from env vars, others receive config injected per-call |

## Check procedure

1. **Find the real binding path before editing `values.yaml`.** For Java, grep the `@ConfigurationProperties` prefix as above. For Python, read the service's actual config-loading code (settings class, or wherever it reads its runtime config) — don't assume it matches another service's pattern.
2. **Render and inspect**, don't just lint:
   ```bash
   helm template <release> labs64.io-helm-charts/charts/<module> \
     -f labs64.io-helm-charts/overrides/<module>/values.local.yaml \
     | grep -A5 "kind: ConfigMap"
   ```
   Confirm the YAML nesting in the rendered ConfigMap matches the binding path exactly — same key names, same depth.
3. **After renaming or restructuring any values.yaml key**, run `just generate-all` in `labs64.io-helm-charts/` to regenerate the chart README and `values.schema.json` — stale schema docs are worse than none.
4. **Verify at runtime, not just at render time.** Deploy locally and check the service's own startup log for a line that only prints when the value actually bound to something non-default (e.g. a "Loaded N <things>" line, where `N` should match what you configured). A value can render correctly and still fail to reach the object the framework builds if there's a type mismatch or a second conflicting key.
5. **If the ConfigMap changed but the pod didn't pick it up**, check whether the Deployment has a `checksum/config` annotation on the pod template (chart-libs helper). Without it, `helm upgrade` updates the ConfigMap but doesn't roll the pods.

## Common mistakes

| Mistake | Fix |
|---|---|
| Assuming a Python service reads config the same way as another Python service in the ecosystem | Check that specific service's own config-loading code — don't generalize from one service to another |
| Trusting `helm lint` / successful `helm template` as proof the value is consumed | Neither one knows what the application binds to — grep/read the source for the binding path |
| Renaming a `values.yaml` key without regenerating docs | Run `just generate-all` after any key rename/restructure |
| Assuming a ConfigMap update takes effect immediately | Check for a `checksum/config` pod annotation; without it, `helm upgrade` doesn't restart pods |
| Declaring the same setting name at two different nesting levels during a refactor (old + new) | Grep the whole chart for the old key name and remove it once migrated — leftover dead keys are confusing, not harmless |
