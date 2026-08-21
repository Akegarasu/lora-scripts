import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.captioning.writer import (
    CaptionWriteConflict,
    atomic_write_caption,
    file_fingerprint,
)


class CaptionWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.caption = self.dataset / "nested" / "sample.txt"
        self.caption.parent.mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, text: str, fingerprint, *, backup_existing: bool = False) -> str:
        return atomic_write_caption(
            job_id="caption_writer",
            caption_path=self.caption,
            allowed_root=self.dataset,
            relative_path="nested/sample.png",
            text=text,
            expected_fingerprint=fingerprint,
            backup_existing=backup_existing,
        )

    def test_rejects_external_change_using_full_fingerprint(self) -> None:
        self.caption.write_text("scanned", encoding="utf-8")
        scanned = file_fingerprint(self.caption)
        self.caption.write_text("changed elsewhere", encoding="utf-8")

        with self.assertRaises(CaptionWriteConflict):
            self.write("generated", scanned)

        self.assertEqual(self.caption.read_text(encoding="utf-8"), "changed elsewhere")

    def test_backup_and_manifest_preserve_previous_caption_before_atomic_replace(self) -> None:
        self.caption.write_text("old caption", encoding="utf-8")
        scanned = file_fingerprint(self.caption)

        with patch("mikazuki.captioning.writer.app_root", return_value=self.root):
            written_hash = self.write("new caption", scanned, backup_existing=True)

        backup_root = self.root / "config" / "caption-backups" / "caption_writer"
        backup = backup_root / "nested" / "sample.txt"
        manifest = backup_root / "manifest.jsonl"
        self.assertEqual(self.caption.read_text(encoding="utf-8"), "new caption")
        self.assertEqual(backup.read_text(encoding="utf-8"), "old caption")
        self.assertIn(written_hash, manifest.read_text(encoding="utf-8"))

    def test_replace_failure_keeps_original_and_cleans_temporary_file(self) -> None:
        self.caption.write_text("original", encoding="utf-8")
        scanned = file_fingerprint(self.caption)

        with patch("mikazuki.captioning.writer.os.replace", side_effect=OSError("locked")):
            with self.assertRaisesRegex(OSError, "locked"):
                self.write("replacement", scanned)

        self.assertEqual(self.caption.read_text(encoding="utf-8"), "original")
        self.assertEqual(list(self.caption.parent.glob(".*.tmp")), [])

    def test_output_path_cannot_escape_allowed_dataset_root(self) -> None:
        outside = self.root / "outside.txt"
        with self.assertRaises(CaptionWriteConflict):
            atomic_write_caption(
                job_id="caption_writer",
                caption_path=outside,
                allowed_root=self.dataset,
                relative_path="../outside.png",
                text="unsafe",
                expected_fingerprint=None,
                backup_existing=False,
            )
        self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
