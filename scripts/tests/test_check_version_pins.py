"""Tests for scripts/check-version-pins.py.

A gate nobody tests reports "clean" forever. Each test builds a small synthetic ecosystem
(only the files a check needs — absent repositories are skipped by design), proves the
baseline passes, then plants exactly one kind of drift and asserts it is reported.

Run: pytest scripts/tests/test_check_version_pins.py -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-version-pins.py"

TOOLS = "HELM_VERSION=4.3.0\nTERRAFORM_VERSION=1.16.5\nJAVA_VERSION=25\nNODE_VERSION=26\nPYTHON_VERSION=3.14\n"

HELMFILE = """releases:
  - name: external-secrets
    chart: oci://ghcr.io/external-secrets/charts/external-secrets
    version: 2.11.0
  - name: keycloak
    chart: oci://ghcr.io/codecentric/helm-charts/keycloakx
    version: 7.3.2
  - name: postgresql
    chart: bitnami/postgresql
    version: 18.12.4
"""

CHARTS_VERSIONS = """# renovate: datasource=github-releases depName=kubernetes-sigs/gateway-api
GATEWAY_API_VERSION := "v1.6.2"
"""


K3D = "kind: Simple\nimage: rancher/k3s:v1.36.5-k3s1\n"
IMPORTING_JUSTFILE = "import 'justfile.versions'\n\ndefault:\n    @just --list\n"


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def ecosystem(root: Path) -> Path:
    write(root, "labs64.io-workspace/tool-versions.env", TOOLS)
    write(root, "labs64.io-helm-charts/helmfile.yaml.gotmpl", HELMFILE)
    write(root, "labs64.io-helm-charts/justfile", IMPORTING_JUSTFILE)
    write(root, "labs64.io-helm-charts/justfile.versions", CHARTS_VERSIONS)
    write(root, "labs64.io-helm-charts/k3d/labs64io.yaml", K3D)
    return root


def run(root: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *flags], capture_output=True, text=True
    )


def replace(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text()
    assert old in text, f"fixture drifted: {old!r} not in {rel}"
    path.write_text(text.replace(old, new))


def test_consistent_ecosystem_is_clean(tmp_path):
    proc = run(ecosystem(tmp_path))
    assert proc.returncode == 0, proc.stdout
    assert "clean" in proc.stdout


def test_missing_repositories_are_skipped_not_failed(tmp_path):
    write(tmp_path, "labs64.io-workspace/tool-versions.env", TOOLS)
    assert run(tmp_path).returncode == 0


def test_missing_workspace_is_an_error(tmp_path):
    proc = run(tmp_path)
    assert proc.returncode != 0


def test_version_constant_in_justfile_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    (root / "labs64.io-helm-charts/justfile").write_text(IMPORTING_JUSTFILE + 'K6_VERSION := "2.3.0"\n')
    proc = run(root)
    assert proc.returncode == 1
    assert "version constant outside justfile.versions" in proc.stdout


def test_pin_without_renovate_annotation_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    replace(root, "labs64.io-helm-charts/justfile.versions", "# renovate: datasource=github-releases depName=kubernetes-sigs/gateway-api\n", "")
    proc = run(root)
    assert proc.returncode == 1
    assert "GATEWAY_API_VERSION has no `# renovate:` annotation" in proc.stdout


def test_justfile_that_does_not_import_the_versions_file_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    (root / "labs64.io-helm-charts/justfile").write_text("default:\n    @just --list\n")
    proc = run(root)
    assert proc.returncode == 1
    assert "does not import justfile.versions" in proc.stdout


def test_versions_file_missing_while_justfile_exists_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    (root / "labs64.io-helm-charts/justfile.versions").unlink()
    proc = run(root)
    assert proc.returncode == 1
    assert "justfile.versions is missing" in proc.stdout


def test_hardcoded_tool_version_in_a_workflow_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    write(
        root,
        "labs64.io-tests/.github/workflows/ci.yml",
        "jobs:\n  a:\n    steps:\n      - run: curl -fsSL https://raw.githubusercontent.com/helm/helm/v4.1.0/scripts/get-helm-4\n",
    )
    proc = run(root)
    assert proc.returncode == 1
    assert "hard-coded or floating tool version" in proc.stdout


def test_floating_k3d_installer_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    write(
        root,
        "labs64.io-tests/.github/workflows/ci.yml",
        "jobs:\n  a:\n    steps:\n      - run: curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash\n",
    )
    assert run(root).returncode == 1


POM = """<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>io.labs64</groupId>
    <artifactId>labs64io-parent</artifactId>
    <version>0.0.0-SNAPSHOT</version>
    <relativePath />
  </parent>
  <groupId>io.labs64</groupId>
  <artifactId>demo</artifactId>
  <version>${revision}</version>
