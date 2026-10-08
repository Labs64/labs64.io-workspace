#!/usr/bin/env python3
"""Check that every version pin shared across files or repositories agrees.

Most pins in the ecosystem have exactly one owner (helmfile.yaml.gotmpl for chart
versions, labs64io-parent for the Java stack, tool-versions.env for the CLI toolchain,
justfile.versions in labs64.io-helm-charts and labs64.io-devops for everything else those two
pin). A few cannot: a file that is unable to read its owner (devcontainer.json), or two
repositories that must hold the same value because they install the same thing on
different paths (helm-charts locally, devops on AWS). Those used to be kept together by
"keep in lockstep" comments. This is the gate that replaces the comments — no single
repository's CI can see the other side, so it runs here, across the whole checkout:

    scripts/check-version-pins.py
    just check-pins

It also enforces release order. A service pins released versions of commons
(labs64io-parent) and of auditflow-api; a tagged build refuses -SNAPSHOT inputs, and a pin on
a version nobody released cannot resolve. Both fail here, naming the repository to release
first, so the mistake is caught on master instead of at the first release tag.

Repositories that are not cloned are skipped, not failed: a partial checkout is normal on a
developer machine. CI passes --strict instead, which fails when a repository the checks read is
missing — otherwise a failed clone would turn the gate into a silently weaker one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

problems: list[str] = []
notes: list[str] = []

# Every repository at least one check reads. --strict requires all of them.
REQUIRED_REPOS = (
    "labs64.io-workspace",
    "labs64.io-helm-charts",
    "labs64.io-devops",
    "labs64.io-commons",
    "labs64.io-auditflow",
    "labs64.io-payment-gateway",
    "labs64.io-checkout",
    "labs64.io-authproxy",
    "labs64.io-customer-portal",
)


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


def tf_default(text: str | None, name: str) -> str | None:
    """Default of `variable "<name>"` in a Terraform variables file."""
    if text is None:
        return None
    m = re.search(rf'variable "{name}" \{{(.*?)(?=\nvariable "|\Z)', text, re.S)
    return first(r'^\s*default\s*=\s*"([^"]+)"', m.group(1) if m else None)


def _numeric(version: str | None) -> list[str]:
    """Leading numeric components of an image tag: '9.1-alpine' -> ['9', '1']."""
    m = re.match(r"\d+(?:\.\d+)*", version or "")
    return m.group(0).split(".") if m else []


def major(version: str | None) -> str | None:
    return _numeric(version)[0] if _numeric(version) else None


def minor_line(version: str | None) -> str | None:
    parts = _numeric(version)[:2]
    return ".".join(parts) if parts else None


def _git(cwd: Path | None, *args: str) -> subprocess.CompletedProcess | None:
    """Run git quietly and never prompt; None when git cannot run or times out."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


_tag_cache: dict[tuple[str, str], bool | None] = {}


def release_tag_exists(root: Path, repo: str, tag: str) -> bool | None:
    """Whether `repo` has release tag `tag` on its remote.

    The remote is the authority (a tag that only exists in a local clone was never released).
    When it cannot be reached, a local tag is accepted; otherwise the answer is None: unknown.
    """
    key = (repo, tag)
    if key in _tag_cache:
        return _tag_cache[key]
    checkout = root / repo
    cloned = (checkout / ".git").exists()
    url = None
    if cloned:
        origin = _git(checkout, "remote", "get-url", "origin")
        url = origin.stdout.strip() if origin and origin.returncode == 0 else None
    url = url or f"https://github.com/Labs64/{repo}.git"
    answer: bool | None = None
    remote = _git(None, "ls-remote", "--tags", url, f"refs/tags/{tag}")
    if remote and remote.returncode == 0:
        answer = bool(remote.stdout.strip())
    elif cloned:
        local = _git(checkout, "tag", "--list", tag)
        if local and local.returncode == 0 and local.stdout.strip():
            answer = True
    _tag_cache[key] = answer
    return answer


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


