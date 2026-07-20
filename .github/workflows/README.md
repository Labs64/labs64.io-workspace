# Reusable GitHub Actions workflows

Shared CI/CD building blocks for the Labs64.IO ecosystem. Each module repo
calls these instead of maintaining its own workflow logic, so build/test/
publish behavior stays consistent across the polyglot fleet.

## Workflows

- **`java-ci.yml`** — Maven build + test (Java 25 / Spring Boot modules).
  Optionally pre-installs sibling modules from the same repo before the main
  build, and can upload surefire/failsafe reports as an artifact.
- **`python-ci.yml`** — pip install + pytest (FastAPI/Uvicorn services).
  Optionally runs a `docker build` smoke check and/or enables pip caching.
- **`vue-ci.yml`** — npm ci + lint + type-check + unit tests + build (Vue 3 /
  Vite frontends). Optionally uploads the `dist/` output as an artifact.
- **`docker-publish.yml`** — Builds and pushes a multi-platform image to
  DockerHub. `mode: edge` tags `<image>:edge` (master pushes after green CI);
  `mode: release` tags `<image>:<version>` + `<image>:latest` (GitHub
  releases).
- **`maven-publish.yml`** — Publishes to the Labs64 Nexus repos
  (`labs64.io-releases` / `labs64.io-snapshots`, via the poms'
  `distributionManagement`). `mode: snapshot` deploys the current
  `-SNAPSHOT` (no-op if the pom isn't a SNAPSHOT); `mode: release` sets the
  version, GPG-signs and deploys, commits + tags, then bumps to the next
  `-SNAPSHOT`.

## Calling convention

Callers pin the reusable workflow to `@master` and forward all secrets with
`secrets: inherit`:

```yaml
jobs:
  ci:
    uses: Labs64/labs64.io-workspace/.github/workflows/java-ci.yml@master
    with:
      working-directory: my-service-be
      artifact-name: my-service-test-reports
    secrets: inherit
```

See each workflow's `on.workflow_call.inputs` block for the full set of
inputs and defaults.
