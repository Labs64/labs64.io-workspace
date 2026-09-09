import importlib.util
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import call, patch

SCRIPT = Path(__file__).resolve().parents[1] / "container-build.py"
spec = importlib.util.spec_from_file_location("container_build", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class HostPathTests(unittest.TestCase):
    def test_host_execution_keeps_local_path(self):
        path = builder.WORKSPACE / "scripts/container-build.py"
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(builder.host_path(path), str(path.resolve()))

    def test_windows_host_from_linux_devcontainer(self):
        path = builder.WORKSPACE.parent / "example-module/file with spaces.txt"
        with patch.dict(os.environ, {"LOCAL_WORKSPACE_FOLDER": r"D:\Work\Labs64\labs64.io-workspace"}):
            self.assertEqual(builder.host_path(path), r"D:\Work\Labs64\example-module\file with spaces.txt")

    def test_posix_host_from_devcontainer(self):
        path = builder.WORKSPACE.parent / "example-module/pom.xml"
        with patch.dict(os.environ, {"LOCAL_WORKSPACE_FOLDER": "/home/dev/ecosystem/labs64.io-workspace"}):
            self.assertEqual(builder.host_path(path).replace("\\", "/"), "/home/dev/ecosystem/example-module/pom.xml")

    def test_unmapped_path_is_rejected_in_devcontainer(self):
        with patch.dict(os.environ, {"LOCAL_WORKSPACE_FOLDER": "/home/dev/ecosystem/labs64.io-workspace"}):
            with self.assertRaises(ValueError):
                builder.host_path(builder.WORKSPACE.parent.parent / "outside/settings.xml")


class BuilderContainerTests(unittest.TestCase):
    @patch.object(builder.subprocess, "run")
    def test_failure_streams_logs_waits_and_removes_container(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0, stdout="7\n"),
            subprocess.CompletedProcess([], 0),
        ]

        with self.assertRaisesRegex(subprocess.CalledProcessError, "exit status 7"):
            builder.run_builder_container(["docker", "run"], "builder-test")

        self.assertEqual(
            run.call_args_list,
            [
                call(
                    ["docker", "run"],
                    stdout=subprocess.DEVNULL,
                    check=True,
                ),
                call(["docker", "logs", "--follow", "builder-test"], check=True),
                call(
                    ["docker", "wait", "builder-test"],
                    capture_output=True,
                    text=True,
                    check=True,
                ),
                call(
                    ["docker", "rm", "--force", "builder-test"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
