# Reusable GitHub Actions workflows

Shared CI/CD building blocks for the Labs64.IO ecosystem. Each module repo
calls these instead of maintaining its own workflow logic, so build/test/
publish behavior stays consistent across the polyglot fleet.

## Workflows

- **`java-ci.yml`** — Maven build + test (Java 25 / Spring Boot modules).
  Optionally pre-installs sibling modules from the same repo before the main
  build, and can upload surefire/failsafe reports as an artifact. Also
  optional: bring up/tear down docker-compose test dependencies
  (`compose-file`/`compose-project`), extra build-step environment variables
  (`extra-env`, one `KEY=VALUE` per line), a post-test unpushed Docker build
  sanity check (`docker-build-context`/`docker-build-tag`), and Maven
  dependency-graph submission for Dependabot (`submit-dependency-graph` —
  needs `contents: write` granted by the calling job).
- **`python-ci.yml`** — pip install + pytest (FastAPI/Uvicorn services).
  Optionally runs a `docker build` smoke check, enables pip caching, and/or
  uploads test output (`artifact-name`/`test-results-path`, e.g. a
  `--junit-xml` file).
- **`vue-ci.yml`** — npm ci + lint + type-check + unit tests + build (Vue 3 /
  Vite frontends). Optionally uploads the `dist/` output as an artifact.
- **`docker-publish.yml`** — Builds and pushes a multi-platform image to
  DockerHub. `mode: edge` tags `<image>:edge` (master pushes after green CI);
  `mode: release` tags `<image>:<version>` + `<image>:latest` (GitHub
  releases).
- **`maven-publish.yml`** — Publishes to Labs64 Nexus via the poms'
  `distributionManagement` (credentials are injected for server ids
  `labs64-nexus` / `labs64-nexus-snapshots`). `mode: snapshot` deploys the current
  `-SNAPSHOT` (no-op if the pom isn't a SNAPSHOT); `mode: release` sets the
  version, GPG-signs and deploys, commits + tags, then bumps to the next
  `-SNAPSHOT`. Callers must grant `permissions: contents: write` on the
  calling job for **both** modes — this workflow declares `contents: write`
  at its own top level and GitHub enforces that against the caller
  regardless of which mode runs.


  `java-ci.yml`'s reusable-workflow `permissions:` block was deliberately left
  unset (inherits from the caller) rather than hardcoded — so a caller that
  only grants `contents: read` (e.g. commons) keeps read-only tokens, while a
  caller that grants `contents: write` (needed for
  `submit-dependency-graph`) gets it. Don't add a top-level `permissions:`
  block back to `java-ci.yml` without re-checking every existing caller.

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
