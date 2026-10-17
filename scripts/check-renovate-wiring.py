#!/usr/bin/env python3
"""Check that every event which makes a Renovate pull request due starts the Renovate runner.

The runner is self-hosted (the operator's private repository): it runs on a clock and when something asks
it to (`.github/actions/renovate-trigger`). Two kinds of event ask, and each is wired in different
repositories, so no single repository's CI can see when one of them silently stops:

  * a ticked Dependency Dashboard box: every repository that carries a `renovate.json` must carry the
    `issues: edited` caller of `renovate-dashboard.yml`, with `secrets: inherit` (else the token never
    reaches it). A new repository that forgets it would have dashboard boxes that wait for the clock;
  * a release reaching Nexus (`maven-publish.yml`) and a published chart (labs64.io-helm-charts'
    release workflow) must each run the trigger action.

Every caller of `maven-publish.yml` must pass its secrets on (`secrets: inherit`), or the release
cannot ask for the run. That the runner accepts what the action sends is checked where the runner is,
in the private repository's tests.

Run from the ecosystem root (the directory holding all labs64.io-* repos):

    scripts/check-renovate-wiring.py
    just check-renovate-wiring
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

DASHBOARD_WORKFLOW = "renovate-dashboard.yml"
MAVEN_PUBLISH = "maven-publish.yml"
TRIGGER_ACTION = "actions/renovate-trigger"


def load(path: Path):
    """The parsed workflow, or the reason it cannot be read."""
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return None, f"unparseable ({exc})"
    return (doc if isinstance(doc, dict) else {}), None


def triggers(doc: dict) -> dict:
    """The `on:` block (PyYAML reads the key `on` as True)."""
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    return on or {}


def calls(doc: dict, workflow: str):
    """The jobs of `doc` that call the reusable workflow `workflow`."""
    for name, job in (doc.get("jobs") or {}).items():
        if isinstance(job, dict) and str(job.get("uses") or "").split("@")[0].endswith(workflow):
            yield name, job


def has_step_using(doc: dict, action: str) -> bool:
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            if action in str(step.get("uses") or ""):
                return True
    return False


def check_dashboard_callers(root: Path, problems: list[str]) -> int:
    ok = 0
    for repo in sorted(p for p in root.glob("labs64.io*") if (p / "renovate.json").is_file()):
        found = False
        for workflow in sorted((repo / ".github" / "workflows").glob("*.yml")):
            doc, error = load(workflow)
            if doc is None:
                problems.append(f"{workflow.relative_to(root)}: {error}")
                continue
            for name, job in calls(doc, DASHBOARD_WORKFLOW):
                rel = workflow.relative_to(root)
                edited = "edited" in ((triggers(doc).get("issues") or {}).get("types") or [])
                if not edited:
                    problems.append(f"{rel}: calls {DASHBOARD_WORKFLOW} but does not run on `issues: types: [edited]`")
                elif job.get("secrets") != "inherit":
                    problems.append(f"{rel} [{name}]: needs `secrets: inherit` so RENOVATE_TRIGGER_TOKEN reaches it")
                else:
                    found = True
        if found:
            ok += 1
        elif not any(str(p).startswith(f"{repo.name}/") for p in problems):
            problems.append(
                f"{repo.name}: has a renovate.json but no workflow calling {DASHBOARD_WORKFLOW} on `issues: edited`; "
                f"a ticked Dependency Dashboard box would wait for the six-hourly run "
                f"(copy .github/workflows/labs64io-renovate-dashboard.yml from labs64.io-workspace)"
            )
    return ok


def check_maven_callers(root: Path, problems: list[str]) -> None:
    for workflow in sorted(root.glob("labs64.io*/.github/workflows/*.yml")):
        doc, _ = load(workflow)
        for name, job in calls(doc or {}, MAVEN_PUBLISH):
            if job.get("secrets") != "inherit":
                problems.append(
                    f"{workflow.relative_to(root)} [{name}]: calls {MAVEN_PUBLISH} without `secrets: inherit`, "
                    f"so a release cannot ask Renovate to run"
                )


def check_producers(root: Path, problems: list[str]) -> None:
    workspace = root / "labs64.io-workspace"
    publish = workspace / ".github" / "workflows" / MAVEN_PUBLISH
    if publish.is_file():
        doc, error = load(publish)
        if doc is None or not has_step_using(doc, TRIGGER_ACTION):
            problems.append(f"{publish.relative_to(root)}: a release does not run {TRIGGER_ACTION} {error or ''}".rstrip())
    for required in (".github/actions/renovate-trigger/action.yml", f".github/workflows/{DASHBOARD_WORKFLOW}"):
        if workspace.is_dir() and not (workspace / required).is_file():
            problems.append(f"labs64.io-workspace/{required}: missing")

    charts = root / "labs64.io-helm-charts" / ".github" / "workflows"
    releasing = [w for w in sorted(charts.glob("*.yml")) if "chart-releaser-action" in w.read_text()] if charts.is_dir() else []
    for workflow in releasing:
        doc, _ = load(workflow)
        if not has_step_using(doc or {}, TRIGGER_ACTION):
            problems.append(f"{workflow.relative_to(root)}: publishes charts but does not run {TRIGGER_ACTION}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default="..", help="ecosystem root (default: ..)")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    problems: list[str] = []
    callers = check_dashboard_callers(root, problems)
    check_maven_callers(root, problems)
    check_producers(root, problems)

    if problems:
        prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") else "  FAIL  "
        print()
        for problem in problems:
            print(f"{prefix}{problem}")
        print(f"\ncheck-renovate-wiring: {len(problems)} problem(s)")
        return 1
    print(f"  ok  {callers} repositories ask Renovate to run when a dashboard box is ticked")
    print("\ncheck-renovate-wiring: clean — every event that makes a pull request due starts the runner")
    return 0


if __name__ == "__main__":
    sys.exit(main())
