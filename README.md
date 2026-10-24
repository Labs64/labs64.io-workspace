# Labs64.IO :: Workspace

**Work on the whole Labs64.IO Ecosystem from source, in one command.**
*Part of the [Labs64.IO Ecosystem](https://labs64.io): the contributor entry point: every repository, one toolchain, one local platform.*

[![CI](https://github.com/Labs64/labs64.io-workspace/actions/workflows/labs64io-ci.yml/badge.svg)](https://github.com/Labs64/labs64.io-workspace/actions/workflows/labs64io-ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![📖 Documentation](https://img.shields.io/badge/📖-Documentation-AB6543.svg)](https://labs64.io/docs/development/)

<p align="center"><img src="docs/assets/workspace-hero.svg" alt="Workspace: One command, just up, builds and deploys every ecosystem repository to a local k3d cluster; repository tiles light up as they build until the gateway is ready." width="880"></p>

[**Get started**](#get-started) · [Features](#features) · [Architecture](#architecture) · [AI agents](#using-workspace-with-ai-agents) · [Ecosystem](#the-labs64io-ecosystem) · [Documentation](https://labs64.io/docs/development/) · [labs64.io](https://labs64.io)

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

## Get started

Four ways in. Pick the one that matches what you have; each is complete on its own.

```
 1  install.sh             2  Dev container          3  Docker                 4  Source
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│ Just see it running:  │ │ Open the folder in    │ │ Clone the ecosystem,  │ │ Open all repos as     │
│ no workspace needed;  │ │ VS Code and reopen    │ │ build every image     │ │ one multi-root        │
│ install the platform  │ │ in the container:     │ │ and run the platform  │ │ workspace, change     │
│ with one script       │ │ every tool pinned     │ │ on a local k3d        │ │ any module            │
├───────────────────────┤ ├───────────────────────┤ ├───────────────────────┤ ├───────────────────────┤
│ needs  a cluster,     │ │ needs  VS Code,       │ │ needs  Docker, just   │ │ needs  VS Code, Git   │
│        kubectl, helm  │ │        Docker         │ │                       │ │                       │
│ time   ~5 minutes     │ │ time   ~5 minutes     │ │ time   first build    │ │ time   ~2 minutes     │
└───────────────────────┘ └───────────────────────┘ └───────────────────────┘ └───────────────────────┘
 evaluate first            get the tools             run from source           work on the code
```

Not sure? Run **1** first: if all you want is to call the platform, you are done in five minutes.

### 1. `install.sh`: the quick ecosystem start

You do not need this workspace to see Labs64.IO running. One script installs the gateway, AuditFlow and Payment Gateway on any Kubernetes cluster, then proves it with a real request.

```bash
# No cluster yet? A throwaway one needs only Docker and k3d:
k3d cluster create labs64io-demo -p "8000:80@loadbalancer" --k3s-arg "--disable=traefik@server:0"

curl -fsSL https://raw.githubusercontent.com/Labs64/labs64.io-helm-charts/master/install.sh -o install.sh
bash install.sh
```

Press Enter three times to take the defaults. A few minutes later you should see:

```text
  PASS  Obtained a demo access token from mock-oidc
  PASS  Published a demo audit event (HTTP 200) — first good request succeeded

 Labs64.IO is ready.
   Base URL:  http://localhost:8000
   API docs:  http://localhost:8000/swagger-ui/
```

Come back here when you want to change the code. The same script later runs `status`, `stop`, `start` and `uninstall`. This is an evaluation install with a demo identity provider: keep it on a local or private cluster. Details: [Quickstart](https://labs64.io/docs/getting-started/quickstart.html) · [`install.sh`](https://github.com/Labs64/labs64.io-helm-charts/blob/master/install.sh).

### 2. Dev container: every tool at the pinned version

Open the `labs64.io-workspace` folder in VS Code and choose **Reopen in Container**. The dev container mounts the folder that holds all ecosystem repositories at `/workspaces`, so keep the folder name `labs64.io-workspace` and clone into an empty parent folder:

```bash
mkdir labs64.io && cd labs64.io
git clone https://github.com/Labs64/labs64.io-workspace.git
code labs64.io-workspace
```

No VS Code? Install the [prerequisites](https://github.com/Labs64/labs64.io-workspace#-prerequisites) yourself; `just doctor` checks them.

### 3. Docker: on your machine

Docker, `just` and the checkouts are all that is needed; images are built in a builder container:

```bash
cd labs64.io-workspace
just doctor && just clone && just up
```

The first run downloads and builds everything. It ends with:

```text
Local environment ready: http://gateway.localhost/swagger-ui/
```

`just smoke` runs the fast smoke tests against the cluster and `just down` deletes it again.

### 4. Source: work on the code

After `just clone` every repository sits next to the workspace. Open them all at once with **File ▸ Open Workspace from File…** and choose `labs64.io-workspace/labs64.io.code-workspace`.

```
<ecosystem-root>/
├── labs64.io-workspace/     # this repository: justfile, dev container, scripts
├── labs64.io-auditflow/
├── labs64.io-checkout/
├── labs64.io-helm-charts/
└── ...                      # the remaining ecosystem repositories
```

All `just` recipes run from `labs64.io-workspace/`. The other repositories are mounted as modules, so `just helm-charts <recipe>` and `just tests <recipe>` run in those repositories without a `cd`. See [`docs/reference.md`](docs/reference.md) for every command (versions, releases, dependency updates) and [`docs/justfiles.md`](docs/justfiles.md) for how every justfile is organised.

### Where next?

Everything below is in the [Workspace documentation](https://labs64.io/docs/development/):

| I want to… | Read |
|---|---|
| Understand which repository does what | [Workspace repositories](https://labs64.io/docs/development/workspace-repositories.html) |
| Follow the contribution workflow | [Contributing guide](https://labs64.io/docs/development/contributing.html) |
| Fix a first-run problem | [Troubleshooting](https://labs64.io/docs/getting-started/troubleshooting.html) |
| Read every `just` command | [`docs/reference.md`](docs/reference.md) |
| Add or change a `just` recipe | [`docs/justfiles.md`](docs/justfiles.md) |
| Compare all the ways to run Labs64.IO | [Choose a deployment path](https://labs64.io/docs/getting-started/choose-a-deployment-path.html) |

Something not working? [Troubleshooting your first run](https://labs64.io/docs/getting-started/troubleshooting.html) covers the usual suspects, and you are always welcome to [open an issue](https://github.com/Labs64/labs64.io-workspace/issues).

## Features

- **Multi-repo bootstrap**: `just clone` fetches every ecosystem repository next to the workspace.
- **Pinned dev container**: every tool at the version the repositories expect, with Docker-outside-of-Docker.
- **Local platform**: `just up` builds first-party images in a builder container and deploys them to k3d with a local registry.
- **Smoke tests**: `just smoke` checks the running platform through the gateway.
- **Knowledge graph and AI skills**: a graph of the ecosystem and skills for agents working across repositories.
- **Version and release tooling**: pin checks, release and dependency-update recipes.

## Architecture

```
  ┌──────────────────────────────────────────────────────────────────┐
  │ labs64.io-workspace      justfile · dev container · scripts      │
  └───────┬──────────────────────────────────────────────────────────┘
          │ just clone                          │ just up
  ┌───────▼─────────────────────────────┐ ┌─────▼────────────────────────────┐
  │ ../ every ecosystem repository      │ │ builder container                │
  │ auditflow · checkout · helm-charts  │ │ builds first-party images        │
  │ payment-gateway · authproxy · …     │ └─────┬────────────────────────────┘
  └─────────────────────────────────────┘       │ push
                                          ┌─────▼────────────┐   ┌────────────┐
                                          │ k3d + registry   │──►│ platform   │
                                          │ (Docker)         │   │ gateway.   │
                                          └──────────────────┘   │ localhost  │
                                                                 └────────────┘
```

## Is this the right place to start?

| You want to… | Start here |
|---|---|
| **See Labs64.IO running** and call an API | You do not need this workspace: the [Quickstart](https://labs64.io/docs/getting-started/quickstart.html) installs published images in about five minutes |
| **Try one service** without Kubernetes | [Run one module locally](https://labs64.io/docs/getting-started/run-one-module-locally.html) |
| **Deploy for your team** on AWS, Azure, Google Cloud or your own cluster | [Deploy to your Kubernetes cluster](https://labs64.io/docs/getting-started/deploy-to-kubernetes.html) |
| **Change the code**, build from source, contribute | You are in the right place |

## Using Workspace with AI agents

Workspace is where an agent gets the same environment a human contributor has.

- **One entry point.** Every build, deploy and test is a `just` recipe run from `labs64.io-workspace/`; `just` lists them by group, and `just helm-charts` / `just tests` list those repositories' recipes. The same name means the same thing in every repository ([`docs/justfiles.md`](docs/justfiles.md)).
- **Cross-repo knowledge.** The workspace carries a knowledge graph and skills so an agent can follow a change across repositories.
- **Verify before proposing.** `just ci` in the repository you changed runs what its pull-request check runs; `just smoke` checks the running platform.
- **Working on the code with an agent?** [`AGENTS.md`](AGENTS.md) and [`CLAUDE.md`](CLAUDE.md) describe the layout and conventions.

## The Labs64.IO Ecosystem

Workspace is one module of the [Labs64.IO Ecosystem](https://labs64.io); [every module is documented here](https://labs64.io/docs/).

| Module | What it does | Link |
|---|---|---|
| **AuditFlow** | Audit-event routing pipeline | [labs64.io-auditflow](https://github.com/Labs64/labs64.io-auditflow) |
| **API Gateway** | Authenticating, policy-enforcing edge for all modules | [labs64.io-authproxy](https://github.com/Labs64/labs64.io-authproxy) |
| **Payment Gateway** | One API over multiple payment providers | [labs64.io-payment-gateway](https://github.com/Labs64/labs64.io-payment-gateway) |
| **Checkout** | Embeddable, brandable checkout | [labs64.io-checkout](https://github.com/Labs64/labs64.io-checkout) |
| **Customer Portal** | Customer self-service UI | [labs64.io-customer-portal](https://github.com/Labs64/labs64.io-customer-portal) |
| **Commons** | Shared Java and Python libraries | [labs64.io-commons](https://github.com/Labs64/labs64.io-commons) |
| **Helm Charts** | Kubernetes deployment for every module | [labs64.io-helm-charts](https://github.com/Labs64/labs64.io-helm-charts) |
| **Workspace** | Dev container and multi-repo tooling | [labs64.io-workspace](https://github.com/Labs64/labs64.io-workspace) |
| **Tests** | Cross-module regression suite | [labs64.io-tests](https://github.com/Labs64/labs64.io-tests) |
| **Docs** | Published documentation | [labs64.io-docs](https://github.com/Labs64/labs64.io-docs) |
| **NetLicensing** | Licensing-as-a-Service: license and entitlement management | [netlicensing.io](https://netlicensing.io) |
| **GuideChimp** | Interactive guided product tours | [labs64.com/guidechimp](https://www.labs64.com/guidechimp/) |

## Contributing

We would love your help. The workspace is where contributors spend their first hour, so every rough edge you smooth here helps the next person. Fork the repository, make your change on a branch, run the checks described in [`AGENTS.md`](AGENTS.md) and open a pull request. Not sure whether an idea fits? Open an issue first and we will talk it through; that is a perfectly good way to start.

## License

Everything in this repository is open source under the [Apache License 2.0](LICENSE): you can use it, change it and ship it commercially. The core of the *Labs64.IO Ecosystem* is free forever; community modules are Apache-2.0 licensed.

---

<p align="center">
  <a href="https://labs64.io"><img alt="Labs64.IO" src="https://labs64.io/docs/assets/images/labs64-logo.png" width="110"></a><br>
  <sub>Made by the <a href="https://labs64.io">Labs64</a> team and community.</sub>
</p>
