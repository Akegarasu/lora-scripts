import subprocess
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

from mikazuki import launch_utils


class LaunchUtilsTests(unittest.TestCase):
    def test_requirements_use_version_order_and_specifiers(self):
        cases = [
            ("example>=5.9", "5.10", True),
            ("example>=5.10", "5.9", False),
            ("example>=2,<3", "3.0", False),
            ("example[extra] == 2.0", "2.0", True),
            ("example==2.0", "2.1", False),
            ("example==2.0", "2.0+cu128", True),
        ]
        for requirement, installed, expected in cases:
            with self.subTest(requirement=requirement, installed=installed):
                with patch.object(launch_utils, "version", return_value=installed) as version:
                    self.assertEqual(launch_utils.is_installed(requirement), expected)
                    version.assert_called_once_with("example")

    def test_missing_distribution_returns_false(self):
        with patch.object(launch_utils, "version", side_effect=PackageNotFoundError):
            self.assertFalse(launch_utils.is_installed("missing-package"))

    def test_non_matching_marker_skips_distribution_lookup(self):
        with patch.object(launch_utils, "version") as version:
            self.assertTrue(launch_utils.is_installed('example; python_version < "1"'))
            version.assert_not_called()

    def test_requirement_file_keeps_requirement_as_one_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory) / "requirements.txt"
            requirements.write_text(
                '  # comment\n\n--index-url https://example.invalid/simple\n'
                'example[extra]>=2; python_version >= "3" # dependency\n'
                'skipped==1 # skip_verify\n--find-links local-wheels\n',
                encoding="utf-8",
            )
            with patch.object(launch_utils, "is_installed", return_value=False) as installed:
                with patch.object(launch_utils, "run_pip") as run_pip:
                    launch_utils.validate_requirements(str(requirements))
            requirement = 'example[extra]>=2; python_version >= "3"'
            installed.assert_called_once_with(requirement)
            run_pip.assert_called_once_with(
                ["install", requirement, "--index-url", "https://example.invalid/simple"],
                requirement,
                live=True,
            )

    def test_pip_arguments_do_not_pass_through_a_shell(self):
        with patch.object(launch_utils, "run", return_value="ok") as run:
            self.assertEqual(launch_utils.run_pip("install example>=2"), "ok")
            self.assertEqual(run.call_args.args[0], [launch_utils.python_bin, "-m", "pip", "install", "example>=2"])
            self.assertFalse(run.call_args.kwargs["shell"])

    def test_missing_bitsandbytes_directory_can_be_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(launch_utils.sys, "platform", "win32"), patch.object(
                launch_utils.sysconfig, "get_paths", return_value={"purelib": directory}
            ), patch.object(launch_utils, "is_installed", return_value=False), patch.object(
                launch_utils, "run_pip"
            ) as run_pip:
                launch_utils.setup_windows_bitsandbytes()
                self.assertEqual(run_pip.call_count, 2)
                self.assertEqual(run_pip.call_args.args[0], "install bitsandbytes==0.46.0")

    def test_old_glibc_uses_compatible_onnxruntime(self):
        with patch.object(launch_utils.sys, "platform", "linux"), patch.object(
            launch_utils.platform, "libc_ver", return_value=("glibc", "2.9")
        ), patch.dict(launch_utils.os.environ, {}, clear=True), patch.object(
            launch_utils, "is_installed", return_value=False
        ), patch.object(launch_utils, "run_pip"), patch.object(launch_utils, "pip_install") as install:
            launch_utils.setup_onnxruntime()
            self.assertEqual(install.call_args.args, ("onnxruntime-gpu", "1.16.3"))

    def test_run_preserves_live_and_captured_output(self):
        for live in (True, False):
            with self.subTest(live=live):
                result = subprocess.CompletedProcess(
                    ["command"], 0, stdout=None if live else b"output", stderr=None if live else b""
                )
                with patch.object(launch_utils.subprocess, "run", return_value=result) as run:
                    self.assertEqual(launch_utils.run(["command"], live=live, shell=False), "" if live else "output")
                    self.assertEqual(run.call_args.kwargs["capture_output"], not live)
                result.returncode = 1
                with patch.object(launch_utils.subprocess, "run", return_value=result):
                    with self.assertRaisesRegex(RuntimeError, "Error code: 1"):
                        launch_utils.run(["command"], live=live, shell=False)


if __name__ == "__main__":
    unittest.main()
