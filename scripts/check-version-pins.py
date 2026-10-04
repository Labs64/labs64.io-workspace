#!/usr/bin/env python3
"""Check that every version pin shared across files or repositories agrees.

Most pins in the ecosystem have exactly one owner (helmfile.yaml.gotmpl for chart
versions, labs64io-parent for the Java stack, tool-versions.env for the CLI toolchain).
A few cannot: a file that is unable to read its owner (devcontainer.json), or two
repositories that must hold the same value because they install the same thing on
different paths (helm-charts locally, devops on AWS). Those used to be kept together by
"keep in lockstep" comments. This is the gate that replaces the comments — no single
repository's CI can see the other side, so it runs here, across the whole checkout:

    scripts/check-version-pins.py
    just check-pins

Repositories that are not cloned are skipped, not failed: a partial checkout is normal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

problems: list[str] = []
notes: list[str] = []


def ok(what: str, value: str) -> None:
    print(f"  ok    {what:58} {value}")


def fail(message: str) -> None:
    problems.append(message)


def read(path: Path) -> str | None:
    return path.read_text() if path.is_file() else None


def first(pattern: str, text: str | None, flags: int = re.M) -> str | None:
    if text is None:
        return None
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def expect_equal(what: str, values: dict[str, str | None]) -> None:
    """All present values must be identical; absent ones (repo not cloned) are skipped."""
    present = {where: v for where, v in values.items() if v is not None}
    if len(present) < 2:
        return
    if len(set(present.values())) == 1:
        ok(what, next(iter(present.values())))
        return
    detail = "; ".join(f"{where} = {v}" for where, v in present.items())
    fail(f"{what} differs: {detail}")


def env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in (read(path) or "").splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m:
            values[m.group(1)] = m.group(2).strip().strip("\"'")
    return values


def helmfile_versions(text: str | None) -> dict[str, str]:
    """Release name -> pinned chart version, read straight from helmfile.yaml.gotmpl."""
    versions: dict[str, str] = {}
    current = None
    for line in (text or "").splitlines():
        m = re.match(r"^  - name:\s*(\S+)", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"^    version:\s*[\"']?([^\"'\s]+)", line)
        if m and current:
            versions[current] = m.group(1)
    return versions


def just_constant(text: str | None, name: str) -> str | None:
    return first(rf'^{name}\s*:=\s*"([^"]+)"', text)


# --- checks ---------------------------------------------------------------------


def check_toolchain(root: Path) -> None:
    ws = root / "labs64.io-workspace"
    tools = env_file(ws / "tool-versions.env")
    if not tools:
        fail("labs64.io-workspace/tool-versions.env is missing or empty")
        return

    # devcontainer.json cannot read the env file; it mirrors the feature-installed tools.
    raw = read(ws / ".devcontainer" / "devcontainer.json")
    if raw is not None:
        features = json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M)).get("features", {})

        def feature(name: str, key: str = "version") -> str | None:
            for ref, options in features.items():
                if f"/features/{name}:" in ref:
                    return str(options.get(key)) if key in options else None
            return None

        for label, tool, value in (
            ("helm", "HELM_VERSION", feature("kubectl-helm-minikube", "helm")),
            ("terraform", "TERRAFORM_VERSION", feature("terraform")),
            ("java", "JAVA_VERSION", feature("java")),
            ("node", "NODE_VERSION", feature("node")),
            ("python", "PYTHON_VERSION", feature("python")),
        ):
            expect_equal(
                f"{label}: tool-versions.env vs devcontainer.json",
                {"tool-versions.env": tools.get(tool), "devcontainer.json": value},
            )

    # Reusable workflow defaults are what CI builds with unless a caller overrides them.
    workflows = ws / ".github" / "workflows"
    for workflow, input_name, tool in (
        ("java-ci.yml", "java-version", "JAVA_VERSION"),
        ("maven-publish.yml", "java-version", "JAVA_VERSION"),
        ("docker-publish.yml", "java-version", "JAVA_VERSION"),
        ("python-ci.yml", "python-version", "PYTHON_VERSION"),
        ("vue-ci.yml", "node-version", "NODE_VERSION"),
    ):
        text = read(workflows / workflow)
        if text is None:
            continue
        doc = yaml.safe_load(text)
        # PyYAML reads the `on:` key as boolean True.
        triggers = doc.get("on", doc.get(True, {}))
        default = triggers["workflow_call"]["inputs"][input_name].get("default")
        expect_equal(
            f"{input_name} default in {workflow}",
            {"tool-versions.env": tools.get(tool), workflow: str(default)},
        )

    # Image bases must be the same runtime line the toolchain declares.
    for dockerfile in sorted(root.glob("labs64.io-*/**/Dockerfile")):
        if any(part in ("node_modules", "target", "_site") for part in dockerfile.parts):
            continue
        rel = dockerfile.relative_to(root).as_posix()
        for image, tool in (
            (r"eclipse-temurin", "JAVA_VERSION"),
            (r"python", "PYTHON_VERSION"),
            (r"node", "NODE_VERSION"),
        ):
            for found in re.findall(rf"^FROM\s+{image}:([0-9.]+)", dockerfile.read_text(), re.M):
                if found != tools.get(tool):
                    fail(f"{rel}: base image {image}:{found}, but tool-versions.env {tool}={tools.get(tool)}")

    # No workflow may carry a tool version of its own.
    hardcoded = re.compile(
        r"helm/helm/v\d|get-helm-\d\b.*DESIRED_VERSION=v\d|HELMFILE_VERSION=\d|K3D_VERSION=v?\d"
        r"|terraform_version:\s*[\"']?\d|helm-docs:v\d|helm-diff\S*\s+--version\s+v?\d"
        r"|k3d-io/k3d/main/|helm/helm/main/"
    )
    for workflow in sorted(root.glob("labs64.io-*/.github/workflows/*.yml")):
        for number, line in enumerate(workflow.read_text().splitlines(), 1):
            if hardcoded.search(line):
                fail(
                    f"{workflow.relative_to(root).as_posix()}:{number}: hard-coded or floating tool "
                    f"version — use .github/actions/setup-k8s-tools or tool-versions"
                )


def check_platform_lockstep(root: Path) -> None:
    charts = root / "labs64.io-helm-charts"
    devops_just = read(root / "labs64.io-devops" / "justfile")
    charts_just = read(charts / "justfile")
    helmfile = helmfile_versions(read(charts / "helmfile.yaml.gotmpl"))

    expect_equal(
        "External Secrets Operator chart",
        {
            "helm-charts helmfile (external-secrets)": helmfile.get("external-secrets"),
            "devops justfile ESO_CHART_VERSION": just_constant(devops_just, "ESO_CHART_VERSION"),
        },
    )
    expect_equal(
        "Keycloak (keycloakx) chart",
        {
            "helm-charts helmfile (keycloak)": helmfile.get("keycloak"),
            "devops justfile KEYCLOAK_CHART_VERSION": just_constant(devops_just, "KEYCLOAK_CHART_VERSION"),
        },
    )
    expect_equal(
        "Gateway API CRDs",
        {
            "helm-charts justfile": just_constant(charts_just, "GATEWAY_API_VERSION"),
            "helm-charts install.sh": first(
                r'^GATEWAY_API_VERSION="\$\{LABS64_GATEWAY_API_VERSION:-([^}]+)\}"', read(charts / "install.sh")
            ),
            "devops justfile": just_constant(devops_just, "GATEWAY_API_VERSION"),
        },
    )

    # The umbrella bundles the same infrastructure charts the local helmfile installs.
    umbrella = read(charts / "charts" / "labs64io-ecosystem" / "Chart.yaml")
    if umbrella is not None:
        deps = {d["name"]: str(d["version"]) for d in yaml.safe_load(umbrella).get("dependencies", [])}
        for release, dependency in (("traefik", "traefik"), ("postgresql", "postgresql"), ("redis", "valkey")):
            expect_equal(
                f"{dependency} chart: helmfile vs umbrella Chart.yaml",
                {f"helmfile ({release})": helmfile.get(release), "labs64io-ecosystem": deps.get(dependency)},
            )


def check_cerbos(root: Path) -> None:
    image = r"ghcr\.io/cerbos/cerbos:([0-9][^\s\"']*)"
    expect_equal(
        "Cerbos PDP",
        {
            "helm-charts charts/authz-pdp appVersion": first(
                r'^appVersion:\s*"?([^"\s]+)', read(root / "labs64.io-helm-charts/charts/authz-pdp/Chart.yaml")
            ),
            "commons auth-policy-cerbos/validate.sh": first(
                r'^CERBOS_VERSION="([^"]+)"', read(root / "labs64.io-commons/auth-policy-cerbos/validate.sh")
            ),
            "auditflow docker-compose.yml": first(image, read(root / "labs64.io-auditflow/docker-compose.yml")),
            "checkout docker-compose.dev.yml": first(
                image, read(root / "labs64.io-checkout/checkout-be/docker-compose.dev.yml")
            ),
            "payment-gateway docker-compose.yml": first(
                image, read(root / "labs64.io-payment-gateway/payment-gateway-be/docker-compose.yml")
            ),
        },
    )


def check_opentelemetry(root: Path) -> None:
    agents = {}
    for dockerfile in sorted(root.glob("labs64.io-*/**/Dockerfile")):
        version = first(r"^ARG OTEL_JAVAAGENT_VERSION=(\S+)", dockerfile.read_text())
        if version:
            agents[dockerfile.relative_to(root).as_posix()] = version
    expect_equal("OpenTelemetry Java agent", agents)

    python: dict[str, str] = {}
    for requirements in sorted(root.glob("labs64.io-*/**/requirements-otel.txt")):
        lines = sorted(
            line.strip()
            for line in requirements.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        python[requirements.relative_to(root).as_posix()] = " ".join(lines)
    if len(set(python.values())) > 1:
        fail("OpenTelemetry Python requirements differ between: " + ", ".join(python))
    elif len(python) > 1:
        ok("OpenTelemetry Python requirements", f"{len(python)} identical files")


def check_java(root: Path) -> None:
    poms = [
        p
        for p in sorted(root.glob("labs64.io-*/**/pom.xml"))
        if not any(part in ("target", "node_modules") for part in p.parts)
    ]
    parent_pins: dict[str, str] = {}
    for pom in poms:
        rel = pom.relative_to(root).as_posix()
        text = pom.read_text()
        flat = re.sub(r"<!--.*?-->", "", text, flags=re.S)

        if "spring-boot-starter-parent" in flat and not rel.endswith("labs64io-parent/pom.xml"):
            fail(f"{rel}: declares spring-boot-starter-parent — inherit io.labs64:labs64io-parent instead")

        # The project's own <version> (not the one inside <parent>) must not be a literal.
        without_parent = re.sub(r"<parent>.*?</parent>", "", flat, flags=re.S)
        head = without_parent.split("<properties>")[0].split("<dependencies>")[0].split("<modules>")[0]
        own = first(r"<version>([^<]+)</version>", head, 0)
        if own is not None and own != "${revision}":
            fail(f"{rel}: hard-coded <version>{own}</version> — declare ${{revision}} (the release tag sets it)")

        parent = re.search(
            r"<parent>.*?<artifactId>labs64io-parent</artifactId>\s*<version>([^<]+)</version>.*?</parent>", flat, re.S
        )
        if parent and parent.group(1) != "${revision}":
            parent_pins[rel] = parent.group(1)

    for rel, version in parent_pins.items():
        if version.endswith("-SNAPSHOT"):
            notes.append(f"{rel}: labs64io-parent {version} — a release build of this module will be refused")
    if parent_pins:
        ok("labs64io-parent pinned by", f"{len(parent_pins)} module poms")

    pg = root / "labs64.io-payment-gateway"
    auditflow_api = first(
        r"<auditflow-api\.version>([^<]+)</auditflow-api\.version>", read(pg / "payment-gateway-be/pom.xml")
    )
    if auditflow_api and auditflow_api.endswith("-SNAPSHOT"):
        notes.append(
            f"labs64.io-payment-gateway: auditflow-api {auditflow_api} — a release build of payment-gateway will be refused"
        )
    # payment-gateway-api is a standalone pom, so it names the commons version it runs
    # its schema generator from; it must be the commons release the backend inherits.
    expect_equal(
        "payment-gateway: commons version (api vs backend parent)",
        {
            "payment-gateway-api openapi-schema-generator.version": first(
                r"<openapi-schema-generator\.version>([^<]+)<", read(pg / "payment-gateway-api/pom.xml")
            ),
            "payment-gateway-be labs64io-parent": parent_pins.get(
                "labs64.io-payment-gateway/payment-gateway-be/pom.xml"
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default="..", help="ecosystem root (default: ..)")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not (root / "labs64.io-workspace").is_dir():
        raise SystemExit(f"no labs64.io-workspace under {root}")

    for check in (check_toolchain, check_platform_lockstep, check_cerbos, check_opentelemetry, check_java):
        check(root)

    if notes:
        print()
        for note in notes:
            print(f"  note  {note}")
    if problems:
        prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") else "  FAIL  "
        print()
        for problem in problems:
            print(f"{prefix}{problem}")
        print(f"\ncheck-version-pins: {len(problems)} problem(s)")
        return 1
    print("\ncheck-version-pins: clean — every shared pin agrees")
    return 0


if __name__ == "__main__":
    sys.exit(main())