def platform_pins(root: Path) -> dict[str, dict[str, str | None]]:
    """Every platform pin, with each place this checkout states it.

    `--print-pins` prints this mapping as JSON, so tooling that installs the same charts and
    engines on another path (an operator's own infrastructure repository) can hold its pins
    against these without parsing the files itself. Engine versions are reduced to the line the
    places have to share: a major for PostgreSQL, major.minor for Valkey, RabbitMQ and Kubernetes.
    """
    charts = root / "labs64.io-helm-charts"
    helmfile = helmfile_versions(read(charts / "helmfile.yaml.gotmpl"))
    preflight = read(charts / "charts/preflight/values.yaml")
    compose = read(root / "labs64.io-auditflow/docker-compose.yml")
    return {
        "External Secrets Operator chart": {"helm-charts helmfile (external-secrets)": helmfile.get("external-secrets")},
        "Keycloak (keycloakx) chart": {"helm-charts helmfile (keycloak)": helmfile.get("keycloak")},
        "Traefik chart": {"helm-charts helmfile (traefik)": helmfile.get("traefik")},
        "OpenTelemetry Collector chart": {
            "helm-charts helmfile (opentelemetry-collector)": helmfile.get("opentelemetry-collector")
        },
        "Gateway API CRDs": {
            "helm-charts justfile.versions": just_constant(read(charts / "justfile.versions"), "GATEWAY_API_VERSION"),
            "helm-charts install.sh": first(
                r'^GATEWAY_API_VERSION="\$\{LABS64_GATEWAY_API_VERSION:-([^}]+)\}"', read(charts / "install.sh")
            ),
        },
        "Kubernetes minor": {
            "k3d/labs64io.yaml": first(r"^image:\s*rancher/k3s:v(\d+\.\d+)", read(charts / "k3d" / "labs64io.yaml")),
        },
        "PostgreSQL major": {
            "bitnami/postgresql chart (helmfile)": major(helmfile.get("postgresql")),
            "chart-libs _job.tpl": major(
                first(r"image:\s*postgres:(\d[^\s\"']*)", read(charts / "charts/chart-libs/templates/_job.tpl"))
            ),
            "preflight values": major(first(r"postgres:(\d[^\s\"']*)", preflight)),
            "keycloak override": major(
                first(r"image:\s*postgres:(\d[^\s\"']*)", read(charts / "overrides/keycloak/values.yaml"))
            ),
        },
        "Valkey line": {
            "preflight values": minor_line(first(r"valkey/valkey:(\d[^\s\"']*)", preflight)),
            "auditflow docker-compose": minor_line(first(r"valkey/valkey:(\d[^\s\"']*)", compose)),
        },
        "RabbitMQ line": {
            "overrides/rabbitmq chart": minor_line(
                first(r"tag:\s*(\d[^\s\"']*)", read(charts / "overrides/rabbitmq/chart/values.yaml"))
            ),
            "umbrella values": minor_line(
                first(r"tag:\s*\"(4\.[^\"]*)\"", read(charts / "charts/labs64io-ecosystem/values.yaml"))
            ),
            "auditflow docker-compose": minor_line(first(r"image:\s*rabbitmq:(\d[^\s\"']*)", compose)),
        },
        "curl image": {"preflight values": first(r"curlimages/curl:(\S+)", preflight)},
    }


