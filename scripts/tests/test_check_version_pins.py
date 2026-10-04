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

DEVOPS_VERSIONS = """# renovate: datasource=docker depName=ghcr.io/external-secrets/charts/external-secrets
ESO_CHART_VERSION := "2.11.0"
# renovate: datasource=docker depName=ghcr.io/codecentric/helm-charts/keycloakx
KEYCLOAK_CHART_VERSION := "7.3.2"
# renovate: datasource=github-releases depName=kubernetes-sigs/gateway-api
GATEWAY_API_VERSION := "v1.6.2"
# renovate: datasource=docker depName=curlimages/curl
CANARY_CURL_VERSION := "8.22.0"
"""

VARIABLES_TF = """variable "eks_cluster_version" {
  default = "1.36"
}
variable "rds_engine_version" {
  default = "18"
}
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
    write(root, "labs64.io-devops/justfile", IMPORTING_JUSTFILE)
    write(root, "labs64.io-devops/justfile.versions", DEVOPS_VERSIONS)
    write(root, "labs64.io-devops/terraform/variables.tf", VARIABLES_TF)
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


def test_eso_version_drift_between_helmfile_and_devops(tmp_path):
    root = ecosystem(tmp_path)
    replace(root, "labs64.io-devops/justfile.versions", 'ESO_CHART_VERSION := "2.11.0"', 'ESO_CHART_VERSION := "2.10.0"')
    proc = run(root)
    assert proc.returncode == 1
    assert "External Secrets Operator chart differs" in proc.stdout


def test_gateway_api_drift_between_charts_and_devops(tmp_path):
    root = ecosystem(tmp_path)
    replace(root, "labs64.io-devops/justfile.versions", 'GATEWAY_API_VERSION := "v1.6.2"', 'GATEWAY_API_VERSION := "v1.6.1"')
    proc = run(root)
    assert proc.returncode == 1
    assert "Gateway API CRDs differs" in proc.stdout


def test_version_constant_in_justfile_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    (root / "labs64.io-devops/justfile").write_text(IMPORTING_JUSTFILE + 'K6_VERSION := "2.3.0"\n')
    proc = run(root)
    assert proc.returncode == 1
    assert "version constant outside justfile.versions" in proc.stdout


def test_pin_without_renovate_annotation_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    replace(root, "labs64.io-devops/justfile.versions", "# renovate: datasource=docker depName=curlimages/curl\n", "")
    proc = run(root)
    assert proc.returncode == 1
    assert "CANARY_CURL_VERSION has no `# renovate:` annotation" in proc.stdout


def test_justfile_that_does_not_import_the_versions_file_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    (root / "labs64.io-devops/justfile").write_text("default:\n    @just --list\n")
    proc = run(root)
    assert proc.returncode == 1
    assert "does not import justfile.versions" in proc.stdout


def test_versions_file_missing_while_justfile_exists_is_rejected(tmp_path):
    root = ecosystem(tmp_path)
    (root / "labs64.io-helm-charts/justfile.versions").unlink()
    proc = run(root)
    assert proc.returncode == 1
    assert "justfile.versions is missing" in proc.stdout


def test_local_kubernetes_minor_must_equal_eks(tmp_path):
    root = ecosystem(tmp_path)
    replace(root, "labs64.io-helm-charts/k3d/labs64io.yaml", "v1.36.5-k3s1", "v1.35.5-k3s1")
    proc = run(root)
    assert proc.returncode == 1
    assert "Kubernetes minor: local k3s vs EKS differs" in proc.stdout


def test_postgres_major_across_helmfile_and_terraform(tmp_path):
    root = ecosystem(tmp_path)
    replace(root, "labs64.io-devops/terraform/variables.tf", 'default = "18"', 'default = "17"')
    proc = run(root)
    assert proc.returncode == 1
    assert "PostgreSQL major differs" in proc.stdout


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


def test_strict_fails_when_a_required_repository_is_missing(tmp_path):
    # the fixture has workspace, helm-charts and devops only
    proc = run(ecosystem(tmp_path), "--strict")
    assert proc.returncode == 1
    assert "--strict: labs64.io-commons is not present" in proc.stdout
    assert "--strict: labs64.io-devops" not in proc.stdout  # present, so not reported


def test_strict_failure_names_the_private_repo_when_it_is_the_one_missing(tmp_path):
    root = ecosystem(tmp_path)
    import shutil
    shutil.rmtree(root / "labs64.io-devops")
    proc = run(root, "--strict")
    assert proc.returncode == 1
    assert "--strict: labs64.io-devops is not present" in proc.stdout


def test_default_mode_still_skips_missing_repositories(tmp_path):
    import shutil
    root = ecosystem(tmp_path)
    shutil.rmtree(root / "labs64.io-devops")
    assert run(root).returncode == 0
