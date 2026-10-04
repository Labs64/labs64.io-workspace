"""Tests for scripts/check-release-wiring.py.

The gate exists because no single repository can see the chain module release -> chart.
Each test builds a synthetic ecosystem (a chart repo plus one module repo) and checks that the
ways the chain silently rots are all reported: a second image nobody dispatches, a renamed
chart, a release with no propagation, a partial release that could still propagate.

Reuses the chart repository's own image-block discovery (update-chart-images.py), exactly as the
gate does; skipped where that sibling checkout is not available.

Run: pytest scripts/tests/test_check_release_wiring.py -q
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-release-wiring.py"
HELPER = SCRIPT.parents[2] / "labs64.io-helm-charts" / "scripts" / "update-chart-images.py"

pytestmark = pytest.mark.skipif(not HELPER.is_file(), reason="labs64.io-helm-charts checkout not available")

DEMO_VALUES = """image:
  repository: labs64/demo
  tag: ""
  digest: ""
sidecar:
  image:
    repository: labs64/demo-sidecar
    tag: ""
    digest: ""
swagger:
  image:
    repository: swaggerapi/swagger-ui
    tag: ""
"""


def make_charts(root: Path, charts: dict[str, str]) -> None:
    repo = root / "labs64.io-helm-charts"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(HELPER, repo / "scripts" / "update-chart-images.py")
    for name, values in charts.items():
        (repo / "charts" / name).mkdir(parents=True)
        (repo / "charts" / name / "values.yaml").write_text(values)


def release_workflow(*, images=("labs64/demo", "labs64/demo-sidecar"), dispatch=True, chart="demo",
                     supplied=None, needs=None, mode="release") -> str:
    jobs = {}
    for i, image in enumerate(images):
        jobs[f"publish-{i}"] = (
            f"  publish-{i}:\n    uses: Labs64/labs64.io-workspace/.github/workflows/docker-publish.yml@v1\n"
            f"    with:\n      image: {image}\n      context: ./c{i}\n      mode: {mode}\n      version: 1.0.0\n"
        )
    text = "name: release\non: {release: {types: [created]}}\njobs:\n" + "".join(jobs.values())
    if dispatch:
        jobs_supplied = supplied if supplied is not None else [f"publish-{i}" for i in range(len(images))]
        needs_list = needs if needs is not None else [f"publish-{i}" for i in range(len(images))]
        refs = "\n".join(f"        ${{{{ needs.{j}.outputs.image-ref }}}}" for j in jobs_supplied)
        text += (
            "  propagate:\n"
            f"    needs: [{', '.join(needs_list)}]\n"
            "    uses: Labs64/labs64.io-workspace/.github/workflows/chart-update-dispatch.yml@v1\n"
            f"    with:\n      chart: {chart}\n      version: 1.0.0\n      images: |\n{refs}\n"
        )
    return text


def add_module(root: Path, workflow: str) -> None:
    path = root / "labs64.io-demo" / ".github" / "workflows" / "release.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workflow)


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True)


def test_fully_wired_release_is_clean(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES})
    add_module(tmp_path, release_workflow())
    proc = run(tmp_path)
    assert proc.returncode == 0, proc.stdout
    assert "clean" in proc.stdout


def test_third_party_images_are_not_required(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES})  # swagger-ui is in the chart but not first-party
    add_module(tmp_path, release_workflow())
    assert run(tmp_path).returncode == 0


def test_second_image_that_is_not_dispatched_is_reported(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES})
    add_module(tmp_path, release_workflow(supplied=["publish-0"], needs=["publish-0", "publish-1"]))
    proc = run(tmp_path)
    assert proc.returncode == 1
    assert "requires ['labs64/demo', 'labs64/demo-sidecar'], workflow supplies ['labs64/demo']" in proc.stdout


def test_dispatch_naming_a_renamed_chart_is_reported(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES})
    add_module(tmp_path, release_workflow(chart="old-name"))
    proc = run(tmp_path)
    assert proc.returncode == 1
    assert "chart 'old-name' does not exist" in proc.stdout


def test_release_without_any_propagation_is_reported(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES})
    add_module(tmp_path, release_workflow(dispatch=False))
    proc = run(tmp_path)
    assert proc.returncode == 1
    assert "never dispatches a chart update" in proc.stdout


def test_dispatch_that_does_not_wait_for_every_release_job_is_reported(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES})
    add_module(tmp_path, release_workflow(needs=["publish-0"]))
    proc = run(tmp_path)
    assert proc.returncode == 1
    assert "needs is missing release jobs" in proc.stdout


def test_chart_with_first_party_images_that_no_release_feeds_is_reported(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES, "orphan": DEMO_VALUES.replace("labs64/demo", "labs64/orphan")})
    add_module(tmp_path, release_workflow())
    proc = run(tmp_path)
    assert proc.returncode == 1
    assert "charts/orphan: deploys first-party images but no release wires to it" in proc.stdout


def test_edge_publishers_are_out_of_scope(tmp_path):
    make_charts(tmp_path, {"demo": DEMO_VALUES})
    add_module(tmp_path, release_workflow(mode="edge", dispatch=False))
    proc = run(tmp_path)
    # an :edge build is not a release, so it must neither need nor trigger propagation;
    # the chart is then reported only as unwired, not the workflow as broken
    assert "never dispatches" not in proc.stdout