</project>
"""


def release_repo(root: Path, repo: str, remote_tags: tuple[str, ...] = (), local_tags: tuple[str, ...] = ()) -> None:
    """A cloned repository whose origin is a local bare repository holding `remote_tags`.

    `local_tags` exist only in the clone: tagged, never released.
    """
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    remote = root / ".remotes" / f"{repo}.git"  # not labs64.io-*, so the checker never globs it
    remote.parent.mkdir(exist_ok=True)
    subprocess.run([*git, "init", "-q", "--bare", str(remote)], check=True)
    work = root / repo
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([*git, "init", "-q"], cwd=work, check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], cwd=work, check=True)
    subprocess.run([*git, "remote", "add", "origin", str(remote)], cwd=work, check=True)
    for tag in (*remote_tags, *local_tags):
        subprocess.run([*git, "tag", tag], cwd=work, check=True)
    for tag in remote_tags:
        subprocess.run([*git, "push", "-q", "origin", f"refs/tags/{tag}"], cwd=work, check=True)


def pinned(version: str) -> str:
    return POM.replace("<version>0.0.0-SNAPSHOT</version>", f"<version>{version}</version>")


PG_BE_POM = POM.replace("<artifactId>demo</artifactId>", "<artifactId>payment-gateway</artifactId>").replace(
    "<version>0.0.0-SNAPSHOT</version>", "<version>0.0.4</version>"
).replace("</project>", "  <properties><auditflow-api.version>AUDITFLOW_API</auditflow-api.version></properties>\n</project>")


def test_snapshot_pin_is_rejected_and_names_the_repository_to_release_first(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-demo/demo-be/pom.xml", POM)
    proc = run(root)
    assert proc.returncode == 1
    assert "labs64io-parent is pinned to 0.0.0-SNAPSHOT" in proc.stdout
    assert "Release labs64.io-commons first" in proc.stdout


def test_pin_on_a_released_version_is_clean(tmp_path):
    root = ecosystem(tmp_path)
    release_repo(root, "labs64.io-commons", remote_tags=("0.0.4",))
    write(root, "labs64.io-demo/demo-be/pom.xml", pinned("0.0.4"))
    proc = run(root)
    assert proc.returncode == 0, proc.stdout
    assert "labs64io-parent 0.0.4 released by labs64.io-commons" in proc.stdout


def test_pin_on_a_version_nobody_released_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    release_repo(root, "labs64.io-commons", remote_tags=("0.0.3",))
    write(root, "labs64.io-demo/demo-be/pom.xml", pinned("0.0.4"))
    proc = run(root)
    assert proc.returncode == 1
    assert "labs64.io-commons has no release tag 0.0.4" in proc.stdout


def test_a_tag_that_only_exists_locally_is_not_a_release(tmp_path):
    root = ecosystem(tmp_path)
    release_repo(root, "labs64.io-commons", local_tags=("0.0.4",))
    write(root, "labs64.io-demo/demo-be/pom.xml", pinned("0.0.4"))
    proc = run(root)
    assert proc.returncode == 1
    assert "has no release tag 0.0.4" in proc.stdout


def test_unreachable_remote_is_a_note_not_a_failure(tmp_path):
    root = ecosystem(tmp_path)
    release_repo(root, "labs64.io-commons")
    subprocess.run(
        ["git", "remote", "set-url", "origin", str(tmp_path / "does-not-exist.git")],
        cwd=root / "labs64.io-commons",
        check=True,
    )
    write(root, "labs64.io-demo/demo-be/pom.xml", pinned("0.0.4"))
    proc = run(root)
    assert proc.returncode == 0, proc.stdout
    assert "could not confirm that labs64.io-commons released 0.0.4" in proc.stdout


def test_auditflow_api_pin_must_be_released_by_auditflow(tmp_path):
    root = ecosystem(tmp_path)
    release_repo(root, "labs64.io-commons", remote_tags=("0.0.4",))
    release_repo(root, "labs64.io-auditflow", remote_tags=("0.0.18",))
    be = "labs64.io-payment-gateway/payment-gateway-be/pom.xml"
    write(root, be, PG_BE_POM.replace("AUDITFLOW_API", "0.0.18"))
    assert run(root).returncode == 0
    write(root, be, PG_BE_POM.replace("AUDITFLOW_API", "0.0.19"))
    proc = run(root)
    assert proc.returncode == 1
    assert "auditflow-api is pinned to 0.0.19, but labs64.io-auditflow has no release tag 0.0.19" in proc.stdout
    write(root, be, PG_BE_POM.replace("AUDITFLOW_API", "0.0.0-SNAPSHOT"))
    assert "Release labs64.io-auditflow first" in run(root).stdout


def test_pom_with_hardcoded_version_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-demo/demo-be/pom.xml", POM.replace("<version>${revision}</version>", "<version>1.2.3</version>"))
    proc = run(root)
    assert proc.returncode == 1
    assert "hard-coded <version>1.2.3</version>" in proc.stdout


def test_pom_declaring_the_spring_boot_parent_directly_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    boot = POM.replace(
        "<groupId>io.labs64</groupId>\n    <artifactId>labs64io-parent</artifactId>\n    <version>0.0.0-SNAPSHOT</version>",
        "<groupId>org.springframework.boot</groupId>\n    <artifactId>spring-boot-starter-parent</artifactId>\n    <version>4.1.1</version>",
    )
    write(root, "labs64.io-demo/demo-be/pom.xml", boot)
    proc = run(root)
    assert proc.returncode == 1
    assert "inherit io.labs64:labs64io-parent instead" in proc.stdout


def test_cerbos_drift_between_chart_and_compose(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-helm-charts/charts/authz-pdp/Chart.yaml", 'appVersion: "0.56.0"\n')
    write(root, "labs64.io-auditflow/docker-compose.yml", "services:\n  c:\n    image: ghcr.io/cerbos/cerbos:0.55.0\n")
    proc = run(root)
    assert proc.returncode == 1
    assert "Cerbos PDP differs" in proc.stdout


def test_cerbos_digest_annotation_must_name_the_appversion(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-helm-charts/charts/authz-pdp/Chart.yaml", 'appVersion: "0.57.0"\n')
    write(
        root,
        "labs64.io-helm-charts/charts/authz-pdp/values.yaml",
        "image:\n  # renovate-digest: datasource=docker depName=ghcr.io/cerbos/cerbos version=0.56.0\n  digest: sha256:" + "a" * 64 + "\n",
    )
    proc = run(root)
    assert proc.returncode == 1
    assert "Cerbos PDP differs" in proc.stdout


COLLECTOR_VALUES = "image:\n  # chart-pin: opentelemetry-collector 0.175.0\n  tag: 0.161.0\n"


def collector_ecosystem(root: Path) -> Path:
    ecosystem(root)
    replace(
        root,
        "labs64.io-helm-charts/helmfile.yaml.gotmpl",
        "releases:\n",
        "releases:\n  - name: opentelemetry-collector\n    version: 0.175.0\n",
    )
    for kind in ("local", "aws"):
        write(root, f"labs64.io-helm-charts/overrides/opentelemetry/values-collector.{kind}.yaml", COLLECTOR_VALUES)
    return root


def test_collector_image_pin_is_clean_when_stamped_for_the_pinned_chart(tmp_path):
    proc = run(collector_ecosystem(tmp_path))
    assert proc.returncode == 0, proc.stdout
    assert "OpenTelemetry Collector image tag" in proc.stdout


def test_collector_chart_bump_without_rereading_the_appversion_is_rejected(tmp_path):
    root = collector_ecosystem(tmp_path)
    replace(root, "labs64.io-helm-charts/helmfile.yaml.gotmpl", "version: 0.175.0", "version: 0.176.0")
    proc = run(root)
    assert proc.returncode == 1
    assert "was taken from collector chart 0.175.0" in proc.stdout


def test_collector_image_tag_must_match_between_local_and_aws(tmp_path):
    root = collector_ecosystem(tmp_path)
    replace(root, "labs64.io-helm-charts/overrides/opentelemetry/values-collector.aws.yaml", "tag: 0.161.0", "tag: 0.160.0")
    proc = run(root)
    assert proc.returncode == 1
    assert "OpenTelemetry Collector image tag (local vs AWS) differs" in proc.stdout


def test_collector_image_tag_without_a_chart_pin_stamp_is_rejected(tmp_path):
    root = collector_ecosystem(tmp_path)
    write(root, "labs64.io-helm-charts/overrides/opentelemetry/values-collector.local.yaml", "image:\n  tag: 0.161.0\n")
    proc = run(root)
    assert proc.returncode == 1
    assert "has no `# chart-pin: opentelemetry-collector <version>` line" in proc.stdout


PINNED_CHART = 'image:\n  repository: labs64/auditflow\n  tag: ""\n  digest: "sha256:' + "b" * 64 + '"\n'
LOCAL_OVERRIDE = "image:\n  repository: localhost:5005/auditflow\n  tag: latest\n"


def pinned_chart(root: Path, override: str = LOCAL_OVERRIDE + '  digest: ""\n') -> Path:
    ecosystem(root)
    write(root, "labs64.io-helm-charts/charts/auditflow/values.yaml", PINNED_CHART)
    write(root, "labs64.io-helm-charts/overrides/auditflow/values.local.yaml", override)
    return root


def test_override_that_sets_tag_and_clears_the_digest_is_clean(tmp_path):
    proc = run(pinned_chart(tmp_path))
    assert proc.returncode == 0, proc.stdout
    assert "image tag overrides state their digest" in proc.stdout


def test_override_that_sets_only_a_tag_on_a_pinned_image_is_rejected(tmp_path):
    proc = run(pinned_chart(tmp_path, LOCAL_OVERRIDE))
    assert proc.returncode == 1
    assert "overrides/auditflow/values.local.yaml: image.tag is set" in proc.stdout
    assert "a digest wins over the tag" in proc.stdout


def test_override_that_leaves_the_pinned_image_alone_is_clean(tmp_path):
    proc = run(pinned_chart(tmp_path, "replicaCount: 1\n"))
    assert proc.returncode == 0, proc.stdout


def test_umbrella_profile_that_sets_only_a_tag_on_a_pinned_image_is_rejected(tmp_path):
    root = pinned_chart(tmp_path)
    write(root, "labs64.io-helm-charts/charts/labs64io-ecosystem/values.demo.yaml", "auditflow:\n  image:\n    tag: edge\n")
    proc = run(root)
    assert proc.returncode == 1
    assert "values.demo.yaml: auditflow.image.tag is set" in proc.stdout


TRAEFIK_AWS = "providers: {}\n# chart-pin: traefik 41.6.1\nrbac:\n  enabled: false\nextraObjects: []\n"


def traefik_ecosystem(root: Path, values: str = TRAEFIK_AWS) -> Path:
    ecosystem(root)
    replace(root, "labs64.io-helm-charts/helmfile.yaml.gotmpl", "releases:\n", "releases:\n  - name: traefik\n    version: 41.6.1\n")
    write(root, "labs64.io-helm-charts/overrides/traefik/values.aws.yaml", values)
    return root


def test_traefik_rbac_copy_stamped_for_the_pinned_chart_is_clean(tmp_path):
    proc = run(traefik_ecosystem(tmp_path))
    assert proc.returncode == 0, proc.stdout
    assert "Traefik replacement RBAC compared with chart" in proc.stdout


def test_traefik_chart_bump_without_comparing_the_rbac_copy_is_rejected(tmp_path):
    root = traefik_ecosystem(tmp_path)
    replace(root, "labs64.io-helm-charts/helmfile.yaml.gotmpl", "version: 41.6.1", "version: 42.0.0")
    proc = run(root)
    assert proc.returncode == 1
    assert "was compared with traefik chart 41.6.1" in proc.stdout


def test_traefik_rbac_copy_without_a_stamp_is_rejected(tmp_path):
    proc = run(traefik_ecosystem(tmp_path, "rbac:\n  enabled: false\n"))
    assert proc.returncode == 1
    assert "has no `# chart-pin: traefik <version>` line" in proc.stdout


def test_traefik_values_that_keep_the_chart_rbac_need_no_stamp(tmp_path):
    proc = run(traefik_ecosystem(tmp_path, "rbac:\n  enabled: true\n"))
    assert proc.returncode == 0, proc.stdout


def test_strict_fails_when_a_required_repository_is_missing(tmp_path):
    proc = run(ecosystem(tmp_path), "--strict")
    assert proc.returncode == 1
    assert "--strict: labs64.io-commons is not present" in proc.stdout


def test_print_pins_emits_the_platform_pins_as_json(tmp_path):
    import json

    root = ecosystem(tmp_path)
    write(root, "labs64.io-helm-charts/charts/preflight/values.yaml",
          "images:\n  db: postgres:18.2\n  cache: valkey/valkey:9.1-alpine\n  curl: curlimages/curl:8.22.0\n")
    proc = run(root, "--print-pins")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    pins = json.loads(proc.stdout)
    assert set(pins) == {
        "External Secrets Operator chart", "Keycloak (keycloakx) chart", "Traefik chart",
        "OpenTelemetry Collector chart", "Gateway API CRDs", "Kubernetes minor",
        "PostgreSQL major", "Valkey line", "RabbitMQ line", "curl image",
    }
    assert pins["External Secrets Operator chart"] == {"helm-charts helmfile (external-secrets)": "2.11.0"}
    assert pins["Kubernetes minor"] == {"k3d/labs64io.yaml": "1.36"}
    assert pins["PostgreSQL major"]["preflight values"] == "18"
    assert pins["Valkey line"]["preflight values"] == "9.1"
    assert pins["curl image"] == {"preflight values": "8.22.0"}
    assert pins["Traefik chart"] == {"helm-charts helmfile (traefik)": None}


def test_print_pins_names_no_private_repository(tmp_path):
    proc = run(ecosystem(tmp_path), "--print-pins")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "devops" not in proc.stdout
    assert "terraform" not in proc.stdout


def test_gateway_api_drift_between_versions_file_and_installer(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-helm-charts/install.sh", 'GATEWAY_API_VERSION="${LABS64_GATEWAY_API_VERSION:-v1.6.1}"\n')
    proc = run(root)
    assert proc.returncode == 1
    assert "Gateway API CRDs differs" in proc.stdout


def test_postgres_major_across_public_places(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-helm-charts/charts/preflight/values.yaml", "images:\n  db: postgres:17.6\n")
    proc = run(root)
    assert proc.returncode == 1
    assert "PostgreSQL major differs" in proc.stdout


def test_strict_does_not_require_a_private_repository(tmp_path):
    proc = run(ecosystem(tmp_path), "--strict")
    assert "devops" not in proc.stdout


def test_the_script_names_no_private_repository():
    text = SCRIPT.read_text()
    for word in ("devops", "docs-internal", "EKS", "ElastiCache", "Amazon MQ", "variables.tf"):
        assert word not in text, word


DEVCONTAINER = (
    '{"features": {"ghcr.io/devcontainers/features/java:1": {"version": "25", "installMaven": "true", "mavenVersion": "%s"}}}'
)


def test_devcontainer_maven_must_equal_the_pin(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-workspace/tool-versions.env", TOOLS + "MAVEN_VERSION=3.9.16\n")
    write(root, "labs64.io-workspace/.devcontainer/devcontainer.json", DEVCONTAINER % "3.9.15")
    proc = run(root)
    assert proc.returncode == 1
    assert "maven: tool-versions.env vs devcontainer.json differs" in proc.stdout


def test_devcontainer_maven_equal_to_the_pin_is_clean(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-workspace/tool-versions.env", TOOLS + "MAVEN_VERSION=3.9.16\n")
    write(root, "labs64.io-workspace/.devcontainer/devcontainer.json", DEVCONTAINER % "3.9.16")
    proc = run(root)
    assert proc.returncode == 0, proc.stdout
    assert "maven: tool-versions.env vs devcontainer.json" in proc.stdout


MVN_WORKFLOW = "jobs:\n  a:\n    steps:\n%s      - run: mvn -B verify\n"
SETUP_MAVEN = "      - uses: Labs64/labs64.io-workspace/.github/actions/setup-maven@v1\n"


def test_workflow_that_runs_mvn_with_the_runners_maven_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-workspace/.github/workflows/ci.yml", MVN_WORKFLOW % "")
    proc = run(root)
    assert proc.returncode == 1
    assert "runs mvn without .github/actions/setup-maven" in proc.stdout


def test_workflow_that_runs_mvn_after_setup_maven_is_clean(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-workspace/.github/workflows/ci.yml", MVN_WORKFLOW % SETUP_MAVEN)
    assert run(root).returncode == 0


def test_mvn_in_a_comment_or_in_a_module_workflow_is_not_checked(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-workspace/.github/workflows/ci.yml", "jobs:\n  a:\n    steps:\n      # mvn -B verify\n      - run: echo hi\n")
    write(root, "labs64.io-checkout/.github/workflows/ci.yml", MVN_WORKFLOW % "")
    assert run(root).returncode == 0
