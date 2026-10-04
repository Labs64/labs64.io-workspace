"""Tests for scripts/lib/internal-deps.sh — rebuilding pinned internal releases from git tags.

No Maven is run: the interesting logic is which versions are pinned, when a build is needed at
all, and failing loudly when the tag a module pins does not exist. A fake local Maven repository
stands in for ~/.m2, and the fake sibling repositories are real git repos.

Run: pytest scripts/tests/test_internal_deps.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib" / "internal-deps.sh"

PARENT_POM = """<project>
  <parent>
    <groupId>io.labs64</groupId>
    <artifactId>labs64io-parent</artifactId>
    <version>{parent}</version>
    <relativePath />
  </parent>
  <properties>
    <auditflow-api.version>{api}</auditflow-api.version>
  </properties>
</project>
"""


def bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    full = f'set -uo pipefail\nVERBOSE=0\nsource "{LIB.parent}/progress.sh"\nsource "{LIB}"\n{script}\n'
    return subprocess.run(["bash", "-c", full], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin:/usr/local/bin", **env})


def git_repo(path: Path, tag: str | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README").write_text("x")
    cmds = [["git", "init", "-q"], ["git", "add", "-A"], ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"]]
    if tag:
        cmds.append(["git", "tag", tag])
    for cmd in cmds:
        subprocess.run(cmd, cwd=path, check=True, capture_output=True)


def module_pom(root: Path, parent: str, api: str = "0.0.0-SNAPSHOT") -> None:
    pom = root / "labs64.io-checkout" / "checkout-be" / "pom.xml"
    pom.parent.mkdir(parents=True)
    pom.write_text(PARENT_POM.format(parent=parent, api=api))


def env(root: Path, m2: Path) -> dict[str, str]:
    return {"ROOT": str(root), "GIT_ROOT": str(root), "MAVEN_REPO_LOCAL": str(m2), "HOME": str(root)}


def test_pinned_version_reads_parent_and_property(tmp_path):
    module_pom(tmp_path, parent="1.4.0", api="0.0.18")
    pom = tmp_path / "labs64.io-checkout/checkout-be/pom.xml"
    # callers always capture the value with $(...), which is what is exercised here
    out = bash(f'echo "$(_pinned_version "{pom}" parent)"; echo "$(_pinned_version "{pom}" auditflow-api.version)"', env(tmp_path, tmp_path / "m2"))
    assert out.stdout.split() == ["1.4.0", "0.0.18"]


def test_pinned_version_of_a_missing_pom_is_empty_not_an_error(tmp_path):
    out = bash(f'_pinned_version "{tmp_path}/nope.xml" parent', env(tmp_path, tmp_path / "m2"))
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_snapshot_pins_need_nothing(tmp_path):
    module_pom(tmp_path, parent="0.0.0-SNAPSHOT")
    git_repo(tmp_path / "labs64.io-commons")  # no tags at all
    out = bash("ensure_pinned_releases", env(tmp_path, tmp_path / "m2"))
    assert out.returncode == 0, out.stderr


def test_release_already_in_the_local_repository_is_not_rebuilt(tmp_path):
    module_pom(tmp_path, parent="1.4.0")
    m2 = tmp_path / "m2"
    installed = m2 / "io/labs64/labs64io-parent/1.4.0"
    installed.mkdir(parents=True)
    (installed / "labs64io-parent-1.4.0.pom").write_text("<project/>")
    # no commons checkout at all: any attempt to build would fail, so success proves the skip
    out = bash("ensure_pinned_releases", env(tmp_path, m2))
    assert out.returncode == 0, out.stderr


def test_missing_tag_fails_loudly_with_a_hint(tmp_path):
    module_pom(tmp_path, parent="1.4.0")
    git_repo(tmp_path / "labs64.io-commons", tag="0.0.3")  # the pinned 1.4.0 does not exist
    out = bash("ensure_pinned_releases", env(tmp_path, tmp_path / "m2"))
    assert out.returncode != 0
    assert "has no tag '1.4.0'" in out.stderr
    assert "just pull" in out.stderr


def test_auditflow_api_release_is_resolved_from_the_auditflow_repo(tmp_path):
    module_pom(tmp_path, parent="0.0.0-SNAPSHOT")
    pg = tmp_path / "labs64.io-payment-gateway" / "payment-gateway-be" / "pom.xml"
    pg.parent.mkdir(parents=True)
    pg.write_text(PARENT_POM.format(parent="0.0.0-SNAPSHOT", api="0.0.18"))
    git_repo(tmp_path / "labs64.io-auditflow", tag="0.0.3")  # 0.0.18 absent
    out = bash("ensure_pinned_releases", env(tmp_path, tmp_path / "m2"))
    assert out.returncode != 0
    assert "labs64.io-auditflow has no tag '0.0.18'" in out.stderr
