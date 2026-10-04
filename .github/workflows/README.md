# Reusable GitHub Actions workflows

Shared CI/CD building blocks for the Labs64.IO ecosystem. Each module repo
calls these instead of maintaining its own workflow logic, so build/test/
publish behavior stays consistent across the polyglot fleet.

## One release model

Every repository releases the same way: **publish a GitHub Release whose tag is the
version `X.Y.Z`**. Nothing is committed back and no file is edited to "set the version".

- **Java** poms declare `<version>${revision}</version>` (default `0.0.0-SNAPSHOT`,
  inherited from `io.labs64:labs64io-parent`). The release build runs with
  `-Drevision=<tag>`, so the jar, the image and the tag agree. Because the project is
  then a release, the `requireReleaseDeps` enforcer rule in `labs64io-parent` fails the
  build on any `-SNAPSHOT` parent or dependency — a tag can always be rebuilt.
- **Images** are pushed as `<image>:<tag>`, labelled
  `org.opencontainers.image.version=<tag>`, and identified downstream by digest.
- **Charts**: the release dispatches the digests to `labs64.io-helm-charts`, which opens
  a PR pinning them, setting `appVersion`, and bumping the module chart **and** the
  `labs64io-ecosystem` umbrella. The published umbrella version is the ecosystem
  release; Renovate proposes it to `labs64.io-devops` (`CHART_VERSION`).

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
  `-SNAPSHOT` (no-op if the pom isn't a SNAPSHOT). `mode: release` builds the
  checked-out commit with `-Drevision=<version>` and deploys it GPG-signed
  (`-P release`), after verifying that the pom really takes its version from
  `${revision}`; `publish-central: true` additionally publishes to Maven Central.
  It never commits, tags or pushes, so callers need only `contents: read`. Used by
  `labs64.io-commons` (the whole reactor) and `labs64.io-auditflow` (`auditflow-api`).
- **`renovate.yml`** — not reusable: the scheduled Renovate run for the whole
  ecosystem (see [Dependency updates](#dependency-updates)).
- **`labs64io-ci.yml`** — not reusable: this repository's own CI. `tooling` runs the gate
  scripts' tests, `actionlint` (with shellcheck) over every workflow here, and validates the
  Renovate preset; `ecosystem` runs `check-release-wiring.py` and `check-version-pins.py` over
  `master` of all 13 repositories, on every change here **and daily** — so drift that lands in
  another repository is reported here, not found at release time. `just verify-process` runs the
  same checks locally.

## Composite actions

In `.github/actions/`, referenced like the workflows
(`Labs64/labs64.io-workspace/.github/actions/<name>@v1`):

- **`tool-versions`** — exports every pin in [`tool-versions.env`](../../tool-versions.env)
  as an environment variable (`TERRAFORM_VERSION`, `HELM_DOCS_VERSION`, …).
- **`setup-k8s-tools`** — installs helm, helm plugins, helmfile, k3d and just at those
  versions (and exports them). No workflow anywhere installs one of these tools by hand
  or names a version; `just check-pins` fails if one does.
- **`maven-settings`** — writes the `settings.xml` with the Labs64 Nexus / Maven Central
  server entries; used by the three Maven-running workflows above.


  `java-ci.yml`'s reusable-workflow `permissions:` block was deliberately left
  unset (inherits from the caller) rather than hardcoded — so a caller that
  only grants `contents: read` (e.g. commons) keeps read-only tokens, while a
  caller that grants `contents: write` (needed for
  `submit-dependency-graph`) gets it. Don't add a top-level `permissions:`
  block back to `java-ci.yml` without re-checking every existing caller.

## Calling convention

Callers reference the workflows and actions at the moving major tag `@v1` and forward
all secrets with `secrets: inherit`:

```yaml
jobs:
  ci:
    uses: Labs64/labs64.io-workspace/.github/workflows/java-ci.yml@v1
    with:
      working-directory: my-service-be
      artifact-name: my-service-test-reports
    secrets: inherit
```

See each workflow's `on.workflow_call.inputs` block for the full set of
inputs and defaults.

### Versioning these workflows

Every module's CI and release pipeline runs this repository's code, so a change here is a
change to twelve pipelines at once. `v1` is a tag, not a branch: merging to `master` does
**not** change what callers run until the tag is moved.

```bash
# after merging a backwards-compatible change and seeing it green here
git tag -f v1 origin/master && git push -f origin v1
```

A change that callers must adapt to (a renamed input, a new required secret, different
semantics) gets a new major tag (`v2`); callers move to it one repository at a time, and
`v1` keeps working until the last one has moved.

## Dependency updates

Renovate, configured once: [`default.json`](../../default.json) at the root of this
repository is the shared preset, and each repository's `renovate.json` contains only
`{"extends": ["github>Labs64/labs64.io-workspace"]}`.

Beyond the usual manifests (Maven, npm, pip, Dockerfiles, compose, GitHub Actions,
Terraform, helmfile, Helm chart dependencies) it follows pins that live outside any
package manifest, wherever the line above them says what they are:

```
# renovate: datasource=github-releases depName=kubernetes-sigs/gateway-api
GATEWAY_API_VERSION := "v1.6.2"
```

Add that annotation whenever a version has to be written in a `justfile.versions`, a shell script, an
env file, a Dockerfile `ARG` or a Chart.yaml `appVersion` (XML:
`<!-- renovate: datasource=maven depName=group:artifact -->` above a pom property).

`renovate.yml` runs it for every repository with a `renovate.json`. It needs the
`RENOVATE_TOKEN` secret (a PAT that may open PRs in the ecosystem repositories) and
reuses `L64_PUB_CI_USERNAME` / `L64_PUB_CI_PASSWORD` so that releases in the private
Labs64 Nexus (`labs64io-parent`, `auditflow-api`) are proposed too.

## Consuming the digest

`docker-publish.yml` exposes the pushed image's digest so downstream jobs can
reference the exact artifact instead of a tag. Neither Docker Hub nor GHCR can
enforce tag immutability, so `<image>:<version>` may later resolve to different
content than the run that validated it; the digest cannot move.

```yaml
jobs:
  publish-be:
    uses: Labs64/labs64.io-workspace/.github/workflows/docker-publish.yml@v1
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
