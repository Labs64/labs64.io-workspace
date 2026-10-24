"""Tests for scripts/check-just.py.

The gate holds every justfile that adopted docs/justfiles.md to it, and every `just <recipe>` in a workflow, script
or document to a recipe that exists. Each test builds a small ecosystem that is right, breaks one thing, and checks
that the gate names it. Needs `just` on the PATH (the dev container and CI install it).

Run: pytest scripts/tests/test_check_just.py -q
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-just.py"

pytestmark = pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed")

ROOT_JUSTFILE = """\
# List the recipes
default:
    @just --list

import 'just/setup.just'
import 'just/local-stack.just'
import 'just/quality-gates.just'
import 'just/renamed.just'
"""

SETUP = """\
# Check the tools
[group('setup')]
doctor:
    @echo ok
"""

LOCAL_STACK = """\
# Create the local stack
[group('local stack')]
up:
    @echo up

# Show the stack's state
[group('local stack')]
status:
    @echo status
"""

GATES = """\
# Run what the pull-request check runs
[group('quality gates')]
ci: lint

# Lint
[group('quality gates')]
lint:
    @echo lint
"""

RENAMED = """\
# Remove this file after 2099-01-01.

# Fail with the new name of a renamed recipe
[private]
_renamed old +new:
    @echo 'renamed' >&2 && exit 1

[private]
old-status *args:
    @just _renamed old-status status
