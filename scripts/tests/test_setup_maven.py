"""The setup-maven action's installer: the pinned Maven, verified, first on PATH.

The distribution comes from a fake local "Central" laid out like the real one
(<base>/<version>/apache-maven-<version>-bin.tar.gz plus a .sha512 beside it), so these tests
need no network.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tarfile
from pathlib import Path

INSTALL = Path(__file__).resolve().parents[2] / ".github" / "actions" / "setup-maven" / "install.sh"


def distribution(tmp_path: Path, version: str = "9.9.9", reports: str | None = None, sha: str | None = None) -> Path:
    """A fake Central with one Maven archive whose `mvn --version` says `reports` (default: its own)."""
    base = tmp_path / "central"
    folder = base / version
    folder.mkdir(parents=True)
    staging = tmp_path / "staging" / f"apache-maven-{version}" / "bin"
    staging.mkdir(parents=True)
    mvn = staging / "mvn"
    mvn.write_text(f'#!/bin/sh\necho "Apache Maven {reports or version} (fake)"\n')
    mvn.chmod(0o755)
    archive = folder / f"apache-maven-{version}-bin.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tmp_path / "staging" / f"apache-maven-{version}", arcname=f"apache-maven-{version}")
    digest = sha or hashlib.sha512(archive.read_bytes()).hexdigest()
    (folder / f"apache-maven-{version}-bin.tar.gz.sha512").write_text(digest + "\n")
    return base


def install(tmp_path: Path, base: Path, pins: str = "MAVEN_VERSION=9.9.9\n") -> subprocess.CompletedProcess:
    env_file = tmp_path / "tool-versions.env"
    env_file.write_text(pins)
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir(exist_ok=True)
    (tmp_path / "github_path").touch()
    (tmp_path / "github_env").touch()
    env = {
        **os.environ,
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_PATH": str(tmp_path / "github_path"),
        "GITHUB_ENV": str(tmp_path / "github_env"),
        "MAVEN_DIST_BASE": base.as_uri(),
    }
    return subprocess.run(["bash", str(INSTALL), str(env_file)], env=env, capture_output=True, text=True)


def test_installs_the_pinned_maven_and_puts_it_first_on_path(tmp_path):
    proc = install(tmp_path, distribution(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    bin_dir = (tmp_path / "github_path").read_text().strip()
    assert bin_dir == str(tmp_path / "runner" / "apache-maven-9.9.9" / "bin")
    assert "Apache Maven 9.9.9" in subprocess.run([f"{bin_dir}/mvn", "--version"], capture_output=True, text=True).stdout
    assert "MAVEN_VERSION=9.9.9" in (tmp_path / "github_env").read_text()


def test_a_checksum_mismatch_installs_nothing(tmp_path):
    proc = install(tmp_path, distribution(tmp_path, sha="0" * 128))
    assert proc.returncode != 0
    assert "checksum" in (proc.stdout + proc.stderr).lower()
    assert (tmp_path / "github_path").read_text() == ""
    assert not (tmp_path / "runner" / "apache-maven-9.9.9").exists()


def test_an_archive_that_reports_another_version_is_rejected(tmp_path):
    proc = install(tmp_path, distribution(tmp_path, reports="3.10.0"))
    assert proc.returncode != 0
    assert "9.9.9" in proc.stdout + proc.stderr
    assert (tmp_path / "github_path").read_text() == ""


def test_a_missing_pin_is_an_error_that_names_the_file(tmp_path):
    proc = install(tmp_path, distribution(tmp_path), pins="HELM_VERSION=4.3.0\n")
    assert proc.returncode != 0
    assert "MAVEN_VERSION" in proc.stdout + proc.stderr


def test_an_unreachable_distribution_fails_instead_of_falling_back_to_the_runners_maven(tmp_path):
    proc = install(tmp_path, tmp_path / "does-not-exist")
    assert proc.returncode != 0
    assert "download" in (proc.stdout + proc.stderr).lower()
    assert (tmp_path / "github_path").read_text() == ""
