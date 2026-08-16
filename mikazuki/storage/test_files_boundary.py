import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.storage.files import BrowsePathError, list_files


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
            {"test": self.root, "workspace": self.root},
        )
        roots_patcher.start()
        self.addCleanup(roots_patcher.stop)

    def test_relative_and_absolute_paths_within_root_are_allowed(self) -> None:
        paths = ("inside", str(self.inside.resolve()))

        for path in paths:
            with self.subTest(path=path):
                items = list_files(root="test", path=path)

                self.assertEqual(["visible.txt"], [item.name for item in items])

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


if __name__ == "__main__":
    unittest.main()
