import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.storage.files import (
    BrowsePathError,
    SafetensorsMetadataError,
    UnsupportedFileTypeError,
    list_files,
    read_safetensors_metadata,
    resolve_output_file,
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
