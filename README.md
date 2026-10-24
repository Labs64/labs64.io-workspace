# Labs64.IO :: Workspace

**Work on the whole Labs64.IO Ecosystem from source, in one command.**
*Part of the [Labs64.IO Ecosystem](https://labs64.io): the contributor entry point: every repository, one toolchain, one local platform.*

[![CI](https://github.com/Labs64/labs64.io-workspace/actions/workflows/labs64io-ci.yml/badge.svg)](https://github.com/Labs64/labs64.io-workspace/actions/workflows/labs64io-ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![📖 Documentation](https://img.shields.io/badge/📖-Documentation-AB6543.svg)](https://labs64.io/docs/development/)

<p align="center"><img src="docs/assets/workspace-hero.svg" alt="Workspace: One command, just up, builds and deploys every ecosystem repository to a local k3d cluster; repository tiles light up as they build until the gateway is ready." width="880"></p>

[Why Workspace?](#why-workspace) · [Documentation](https://labs64.io/docs/getting-started/run-the-full-ecosystem-locally.html) · [Build and test](#build-and-test) · [Ecosystem](#the-labs64io-ecosystem) · [labs64.io](https://labs64.io)

> [!NOTE]
> Labs64.IO is ten independent Git repositories, not a monorepo. If you only want to **see** it running you do not need the workspace: use `install.sh`.

## Why Workspace?

Changing a platform that spans many repositories means the same toolchain, the same pinned versions and a local cluster that behaves like the real thing. Setting that up by hand is a day you do not get back; Workspace makes it a command.

1. **One checkout command.** `just clone` fetches every ecosystem repository next to the workspace.
2. **One pinned toolchain.** A dev container carries every tool at the version the repositories expect.
3. **One local platform.** `just up` builds every first-party image and deploys it to a k3d cluster; `just smoke` checks it.

**A good fit if**

- You are about to change code in one or more Labs64.IO repositories and want a working environment fast.
- You review pull requests that span repositories.
- You want an AI agent to work across the ecosystem with the same tools you have.

**Probably not what you need if**

- You only want to see Labs64.IO running: `install.sh` is quicker and needs no checkouts.
- You are using one module in your own project: use that module's Docker or Kubernetes option instead.

## Documentation

Install, configure and operate Workspace in the **[Workspace documentation](https://labs64.io/docs/getting-started/run-the-full-ecosystem-locally.html)**.

[Workspace and source repositories](https://labs64.io/docs/development/workspace-repositories.html) · [Contributing guide](https://labs64.io/docs/development/contributing.html)

New to Labs64.IO? The [Quickstart](https://labs64.io/docs/getting-started/quickstart.html) puts the platform on any Kubernetes cluster in about five minutes.

## Build and test

```bash
just doctor      # check your tools against the pinned versions
just ci          # the workspace's own checks: run it before pushing
```

Needs `just`, Docker and Git. [`docs/reference.md`](docs/reference.md) lists every command and [`docs/justfiles.md`](docs/justfiles.md) explains how the justfiles are organised. Working on the code with an AI agent? [`AGENTS.md`](AGENTS.md) and [`CLAUDE.md`](CLAUDE.md) describe the layout, conventions and checks.

## The Labs64.IO Ecosystem

This repository is part of the [Labs64.IO Ecosystem](https://labs64.io): open-source building blocks for secure commerce platforms. Every module is documented at [labs64.io/docs](https://labs64.io/docs/).

| Module | What it does |
|---|---|
| [**AuditFlow**](https://github.com/Labs64/labs64.io-auditflow) | Publish once, route anywhere, lose nothing |
| [**Auth Gateway**](https://github.com/Labs64/labs64.io-authproxy) | One authenticated edge for every module |
| [**Payment Gateway**](https://github.com/Labs64/labs64.io-payment-gateway) | One API across multiple payment providers |
| [**Checkout**](https://github.com/Labs64/labs64.io-checkout) | Whitelabel checkout and order workflow |
| [**Customer Portal**](https://github.com/Labs64/labs64.io-customer-portal) | Self-service portal for your customers |

Built on [Commons](https://github.com/Labs64/labs64.io-commons), deployed with [Helm Charts](https://github.com/Labs64/labs64.io-helm-charts), developed in the [Workspace](https://github.com/Labs64/labs64.io-workspace), verified by [Tests](https://github.com/Labs64/labs64.io-tests) and documented in [Docs](https://github.com/Labs64/labs64.io-docs). Also from Labs64: [NetLicensing](https://netlicensing.io) for licensing-as-a-service and [GuideChimp](https://www.labs64.com/guidechimp/) for guided product tours.

## Contributing

We would love your help. The workspace is where contributors spend their first hour, so every rough edge you smooth here helps the next person. Fork the repository, make your change on a branch, run the checks described in [`AGENTS.md`](AGENTS.md) and open a pull request. Not sure whether an idea fits? Open an issue first.

## License

Open source under the [Apache License 2.0](LICENSE): use it, change it and ship it commercially.

---

<p align="center">
  <a href="https://labs64.io"><img alt="Labs64.IO" src="https://labs64.io/docs/assets/images/labs64-logo.png" width="110"></a><br>
  <sub>Made by the <a href="https://labs64.io">Labs64</a> team and community.</sub>
</p>
