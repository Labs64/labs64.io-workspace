#!/usr/bin/env python3
"""Check that every released image reaches its Helm chart.

The release pipeline spans repositories: a module publishes images
(`docker-publish.yml`), reports their digests, and dispatches a chart update
(`chart-update-dispatch.yml`), which `labs64.io-helm-charts` turns into a PR
pinning those digests. No single repo's CI can see that chain end to end, so
nothing else catches the ways it silently rots:

  * a repo gains a second image and keeps dispatching only the first — the
    chart updater then refuses the event at release time (all-or-nothing), and
    the release is already published by the time anyone finds out;
  * a chart is renamed (`authproxy` publishes into `charts/api-gateway`, not
    `charts/authproxy`) and the dispatch keeps naming the old one;
  * a new module ships images with no propagation at all, so its chart quietly
    keeps deploying by tag.

Only `mode: release` publishers are in scope. `mode: edge` builds a `:edge`
image on master pushes; that is deliberately not a release and must never move
a chart.

Run from the ecosystem root (the directory holding all labs64.io-* repos):

    scripts/check-release-wiring.py
    just check-release-wiring
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

import yaml

PUBLISH_WORKFLOW = "docker-publish.yml"
DISPATCH_WORKFLOW = "chart-update-dispatch.yml"
FIRST_PARTY_PREFIX = "labs64/"


def load_chart_helper(charts_repo: Path):
    """Reuse the chart repo's own image-block discovery — one definition, not two."""
    script = charts_repo / "scripts" / "update-chart-images.py"
    if not script.is_file():
        raise SystemExit(f"cannot find {script}; run this from the ecosystem root")
    spec = importlib.util.spec_from_file_location("update_chart_images", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_chart_images"] = module
    spec.loader.exec_module(module)
    return module


def chart_first_party_images(charts_repo: Path, chart: str, helper) -> set[str]:
    values_file = charts_repo / "charts" / chart / "values.yaml"
    values = yaml.safe_load(values_file.read_text()) or {}
    return {
        repo
        for repo in helper.find_image_blocks(values)
        if repo.startswith(FIRST_PARTY_PREFIX)
    }


def as_list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    return list(value or [])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", default="..", help="ecosystem root (default: ..)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    charts_repo = root / "labs64.io-helm-charts"
    if not charts_repo.is_dir():
        raise SystemExit(f"no labs64.io-helm-charts under {root}")
    helper = load_chart_helper(charts_repo)

    problems: list[str] = []
    wired_charts: set[str] = set()

    for workflow in sorted(root.glob("labs64.io-*/.github/workflows/*.yml")):
        try:
            doc = yaml.safe_load(workflow.read_text()) or {}
        except yaml.YAMLError as exc:
            problems.append(f"{workflow}: unparseable ({exc})")
            continue
        jobs = doc.get("jobs") or {}

        releases: dict[str, str] = {}
        dispatch: tuple[str, dict] | None = None
        for name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            uses = job.get("uses") or ""
            with_ = job.get("with") or {}
            if PUBLISH_WORKFLOW in uses and with_.get("mode") == "release":
                releases[name] = with_.get("image")
            if DISPATCH_WORKFLOW in uses:
                dispatch = (name, job)

        if not releases:
            continue

        rel = workflow.relative_to(root)
        if dispatch is None:
            problems.append(
                f"{rel}: releases {sorted(releases.values())} but never dispatches a chart update"
            )
            continue

        job_name, job = dispatch
        with_ = job.get("with") or {}
        chart = with_.get("chart")
        if not chart or not (charts_repo / "charts" / chart / "values.yaml").is_file():
            problems.append(f"{rel} [{job_name}]: chart '{chart}' does not exist")
            continue
        wired_charts.add(chart)

        referenced_jobs = set(
            re.findall(r"needs\.([A-Za-z0-9_-]+)\.outputs\.image-ref", str(with_.get("images", "")))
        )
        unknown = referenced_jobs - set(releases)
        if unknown:
            problems.append(
                f"{rel} [{job_name}]: images reference non-release jobs {sorted(unknown)}"
            )
        supplied = {releases[j] for j in referenced_jobs & set(releases)}
        required = chart_first_party_images(charts_repo, chart, helper)
        if supplied != required:
            problems.append(
                f"{rel} [{job_name}]: charts/{chart} requires {sorted(required)}, "
                f"workflow supplies {sorted(supplied)}"
            )
            continue

        missing_needs = set(releases) - set(as_list(job.get("needs")))
        if missing_needs:
            problems.append(
                f"{rel} [{job_name}]: needs is missing release jobs {sorted(missing_needs)}, "
                f"so a partial release could propagate"
            )
            continue

        print(f"  ok  {rel.parts[0]:26} -> charts/{chart:16} {sorted(required)}")

    for chart_dir in sorted((charts_repo / "charts").iterdir()):
        if not (chart_dir / "values.yaml").is_file():
            continue
        if chart_first_party_images(charts_repo, chart_dir.name, helper) and chart_dir.name not in wired_charts:
            problems.append(
                f"charts/{chart_dir.name}: deploys first-party images but no release wires to it"
            )

    if problems:
        # Annotate in CI, stay readable in a terminal.
        prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") else "  FAIL  "
        print()
        for problem in problems:
            print(f"{prefix}{problem}")
        print(f"\ncheck-release-wiring: {len(problems)} problem(s)")
        return 1
    print("\ncheck-release-wiring: clean — every released image reaches its chart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