def check_platform_lockstep(root: Path) -> None:
    charts = root / "labs64.io-helm-charts"
    devops_just = read(root / "labs64.io-devops" / "justfile.versions")
    charts_just = read(charts / "justfile.versions")
    helmfile = helmfile_versions(read(charts / "helmfile.yaml.gotmpl"))

    expect_equal(
        "External Secrets Operator chart",
        {
            "helm-charts helmfile (external-secrets)": helmfile.get("external-secrets"),
            "devops justfile.versions ESO_CHART_VERSION": just_constant(devops_just, "ESO_CHART_VERSION"),
        },
    )
    expect_equal(
        "Keycloak (keycloakx) chart",
        {
            "helm-charts helmfile (keycloak)": helmfile.get("keycloak"),
            "devops justfile.versions KEYCLOAK_CHART_VERSION": just_constant(devops_just, "KEYCLOAK_CHART_VERSION"),
        },
    )
    # Installed by helmfile locally and by `just traefik-install` / `just metrics-install` on AWS,
    # with the same overrides/ values files: one chart version on both paths.
    expect_equal(
        "Traefik chart",
        {
            "helm-charts helmfile (traefik)": helmfile.get("traefik"),
            "devops justfile.versions TRAEFIK_CHART_VERSION": just_constant(devops_just, "TRAEFIK_CHART_VERSION"),
        },
    )
    expect_equal(
        "OpenTelemetry Collector chart",
        {
            "helm-charts helmfile (opentelemetry-collector)": helmfile.get("opentelemetry-collector"),
            "devops justfile.versions OTEL_COLLECTOR_CHART_VERSION": just_constant(
                devops_just, "OTEL_COLLECTOR_CHART_VERSION"
            ),
        },
    )
    expect_equal(
        "Gateway API CRDs",
        {
            "helm-charts justfile.versions": just_constant(charts_just, "GATEWAY_API_VERSION"),
            "helm-charts install.sh": first(
                r'^GATEWAY_API_VERSION="\$\{LABS64_GATEWAY_API_VERSION:-([^}]+)\}"', read(charts / "install.sh")
            ),
            "devops justfile.versions": just_constant(devops_just, "GATEWAY_API_VERSION"),
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


def check_version_files(root: Path) -> None:
    """Versions live in justfile.versions / tool-versions.env, never back in a justfile."""
    constant = re.compile(r"^[A-Z0-9_]*VERSION\s*:=", re.M)
    for repo in ("labs64.io-helm-charts", "labs64.io-devops"):
        versions = read(root / repo / "justfile.versions")
        justfile = read(root / repo / "justfile")
        if versions is None:
            if justfile is not None:
                fail(f"{repo}/justfile.versions is missing — its pinned versions belong there")
            continue
        if justfile is not None and "import 'justfile.versions'" not in justfile:
            fail(f"{repo}/justfile does not import justfile.versions")
        for number, line in enumerate((justfile or "").splitlines(), 1):
            if constant.match(line):
                fail(f"{repo}/justfile:{number}: version constant outside justfile.versions — move it there")
        # Every pin in justfile.versions must be visible to Renovate: annotated on the line above.
        lines = versions.splitlines()
        for number, line in enumerate(lines, 1):
            if constant.match(line) and not (number > 1 and lines[number - 2].lstrip().startswith("# renovate:")):
                fail(f"{repo}/justfile.versions:{number}: {line.split(':=')[0].strip()} has no `# renovate:` annotation")
    ok("justfile.versions: imported, annotated, no constants in justfiles", "helm-charts, devops")


def check_data_stores(root: Path) -> None:
    """Engine lines that local/charts and the AWS Terraform path must agree on."""
    charts = root / "labs64.io-helm-charts"
    tfvars = read(root / "labs64.io-devops" / "terraform" / "variables.tf")
    devops_just = read(root / "labs64.io-devops" / "justfile.versions")
    helmfile = helmfile_versions(read(charts / "helmfile.yaml.gotmpl"))

    # Local Kubernetes tracks the EKS control plane.
    k3s = first(r"^image:\s*rancher/k3s:v(\d+\.\d+)", read(charts / "k3d" / "labs64io.yaml"))
    expect_equal(
        "Kubernetes minor: local k3s vs EKS",
        {"k3d/labs64io.yaml": k3s, "terraform eks_cluster_version": tf_default(tfvars, "eks_cluster_version")},
    )

    # PostgreSQL major.
    pg_chart = helmfile.get("postgresql")
    expect_equal(
        "PostgreSQL major",
        {
            "terraform rds_engine_version": tf_default(tfvars, "rds_engine_version"),
            "bitnami/postgresql chart (helmfile)": major(pg_chart),
            "chart-libs _job.tpl": major(first(r"image:\s*postgres:(\d[^\s\"']*)", read(charts / "charts/chart-libs/templates/_job.tpl"))),
            "preflight values": major(first(r"postgres:(\d[^\s\"']*)", read(charts / "charts/preflight/values.yaml"))),
            "keycloak override": major(first(r"image:\s*postgres:(\d[^\s\"']*)", read(charts / "overrides/keycloak/values.yaml"))),
        },
    )

    # Valkey / RabbitMQ minor line.
    expect_equal(
        "Valkey line: AWS ElastiCache vs local",
        {
            "terraform cache_engine_version": tf_default(tfvars, "cache_engine_version"),
            "preflight values": minor_line(first(r"valkey/valkey:(\d[^\s\"']*)", read(charts / "charts/preflight/values.yaml"))),
            "auditflow docker-compose": minor_line(
                first(r"valkey/valkey:(\d[^\s\"']*)", read(root / "labs64.io-auditflow/docker-compose.yml"))
            ),
        },
    )
    expect_equal(
        "RabbitMQ line: Amazon MQ vs local",
        {
            "terraform mq_engine_version": tf_default(tfvars, "mq_engine_version"),
            "overrides/rabbitmq chart": minor_line(first(r"tag:\s*(\d[^\s\"']*)", read(charts / "overrides/rabbitmq/chart/values.yaml"))),
            "umbrella values": minor_line(first(r"tag:\s*\"(4\.[^\"]*)\"", read(charts / "charts/labs64io-ecosystem/values.yaml"))),
            "auditflow docker-compose": minor_line(
                first(r"image:\s*rabbitmq:(\d[^\s\"']*)", read(root / "labs64.io-auditflow/docker-compose.yml"))
            ),
        },
    )

    # Utility images used by chart tests and jobs. Templates cannot be updated by Renovate, so
    # this is what notices when a bump reaches the values but not the templates.
    busybox: dict[str, str | None] = {}
    for rel in (
        "charts/chart-libs/templates/_tests.tpl",
        "charts/checkout/templates/tests/ui-test-connection.yaml",
        "charts/customer-portal/templates/tests/ui-test-connection.yaml",
        "charts/labs64io-ecosystem/values.yaml",
        "charts/preflight/values.yaml",
    ):
        found = set(re.findall(r"busybox:(\d[^\s\"']*)", read(charts / rel) or ""))
        if found:
            busybox[rel] = ",".join(sorted(found))
    busybox["overrides/opentelemetry operator"] = first(
        r"repository:\s*busybox\s*\n(?:\s*#.*\n)*\s*tag:\s*(\S+)",
        read(charts / "overrides/opentelemetry/values-operator.local.yaml"),
    )
    expect_equal("busybox image", busybox)
    expect_equal(
        "curl image: preflight vs devops canary/load test",
        {
            "preflight values": first(r"curlimages/curl:(\S+)", read(charts / "charts/preflight/values.yaml")),
            "devops justfile.versions CANARY_CURL_VERSION": just_constant(devops_just, "CANARY_CURL_VERSION"),
        },
    )


def check_cerbos(root: Path) -> None:
    image = r"ghcr\.io/cerbos/cerbos:([0-9][^\s\"']*)"
    expect_equal(
        "Cerbos PDP",
        {
            "helm-charts charts/authz-pdp appVersion": first(
                r'^appVersion:\s*"?([^"\s]+)', read(root / "labs64.io-helm-charts/charts/authz-pdp/Chart.yaml")
            ),
            # The digest in values.yaml wins over the tag at render time: the version it was taken
            # from must be the appVersion, or the chart deploys another Cerbos than it says.
            "helm-charts charts/authz-pdp values.yaml image.digest (renovate-digest version=)": first(
                r"renovate-digest:.*depName=ghcr\.io/cerbos/cerbos\s+version=(\S+)",
                read(root / "labs64.io-helm-charts/charts/authz-pdp/values.yaml"),
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


def check_collector_image(root: Path) -> None:
    """The collector image tag is the appVersion of the pinned collector chart, kept by hand.

    Renovate proposes the chart only, so a chart bump would leave the image on the old collector
    against a newer config schema. Each values file stamps the chart version its tag was taken from
    (`# chart-pin: opentelemetry-collector <chart version>` directly above `tag:`): the stamp must
    equal the helmfile's, so a chart bump fails here until someone has read the new appVersion.
    """
    charts = root / "labs64.io-helm-charts"
    chart = helmfile_versions(read(charts / "helmfile.yaml.gotmpl")).get("opentelemetry-collector")
    tags: dict[str, str | None] = {}
    for kind in ("local", "aws"):
        rel = f"overrides/opentelemetry/values-collector.{kind}.yaml"
        text = read(charts / rel)
        if text is None:
            continue
        m = re.search(r"^\s*#\s*chart-pin:\s*opentelemetry-collector\s+(\S+)\s*\n\s*tag:\s*[\"']?([0-9][^\s\"']*)", text, re.M)
        if not m:
            fail(f"labs64.io-helm-charts/{rel}: image.tag has no `# chart-pin: opentelemetry-collector <version>` line above it")
            continue
        stamp, tag = m.groups()
        tags[f"helm-charts {kind} collector values"] = tag
        if chart is not None and stamp != chart:
            fail(
                f"labs64.io-helm-charts/{rel}: image.tag {tag} was taken from collector chart {stamp}, but "
                f"helmfile.yaml.gotmpl pins {chart} — read that chart's appVersion, then set tag and chart-pin"
            )
    expect_equal("OpenTelemetry Collector image tag (local vs AWS)", tags)


def load_yaml(path: Path):
    """Parsed YAML of a values file, or None when it is absent, empty or not a mapping."""
    text = read(path)
    if text is None:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def _dig(doc, path: list[str]):
    for key in path:
        if not isinstance(doc, dict) or key not in doc:
            return None
        doc = doc[key]
    return doc


def _pinned_image_blocks(values) -> list[list[str]]:
    """Paths of the image blocks of a chart's values.yaml whose `digest` is set."""
    found: list[list[str]] = []

    def walk(node, path: list[str]) -> None:
        if not isinstance(node, dict):
            return
        if isinstance(node.get("digest"), str) and node["digest"]:
            found.append(path)
        for key, child in node.items():
            walk(child, path + [str(key)])

    walk(values, [])
    return found


def check_override_image_tags(root: Path) -> None:
    """A values file that sets an image tag must also say what happens to the chart's digest.

    The charts render `repository@digest` whenever `digest` is set, and the release pipeline sets
    it in values.yaml. An override that only sets `tag` (a local build: `tag: latest`) is then
    ignored without a word, and the pod asks the registry for the released digest: ImagePullBackOff
    on a local registry that never held it. Setting `digest` in the same block — `""` to follow the
    tag — makes the choice explicit.
    """
    charts = root / "labs64.io-helm-charts"
    if not (charts / "charts").is_dir():
        return
    umbrella_files = sorted((charts / "charts" / "labs64io-ecosystem").glob("values*.yaml"))
    checked = 0
    for chart_values in sorted((charts / "charts").glob("*/values.yaml")):
        chart = chart_values.parent.name
        pinned = _pinned_image_blocks(load_yaml(chart_values))
        if not pinned:
            continue
        # The chart's own override files, and the umbrella profiles (the chart is a key there).
        candidates = [(f, []) for f in sorted((charts / "overrides" / chart).glob("values*.yaml"))]
        candidates += [(f, [chart]) for f in umbrella_files]
        for file, prefix in candidates:
            if ".orig." in file.name:
                continue
            doc = load_yaml(file)
            for path in pinned:
                block = _dig(doc, prefix + path)
                if not isinstance(block, dict) or not block.get("tag"):
                    continue
                checked += 1
                if "digest" not in block:
                    where = ".".join(prefix + path)
                    fail(
                        f"{file.relative_to(root).as_posix()}: {where}.tag is set, but charts/{chart} pins "
                        f"{'.'.join(path)}.digest and a digest wins over the tag — add `digest: \"\"` next "
                        f"to the tag (or the digest you mean)"
                    )
    if checked:
        ok("image tag overrides state their digest", f"{checked} block(s)")


def check_traefik_rbac(root: Path) -> None:
    """The AWS Traefik values replace the chart's RBAC; the copy must follow the chart.

    overrides/traefik/values.aws.yaml switches the chart's RBAC off (its ClusterRole reads every
    Secret) and carries the chart's rules without that one. A chart bump can add a rule the copy
    lacks, and Traefik then fails to sync its providers. The file stamps the chart version the
    copy was compared with (`# chart-pin: traefik <version>` directly above `rbac:`): it must be
    the helmfile's version, so a bump fails here until the rules have been compared again.
    """
    charts = root / "labs64.io-helm-charts"
    rel = "overrides/traefik/values.aws.yaml"
    text = read(charts / rel)
    chart = helmfile_versions(read(charts / "helmfile.yaml.gotmpl")).get("traefik")
    doc = load_yaml(charts / rel)
    if text is None or chart is None or _dig(doc, ["rbac", "enabled"]) is not False:
        return  # absent, or the chart's own RBAC is in use: nothing was copied
    stamp = first(r"^#\s*chart-pin:\s*traefik\s+(\S+)\s*\nrbac:", text)
    if stamp is None:
        fail(f"labs64.io-helm-charts/{rel}: `rbac:` has no `# chart-pin: traefik <version>` line above it")
    elif stamp != chart:
        fail(
            f"labs64.io-helm-charts/{rel}: the replacement RBAC was compared with traefik chart {stamp}, but "
            f"helmfile.yaml.gotmpl pins {chart} — compare it with that chart's ClusterRole (the file says "
            f"how), then set chart-pin"
        )
    else:
        ok("Traefik replacement RBAC compared with chart", stamp)


def check_baseline_policy_exclusions(root: Path) -> None:
    """The namespace baseline must not re-open what a chart's NetworkPolicy closes.

    labs64.io-devops/kubernetes/network-policies/labs64io.yaml holds fallback allow rules for pods
    without a chart policy. NetworkPolicies add up, so a chart that narrows its own ingress
    (networkPolicy.ingressFrom / ingressPorts) only gets what it asks for if the fallbacks exclude
    it (`app.kubernetes.io/name NotIn [...]`). A name excluded without need is the dangerous
    direction: that module is left with the default-deny unless its chart policy is enabled.
    """
    charts = root / "labs64.io-helm-charts" / "charts"
    baseline = read(root / "labs64.io-devops" / "kubernetes" / "network-policies" / "labs64io.yaml")
    if baseline is None or not charts.is_dir():
        return
    aws = load_yaml(charts / "labs64io-ecosystem" / "values.aws.yaml") or {}
    umbrella = load_yaml(charts / "labs64io-ecosystem" / "values.yaml") or {}
    narrowed: set[str] = set()
    enabled: dict[str, bool] = {}
    for chart_values in sorted(charts.glob("*/values.yaml")):
        chart = chart_values.parent.name
        policy: dict = {}
        for source in (_dig(load_yaml(chart_values), ["networkPolicy"]), _dig(umbrella, [chart, "networkPolicy"]),
                       _dig(aws, [chart, "networkPolicy"])):
            if isinstance(source, dict):
                policy.update(source)
        if policy.get("ingressFrom") or policy.get("ingressPorts"):
            narrowed.add(chart)
        enabled[chart] = policy.get("enabled") is True

    try:
        policies = [d for d in yaml.safe_load_all(baseline) if isinstance(d, dict)]
    except yaml.YAMLError as error:
        fail(f"labs64.io-devops/kubernetes/network-policies/labs64io.yaml is not valid YAML: {error}")
        return
    where = "labs64.io-devops/kubernetes/network-policies/labs64io.yaml"
    before = len(problems)
    excluded_anywhere: set[str] = set()
    for policy in policies:
        spec = policy.get("spec") or {}
        selector = spec.get("podSelector") or {}
        if policy.get("kind") != "NetworkPolicy" or not spec.get("ingress") or selector.get("matchLabels"):
            continue  # the default-deny, or a rule for named pods: not a fallback for "every pod"
        excluded = {
            value
            for expression in selector.get("matchExpressions") or []
            if expression.get("key") == "app.kubernetes.io/name" and expression.get("operator") == "NotIn"
            for value in expression.get("values") or []
        }
        excluded_anywhere |= excluded
        name = (policy.get("metadata") or {}).get("name")
        for chart in sorted(narrowed - excluded):
            fail(
                f"{where}: {name} selects the {chart} pods, whose chart narrows its ingress "
                f"(networkPolicy.ingressFrom / ingressPorts) — policies add up, so this rule re-opens it; "
                f"add {chart} to the NotIn list of its podSelector"
            )
        for chart in sorted(excluded - narrowed):
            fail(
                f"{where}: {name} excludes {chart}, but charts/{chart} does not narrow its ingress — "
                f"remove it from the NotIn list (an excluded module without its own policy is unreachable)"
            )
    for chart in sorted(narrowed & excluded_anywhere):
        if not enabled.get(chart):
            fail(
                f"{where} excludes {chart} from the fallback rules, but its NetworkPolicy is not enabled in "
                f"charts/labs64io-ecosystem/values.aws.yaml — on AWS only the default-deny would apply to it"
            )
    if narrowed and len(problems) == before:
        ok("baseline policies leave narrowed charts alone", ", ".join(sorted(narrowed)))


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


def check_release_order(root: Path, pins: list[tuple[str, str, str, str]]) -> None:
    """A pin on a Labs64 artifact must be a real release, and that release must exist.

    Release order is commons, then auditflow (auditflow-api), then the services that pin
    them. Renovate cannot help before the first release: it only proposes versions it finds
    on Nexus, so a pin on an unreleased version has to be fixed by hand.
    """
    for where, what, version, owner in pins:
        if version.endswith("-SNAPSHOT"):
            fail(
                f"{where}: {what} is pinned to {version} — a tagged build refuses -SNAPSHOT inputs, so this "
                f"commit cannot be released. Release {owner} first, then pin that version "
                f"(Renovate proposes it once the release exists)"
            )
            continue
        exists = release_tag_exists(root, owner, version)
        if exists is False:
            fail(f"{where}: {what} is pinned to {version}, but {owner} has no release tag {version} — release {owner} first")
        elif exists is None:
            notes.append(f"{where}: could not confirm that {owner} released {version} (remote unreachable)")
        else:
            ok(f"{what} {version} released by {owner}", where)


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

    if parent_pins:
        ok("labs64io-parent pinned by", f"{len(parent_pins)} module poms")

    pg = root / "labs64.io-payment-gateway"
    auditflow_api = first(
        r"<auditflow-api\.version>([^<]+)</auditflow-api\.version>", read(pg / "payment-gateway-be/pom.xml")
    )
    schema_generator = first(
        r"<openapi-schema-generator\.version>([^<]+)<", read(pg / "payment-gateway-api/pom.xml")
    )

    # (where, what, pinned version, repository that releases it)
    pins = [(rel, "labs64io-parent", v, "labs64.io-commons") for rel, v in parent_pins.items()]
    if auditflow_api:
        pins.append(("labs64.io-payment-gateway/payment-gateway-be/pom.xml", "auditflow-api", auditflow_api, "labs64.io-auditflow"))
    if schema_generator:
        pins.append(
            ("labs64.io-payment-gateway/payment-gateway-api/pom.xml", "openapi-schema-generator", schema_generator, "labs64.io-commons")
        )
    check_release_order(root, pins)

    # payment-gateway-api is a standalone pom, so it names the commons version it runs
    # its schema generator from; it must be the commons release the backend inherits.
    expect_equal(
        "payment-gateway: commons version (api vs backend parent)",
        {
            "payment-gateway-api openapi-schema-generator.version": schema_generator,
            "payment-gateway-be labs64io-parent": parent_pins.get(
                "labs64.io-payment-gateway/payment-gateway-be/pom.xml"
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default="..", help="ecosystem root (default: ..)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when a repository the checks read is not present (CI); default is to skip it",
    )
    parser.add_argument(
        "--print-pins",
        action="store_true",
        help="print the platform pins as JSON (pin -> place -> value) and exit, without checking",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not (root / "labs64.io-workspace").is_dir():
        raise SystemExit(f"no labs64.io-workspace under {root}")

    if args.print_pins:
        print(json.dumps(platform_pins(root), indent=2, sort_keys=True))
        return 0

    if args.strict:
        for repo in REQUIRED_REPOS:
            if not (root / repo).is_dir():
                fail(f"--strict: {repo} is not present under {root}, so its checks did not run")

    for check in (
        check_toolchain,
        check_version_files,
        check_platform_lockstep,
        check_data_stores,
        check_cerbos,
        check_collector_image,
        check_override_image_tags,
        check_traefik_rbac,
        check_baseline_policy_exclusions,
        check_opentelemetry,
        check_java,
    ):
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
