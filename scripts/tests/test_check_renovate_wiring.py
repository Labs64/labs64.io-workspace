"""Tests for scripts/check-renovate-wiring.py.

The gate exists because the events that make a Renovate pull request due are wired in different
repositories (a caller in each, a step in the Maven publish workflow and in the chart release), so no
single repository's CI sees one of them silently stop. Each test builds a small
ecosystem that is right, breaks one thing, and checks that the gate names it.

Run: pytest scripts/tests/test_check_renovate_wiring.py -q
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-renovate-wiring.py"

CALLER = """\
name: dashboard
on:
  issues:
    types: [edited]
jobs:
  run-renovate:
    uses: Labs64/labs64.io-workspace/.github/workflows/renovate-dashboard.yml@v1
    secrets: inherit
"""

MAVEN_PUBLISH = """\
name: Reusable - Maven Publish
on: {workflow_call: {}}
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - run: mvn deploy
      - uses: Labs64/labs64.io-workspace/.github/actions/renovate-trigger@v1
"""

CHART_RELEASE = """\
name: release
on: {push: {}}
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: helm/chart-releaser-action@v1.7.0
      - uses: Labs64/labs64.io-workspace/.github/actions/renovate-trigger@v1
"""

MODULE_RELEASE = """\
name: release
on: {release: {types: [created]}}
jobs:
  publish:
    uses: Labs64/labs64.io-workspace/.github/workflows/maven-publish.yml@v1
    with: {mode: release}
    secrets: inherit
"""


def write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(text) if text.startswith("\n") else text)


def ecosystem(root: Path, **over: str | None) -> Path:
    """A right ecosystem: a module and the chart repository with the caller, and the producers. `over` replaces a file by
    its short name, or removes it with None."""
    files = {
        "module-caller": ("labs64.io-demo/.github/workflows/labs64io-renovate-dashboard.yml", CALLER),
        "module-release": ("labs64.io-demo/.github/workflows/release.yml", MODULE_RELEASE),
        "charts-caller": ("labs64.io-helm-charts/.github/workflows/labs64io-renovate-dashboard.yml", CALLER),
        "charts-release": ("labs64.io-helm-charts/.github/workflows/release.yml", CHART_RELEASE),
        "publish": ("labs64.io-workspace/.github/workflows/maven-publish.yml", MAVEN_PUBLISH),
        "dashboard": ("labs64.io-workspace/.github/workflows/renovate-dashboard.yml", "on: {workflow_call: {}}\njobs: {}\n"),
        "action": ("labs64.io-workspace/.github/actions/renovate-trigger/action.yml", "name: trigger\n"),
        "workspace-caller": ("labs64.io-workspace/.github/workflows/labs64io-renovate-dashboard.yml", CALLER),
    }
    for key, (path, text) in files.items():
        replacement = over.get(key, text)
        if replacement is not None:
            write(root, path, replacement)
    for repo in ("labs64.io-demo", "labs64.io-helm-charts", "labs64.io-workspace"):
        write(root, f"{repo}/renovate.json", "{}")
    return root


def run(root: Path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def test_a_complete_ecosystem_is_clean(tmp_path):
    code, out = run(ecosystem(tmp_path))
    assert code == 0, out
    assert "3 repositories" in out


def test_a_repository_without_the_dashboard_caller_is_named(tmp_path):
    code, out = run(ecosystem(tmp_path, **{"module-caller": None}))
    assert code == 1
    assert "labs64.io-demo: has a renovate.json but no workflow calling renovate-dashboard.yml" in out


def test_a_caller_that_does_not_run_on_edited_issues_is_refused(tmp_path):
    for trigger in ("on: {issues: {types: [opened]}}", "on: {push: {}}"):
        broken = CALLER.replace("on:\n  issues:\n    types: [edited]", trigger)
        code, out = run(ecosystem(tmp_path, **{"module-caller": broken}))
        assert code == 1, trigger
        assert "labs64io-renovate-dashboard.yml: calls renovate-dashboard.yml but does not run on" in out


def test_a_caller_without_inherited_secrets_is_refused(tmp_path):
    code, out = run(ecosystem(tmp_path, **{"module-caller": CALLER.replace("    secrets: inherit\n", "")}))
    assert code == 1
    assert "needs `secrets: inherit`" in out
    assert "has a renovate.json but no workflow" not in out  # one problem, reported once


def test_the_workspaces_own_local_caller_counts(tmp_path):
    local = CALLER.replace("Labs64/labs64.io-workspace/.github/workflows/renovate-dashboard.yml@v1",
                           "./.github/workflows/renovate-dashboard.yml")
    code, out = run(ecosystem(tmp_path, **{"workspace-caller": local}))
    assert code == 0, out


def test_a_repository_without_renovate_json_is_not_asked_for_a_caller(tmp_path):
    root = ecosystem(tmp_path)
    write(root, "labs64.io-extra/.github/workflows/ci.yml", "on: {push: {}}\njobs: {}\n")
    assert run(root)[0] == 0


def test_maven_publish_that_does_not_ask_renovate_is_refused(tmp_path):
    code, out = run(ecosystem(tmp_path, publish=MAVEN_PUBLISH.replace(
        "      - uses: Labs64/labs64.io-workspace/.github/actions/renovate-trigger@v1\n", "")))
    assert code == 1
    assert "a release does not run actions/renovate-trigger" in out


def test_a_release_caller_that_drops_the_secrets_is_refused(tmp_path):
    code, out = run(ecosystem(tmp_path, **{"module-release": MODULE_RELEASE.replace("    secrets: inherit\n", "")}))
    assert code == 1
    assert "calls maven-publish.yml without `secrets: inherit`" in out


def test_a_chart_release_that_does_not_ask_renovate_is_refused(tmp_path):
    code, out = run(ecosystem(tmp_path, **{"charts-release": CHART_RELEASE.replace(
        "      - uses: Labs64/labs64.io-workspace/.github/actions/renovate-trigger@v1\n", "")}))
    assert code == 1
    assert "publishes charts but does not run actions/renovate-trigger" in out


def test_the_shared_pieces_must_exist(tmp_path):
    for key, name in (("action", "renovate-trigger/action.yml"), ("dashboard", "renovate-dashboard.yml")):
        code, out = run(ecosystem(tmp_path / key, **{key: None}))
        assert code == 1 and f"{name}: missing" in out
