import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.storage.files import (
    BrowsePathError,
    FileManagerUnavailableError,
    SafetensorsMetadataError,
    UnsupportedFileTypeError,
    file_manager_capability,
    list_files,
    read_safetensors_metadata,
    resolve_output_file,
    resolve_output_path,
    show_output_in_file_manager,
)


class StorageFilesPathBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

        sandbox = Path(self.temporary_directory.name)
        self.root = sandbox / "root"
        self.outside = sandbox / "outside"
        self.inside = self.root / "inside"
        self.inside.mkdir(parents=True)
        self.outside.mkdir()
        (self.inside / "visible.txt").write_text("visible", encoding="utf-8")
        (self.outside / "secret.txt").write_text("secret", encoding="utf-8")

        roots_patcher = patch(
            "mikazuki.storage.files.ROOTS",
            {"test": self.root, "workspace": self.root, "output": self.root},
        )
        roots_patcher.start()
        self.addCleanup(roots_patcher.stop)

    def test_relative_and_absolute_paths_within_root_are_allowed(self) -> None:
        paths = ("inside", str(self.inside.resolve()))

        for path in paths:
            with self.subTest(path=path):
                items = list_files(root="test", path=path)

                self.assertEqual(["visible.txt"], [item.name for item in items])
                self.assertTrue(items[0].modifiedAt.endswith("Z"))

    def test_parent_traversal_outside_root_is_rejected(self) -> None:
        with self.assertRaises(BrowsePathError):
            list_files(root="test", path="../outside")

    def test_absolute_path_outside_root_is_rejected(self) -> None:
        with self.assertRaises(BrowsePathError):
            list_files(root="test", path=str(self.outside.resolve()))

    def test_directory_symlink_to_outside_root_is_rejected(self) -> None:
        link = self.root / "outside-link"
        try:
            link.symlink_to(self.outside, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")

        with self.assertRaises(BrowsePathError):
            list_files(root="test", path=link.name)

    def test_output_file_reader_rejects_outside_and_disallowed_files(self) -> None:
        image = self.inside / "preview.png"
        image.write_bytes(b"image")

        self.assertEqual(image.resolve(), resolve_output_file("inside/preview.png", extensions={".png"}))
        with self.assertRaises(BrowsePathError):
            resolve_output_file("../outside/secret.txt")
        with self.assertRaises(UnsupportedFileTypeError):
            resolve_output_file("inside/visible.txt", extensions={".png"})

    def test_output_path_resolver_accepts_files_and_directories_within_output(self) -> None:
        self.assertEqual(self.inside.resolve(), resolve_output_path("inside"))
        self.assertEqual(
            (self.inside / "visible.txt").resolve(),
            resolve_output_path("inside/visible.txt"),
        )
        with self.assertRaises(BrowsePathError):
            resolve_output_path("../outside")

    def test_file_manager_capability_requires_an_interactive_desktop(self) -> None:
        with (
            patch("mikazuki.storage.files.platform.system", return_value="Windows"),
            patch("mikazuki.storage.files._windows_has_interactive_desktop", return_value=False),
            patch("mikazuki.storage.files.shutil.which") as which,
        ):
            capability = file_manager_capability()

        self.assertFalse(capability["available"])
        self.assertIn("图形化桌面", str(capability["reason"]))
        which.assert_not_called()

    def test_file_manager_capability_detects_windows_explorer(self) -> None:
        with (
            patch("mikazuki.storage.files.platform.system", return_value="Windows"),
            patch("mikazuki.storage.files._windows_has_interactive_desktop", return_value=True),
            patch("mikazuki.storage.files.shutil.which", return_value=r"C:\Windows\explorer.exe"),
        ):
            capability = file_manager_capability()

        self.assertTrue(capability["available"])
        self.assertEqual("windows", capability["platform"])
        self.assertEqual("Windows 文件资源管理器", capability["fileManager"])

    def test_reveal_output_file_uses_explorer_select_without_a_shell(self) -> None:
        target = (self.inside / "visible.txt").resolve()
        capability = {
            "available": True,
            "platform": "windows",
            "fileManager": "Windows 文件资源管理器",
            "reason": None,
        }
        with (
            patch("mikazuki.storage.files.file_manager_capability", return_value=capability),
            patch("mikazuki.storage.files.subprocess.Popen") as popen,
        ):
            revealed = show_output_in_file_manager("inside/visible.txt")

        self.assertEqual(target, revealed)
        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(["explorer.exe", "/select,", str(target)], command)
        self.assertNotIn("shell", options)
        self.assertEqual(subprocess.DEVNULL, options["stdin"])

    def test_reveal_rechecks_capability_before_resolving_or_launching(self) -> None:
        capability = {
            "available": False,
            "platform": "linux",
            "fileManager": None,
            "reason": "当前后端运行环境没有可用的图形化桌面",
        }
        with (
            patch("mikazuki.storage.files.file_manager_capability", return_value=capability),
            patch("mikazuki.storage.files.subprocess.Popen") as popen,
        ):
            with self.assertRaises(FileManagerUnavailableError):
                show_output_in_file_manager("missing.txt")
        popen.assert_not_called()

    def test_reads_bounded_safetensors_metadata_without_tensor_data(self) -> None:
        model = self.inside / "model.safetensors"
        header = json.dumps(
            {
                "weight": {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]},
                "__metadata__": {"ss_output_name": "demo", "ss_epoch": "4"},
            }
        ).encode("utf-8")
        model.write_bytes(len(header).to_bytes(8, "little") + header + b"\x00\x00")

        result = read_safetensors_metadata("inside/model.safetensors")

        self.assertEqual("model.safetensors", result["name"])
        self.assertEqual(1, result["tensorCount"])
        self.assertEqual("demo", result["metadata"]["ss_output_name"])

    def test_rejects_invalid_safetensors_header(self) -> None:
        model = self.inside / "broken.safetensors"
        model.write_bytes((99).to_bytes(8, "little") + b"{}")

        with self.assertRaises(SafetensorsMetadataError):
            read_safetensors_metadata("inside/broken.safetensors")


if __name__ == "__main__":
    unittest.main()