"""


def repo(root: Path, name: str, files: dict[str, str]) -> Path:
    path = root / name
    for rel, text in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(textwrap.dedent(text))
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    return path


def adopted(root: Path, name: str = "labs64.io-thing", extra: dict[str, str] | None = None) -> Path:
    files = {
        "justfile": ROOT_JUSTFILE,
        "just/setup.just": SETUP,
        "just/local-stack.just": LOCAL_STACK,
        "just/quality-gates.just": GATES,
        "just/renamed.just": RENAMED,
    }
    files.update(extra or {})
    return repo(root, name, files)


def run(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *extra], capture_output=True, text=True)


def test_a_justfile_that_follows_the_convention_is_clean(tmp_path):
    adopted(tmp_path, extra={"README.md": "Run `just up`, then `just status`.\n"})
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_a_recipe_in_the_root_justfile_is_named(tmp_path):
    adopted(tmp_path, extra={"justfile": ROOT_JUSTFILE + "\n# Stray\n[group('setup')]\nstray:\n    @echo x\n"})
    result = run(tmp_path)
    assert result.returncode == 1
    assert "`stray` belongs in just/<group>.just" in result.stderr


def test_a_recipe_without_group_or_description_is_named(tmp_path):
    adopted(tmp_path, extra={"just/setup.just": SETUP + "\nundocumented:\n    @echo x\n"})
    result = run(tmp_path)
    assert "`undocumented` (just/setup.just): no description" in result.stderr
    assert "`undocumented` (just/setup.just): needs exactly one [group('…')]" in result.stderr


def test_a_recipe_in_the_file_of_another_group_is_named(tmp_path):
    adopted(tmp_path, extra={"just/setup.just": SETUP + "\n# Misplaced\n[group('quality gates')]\nmisplaced:\n    @echo x\n"})
    result = run(tmp_path)
    assert "its group `quality gates` lives in just/quality-gates.just" in result.stderr


def test_an_environment_with_a_default_is_refused(tmp_path):
    adopted(tmp_path, extra={"just/setup.just": SETUP + "\n# Plan\n[group('setup')]\nplan env='dev':\n    @echo {{env}}\n"})
    result = run(tmp_path)
    assert "`plan` (just/setup.just): `env` has a default" in result.stderr


def test_the_reserved_recipes_are_required(tmp_path):
    adopted(tmp_path, extra={"just/quality-gates.just": "# Lint\n[group('quality gates')]\nlint:\n    @echo lint\n"})
    result = run(tmp_path)
    assert "no `ci` recipe" in result.stderr


def test_renamed_recipes_expire(tmp_path):
    adopted(tmp_path, extra={"just/renamed.just": RENAMED.replace("2099-01-01", "2020-01-01")})
    result = run(tmp_path)
    assert "its date (2020-01-01) has passed" in result.stderr


def test_a_reference_to_a_renamed_recipe_is_named_and_fixed(tmp_path):
    path = adopted(tmp_path, extra={"docs/ops.md": "Check it with `just old-status`.\n\n```bash\njust old-status\n```\n"})
    result = run(tmp_path)
    assert result.returncode == 1
    assert "docs/ops.md:1: `just old-status`: was renamed to `just status`" in result.stderr
    assert "docs/ops.md:4" in result.stderr
    fixed = run(tmp_path, "--fix")
    assert fixed.returncode == 0, fixed.stderr
    assert (path / "docs/ops.md").read_text() == "Check it with `just status`.\n\n```bash\njust status\n```\n"


def test_a_reference_to_a_recipe_nobody_has_is_named(tmp_path):
    adopted(tmp_path, extra={".github/workflows/ci.yml": "jobs:\n  x:\n    steps:\n      - run: just nope\n"})
    result = run(tmp_path)
    assert ".github/workflows/ci.yml:4: `just nope`: no repository has this recipe" in result.stderr


def test_module_references_resolve_in_the_mounted_repository(tmp_path):
    adopted(tmp_path, "labs64.io-charts")
    front = adopted(tmp_path, "labs64.io-front", extra={
        "justfile": ROOT_JUSTFILE + "\n# The charts\nmod? charts '../labs64.io-charts/justfile'\n",
        "README.md": "`just charts up` works, `just charts old-status` is renamed, `just charts nope` is not there.\n",
    })
    result = run(tmp_path)
    assert "README.md:1: `just charts old-status`: `old-status` of the charts module was renamed to `status`" in result.stderr
    assert "README.md:1: `just charts nope`: the module mounting labs64.io-charts has no recipe `nope`" in result.stderr
    assert "`just charts up`" not in result.stderr
    assert front.exists()


def test_prose_and_history_are_not_checked(tmp_path):
    adopted(tmp_path, extra={
        "tool.py": 'print("just now")  # just in case\n',
        "rfc/old.md": "Back then: `just gone`.\n",
    })
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_a_repository_that_has_not_adopted_the_layout_is_only_checked_for_references(tmp_path):
    repo(tmp_path, "labs64.io-legacy", {"justfile": "build:\n    @echo build\n", "README.md": "`just build`, `just gone`\n"})
    result = run(tmp_path)
    assert "no `ci` recipe" not in result.stderr
    assert "README.md:1: `just gone`: no repository has this recipe" in result.stderr


def test_a_module_whose_repository_is_not_cloned_is_not_a_wrong_reference(tmp_path):
    # CI checks out the public repositories only: `just ee …` points at a private repository that is not there.
    adopted(tmp_path, "labs64.io-front", extra={
        "justfile": ROOT_JUSTFILE + "\n# The private workspace\nmod? ee '../labs64.io-private/justfile'\n",
        "README.md": "From the workspace: `just ee devops plan dev`, then `just status`, but not `just nope`.\n",
    })
    result = run(tmp_path)
    assert "`just ee devops plan dev`" not in result.stderr
    assert "`just nope`: no repository has this recipe" in result.stderr


def test_the_same_reference_is_checked_in_full_when_the_repository_is_cloned(tmp_path):
    adopted(tmp_path, "labs64.io-private")
    adopted(tmp_path, "labs64.io-front", extra={
        "justfile": ROOT_JUSTFILE + "\n# The private workspace\nmod? ee '../labs64.io-private/justfile'\n",
        "README.md": "`just ee status` exists, `just ee gone` does not.\n",
    })
    result = run(tmp_path)
    assert "`just ee status`" not in result.stderr
    assert "`just ee gone`: the module mounting labs64.io-private has no recipe `gone`" in result.stderr

