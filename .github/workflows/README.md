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
  releases). Outputs the immutable identity of what it pushed —
  `image`, `tag` (the primary one; never `latest`), `digest`, and `image-ref`
  (`<image>@sha256:…`) — and fails if the build returns no usable digest. The
  required-OCI-label check runs against the digest, so it asserts the labels on
  the exact artifact of that run rather than on whatever the tag resolves to
  later. See [Consuming the digest](#consuming-the-digest).
- **`chart-update-dispatch.yml`** — Sends the release's image digests to
  `labs64.io-helm-charts` as a `module-released` repository_dispatch; that repo
  opens a PR pinning them into the chart. Validates the payload before sending
  (chart name, version, one `repository@sha256:…` per line). Needs a PAT in
  `CHART_DISPATCH_TOKEN`; without it the job warns, prints the equivalent
  `gh api` command in the job summary, and succeeds — a missing propagation
  secret must not fail an otherwise good release.
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

## Consuming the digest

`docker-publish.yml` exposes the pushed image's digest so downstream jobs can
reference the exact artifact instead of a tag. Neither Docker Hub nor GHCR can
enforce tag immutability, so `<image>:<version>` may later resolve to different
content than the run that validated it; the digest cannot move.

```yaml
jobs:
  publish-be:
    uses: Labs64/labs64.io-workspace/.github/workflows/docker-publish.yml@master
    with:
      image: labs64/checkout
      context: ./checkout-be
      mode: release
      version: ${{ github.event.release.tag_name }}
    secrets: inherit

  propagate:
    needs: publish-be
    runs-on: ubuntu-latest
    steps:
      - name: Show what to pin
        env:
          IMAGE: ${{ needs.publish-be.outputs.image }}
          DIGEST: ${{ needs.publish-be.outputs.digest }}
          REF: ${{ needs.publish-be.outputs.image-ref }}
        run: echo "$REF"   # -> labs64/checkout@sha256:...
```

Every release publisher in the ecosystem is wired this way — `auditflow` (3 images),
`checkout` (2), `authproxy` -> `charts/api-gateway`, `customer-portal`, and
`payment-gateway`. `just check-release-wiring` (in this repo) verifies the whole
chain across repos: each `mode: release` publisher must dispatch a chart update
naming a real chart and supplying exactly the first-party images that chart
deploys. `mode: edge` publishers are excluded — `:edge` is not a release and must
never move a chart.

The digest feeds two consumers:

- the Helm chart's `image.digest` value (`chart-libs >= 0.3.0` renders
  `repository@sha256:…` when it is set, and validates the format at render time);
- the release manifest's `artifacts.container[].digest`.

A release that publishes several images (AuditFlow ships three, checkout two)
calls this workflow once per image and collects one digest from each — all of
them belong to the same release.
