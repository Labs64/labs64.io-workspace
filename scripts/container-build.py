#!/usr/bin/env python3
"""Run a source build in the shared builder with Linux staging and persistent caches."""
import argparse
import os
from pathlib import Path, PureWindowsPath
import subprocess

WORKSPACE = Path(__file__).resolve().parents[1]


def host_path(path):
    """Translate a mounted ecosystem path to the Docker daemon's host path."""
    path = Path(path).resolve()
    host_workspace = os.environ.get("LOCAL_WORKSPACE_FOLDER")
    if not host_workspace:
        return str(path)
    relative = path.relative_to(WORKSPACE.parent)
    if PureWindowsPath(host_workspace).drive:
        return str(PureWindowsPath(host_workspace).parent.joinpath(*relative.parts))
    return str(Path(host_workspace).parent / relative)


def run_build(base_image, source, output, script, cache, settings=None):
    source, output, script = map(lambda p: Path(p).resolve(), (source, output, script))
    if not source.is_dir() or not script.is_file():
        raise ValueError("Build source directory and task script must exist")
    output.mkdir(parents=True, exist_ok=True)
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    gid = os.getgid() if hasattr(os, "getgid") else 1000
    image = f"{cache}-builder"
    subprocess.run([
        "docker", "build", "--build-arg", f"BASE_IMAGE={base_image}",
        "--build-arg", f"USER_ID={uid}", "--build-arg", f"GROUP_ID={gid}",
        "-t", image, "-f", str(WORKSPACE / "scripts/Dockerfile.builder"),
        str(WORKSPACE / "scripts"),
    ], check=True)
    mounts = []
    for suffix in ("m2", "npm"):
        volume, destination = f"{cache}-{suffix}", f"/home/builder/.{suffix}"
        mount = f"type=volume,source={volume},target={destination}"
        # Also supports reuse by a developer with a different UID/GID.
        subprocess.run([
            "docker", "run", "--rm", "--user", "0:0", "--mount", mount,
            "--entrypoint", "chown", image, "-R", f"{uid}:{gid}", destination,
        ], check=True)
        mounts += ["--mount", mount]
    for local, destination, readonly in (
        (source, "/source", True), (output, "/out", False), (script, "/task.sh", True),
    ):
        mounts += ["--mount", f"type=bind,source={host_path(local)},target={destination}" +
                   (",readonly" if readonly else "")]
    if settings:
        settings = Path(settings).resolve()
        if not settings.is_file():
            raise ValueError("Maven settings file does not exist")
        mounts += ["--mount", f"type=bind,source={host_path(settings)},target=/home/builder/.m2/settings.xml,readonly"]
    stage = """set -euo pipefail
mkdir -p /workspaces/build
tar -C /source --exclude=target --exclude=node_modules --exclude=dist --exclude=.local -cf - . |
    tar -C /workspaces/build --no-same-owner -xf -
cd /workspaces/build
export BUILD_OUTPUT=/out
exec bash /task.sh
"""
    subprocess.run([
        "docker", "run", "--rm", "--user", f"{uid}:{gid}", *mounts,
        "-e", "HOME=/home/builder", "-e", "MAVEN_CONFIG=/home/builder/.m2",
        image, "bash", "-c", stage,
    ], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base-image", "source", "output", "script", "cache"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--settings")
    args = parser.parse_args()
    run_build(args.base_image, args.source, args.output, args.script, args.cache, args.settings)
