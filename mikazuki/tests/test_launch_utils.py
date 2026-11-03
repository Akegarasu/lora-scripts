import subprocess
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from packaging.markers import default_environment

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

    def test_startup_requires_supported_torch_before_installing(self):
        with patch.dict(launch_utils.os.environ, {}, clear=True), patch.object(
            launch_utils, "is_installed", return_value=False
        ), patch.object(launch_utils, "validate_requirements") as validate, patch.object(
            launch_utils, "setup_windows_bitsandbytes"
        ):
            with self.assertRaisesRegex(RuntimeError, "PyTorch >= 2.6"):
                launch_utils.prepare_environment(prepare_onnxruntime=False)
            validate.assert_not_called()

    def test_startup_uses_project_requirements(self):
        with patch.dict(launch_utils.os.environ, {}, clear=True), patch.object(
            launch_utils, "is_installed", return_value=True
        ), patch.object(launch_utils, "validate_requirements") as validate, patch.object(
            launch_utils, "setup_windows_bitsandbytes"
        ):
            launch_utils.prepare_environment(prepare_onnxruntime=False)
            self.assertEqual(Path(validate.call_args.args[0]), launch_utils.base_dir_path() / "requirements.txt")

    def test_missing_bitsandbytes_directory_is_repaired_using_project_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("bitsandbytes==0.99.0\n", encoding="utf-8")
            with patch.object(launch_utils.sys, "platform", "win32"), patch.object(
                launch_utils.sysconfig, "get_paths", return_value={"purelib": directory}
            ), patch.object(
                launch_utils, "base_dir_path", return_value=root
            ), patch.object(launch_utils, "is_installed", return_value=False), patch.object(
                launch_utils, "run_pip"
            ) as run_pip:
                launch_utils.setup_windows_bitsandbytes()
                self.assertEqual(run_pip.call_count, 2)
                self.assertEqual(run_pip.call_args.args[0], ["install", "bitsandbytes==0.99.0"])

    def test_healthy_bitsandbytes_needs_no_pip_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            bnb = Path(directory) / "bitsandbytes"
            bnb.mkdir()
            (bnb / "libbitsandbytes_cuda130.dll").touch()
            with patch.object(launch_utils.sys, "platform", "win32"), patch.object(
                launch_utils.sysconfig, "get_paths", return_value={"purelib": directory}
            ), patch.object(launch_utils, "is_installed", return_value=True), patch.object(
                launch_utils, "run_pip"
            ) as run_pip:
                launch_utils.setup_windows_bitsandbytes()
                run_pip.assert_not_called()

    def test_unmanaged_cuda_requires_an_explicit_onnx_override(self):
        for cuda in ("11.8", "12.4", "14.0"):
            with self.subTest(cuda=cuda):
                torch = SimpleNamespace(version=SimpleNamespace(cuda=cuda))
                with patch.dict("sys.modules", {"torch": torch}), patch.dict(
                    launch_utils.os.environ, {}, clear=True
                ), patch.object(launch_utils, "run_pip") as uninstall, patch.object(
                    launch_utils, "pip_install"
                ) as install:
                    with self.assertRaisesRegex(
                        RuntimeError, "ONNXRUNTIME_VERSION.*--skip-prepare-onnxruntime"
                    ):
                        launch_utils.setup_onnxruntime()
                    uninstall.assert_not_called()
                    install.assert_not_called()

    def test_default_onnx_pin_follows_cuda_and_python_profiles(self):
        cases = [
            ("13.0", "3.11", "1.31.1"),
            ("12.8", "3.11", "1.26.0"),
            ("12.8", "3.10", "1.23.2"),
            (None, "3.11", "1.26.0"),
        ]
        for cuda, python, expected in cases:
            with self.subTest(cuda=cuda, python=python):
                marker_environment = {**default_environment(), "python_version": python}
                torch = SimpleNamespace(version=SimpleNamespace(cuda=cuda))
                with patch.object(launch_utils.sys, "platform", "win32"), patch.dict(
                    launch_utils.os.environ, {}, clear=True
                ), patch.dict("sys.modules", {"torch": torch}), patch(
                    "packaging.markers.default_environment", return_value=marker_environment
                ), patch.object(launch_utils, "version", side_effect=PackageNotFoundError), patch.object(
                    launch_utils, "run_pip"
                ) as uninstall, patch.object(launch_utils, "pip_install") as install:
                    launch_utils.setup_onnxruntime()
                    uninstall.assert_not_called()
                    install.assert_called_once_with("onnxruntime-gpu", expected, index_url=None, live=True)

    def test_matching_onnx_gpu_needs_no_pip_calls(self):
        def installed_version(name):
            if name == "onnxruntime-gpu":
                return "1.20.1"
            raise PackageNotFoundError(name)

        with patch.dict("sys.modules", {"torch": None}), patch.object(launch_utils.sys, "platform", "win32"), patch.dict(
            launch_utils.os.environ, {}, clear=True
        ), patch.object(launch_utils, "version", side_effect=installed_version), patch.object(
            launch_utils, "run_pip"
        ) as uninstall, patch.object(launch_utils, "pip_install") as install:
            launch_utils.setup_onnxruntime("1.20.1")
            uninstall.assert_not_called()
            install.assert_not_called()

    def test_matching_default_onnx_pin_needs_no_pip_calls(self):
        def installed_version(name):
            if name == "onnxruntime-gpu":
                return "1.31.1"
            raise PackageNotFoundError(name)

        torch = SimpleNamespace(version=SimpleNamespace(cuda="13.0"))
        with patch.dict("sys.modules", {"torch": torch}), patch.object(
            launch_utils.sys, "platform", "win32"
        ), patch.dict(launch_utils.os.environ, {}, clear=True), patch.object(
            launch_utils, "version", side_effect=installed_version
        ), patch.object(launch_utils, "run_pip") as uninstall, patch.object(
            launch_utils, "pip_install"
        ) as install:
            launch_utils.setup_onnxruntime()
            uninstall.assert_not_called()
            install.assert_not_called()

    def test_overlapping_onnx_packages_are_replaced_with_selected_profile(self):
        torch = SimpleNamespace(version=SimpleNamespace(cuda="13.0"))
        with patch.object(launch_utils.sys, "platform", "win32"), patch.dict(
            launch_utils.os.environ, {}, clear=True
        ), patch.dict("sys.modules", {"torch": torch}), patch.object(
            launch_utils, "version", return_value="1.20.1"
        ), patch.object(
            launch_utils, "run_pip"
        ) as uninstall, patch.object(launch_utils, "pip_install") as install:
            launch_utils.setup_onnxruntime()
            uninstall.assert_called_once_with(
                ["uninstall", "-y", "onnxruntime", "onnxruntime-gpu"], "ONNX Runtime", live=True
            )
            install.assert_called_once_with("onnxruntime-gpu", "1.31.1", index_url=None, live=True)

    def test_onnx_environment_pin_replaces_gpu_without_explicit_uninstall(self):
        def installed_version(name):
            if name == "onnxruntime-gpu":
                return "1.19.0"
            raise PackageNotFoundError(name)

        with patch.dict("sys.modules", {"torch": None}), patch.dict(
            launch_utils.os.environ, {"ONNXRUNTIME_VERSION": "1.20.1"}, clear=True
        ), patch.object(launch_utils, "version", side_effect=installed_version), patch.object(
            launch_utils, "run_pip"
        ) as uninstall, patch.object(launch_utils, "pip_install") as install:
            launch_utils.setup_onnxruntime("1.18.0")
            uninstall.assert_not_called()
            install.assert_called_once_with("onnxruntime-gpu", "1.20.1", index_url=None, live=True)

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
