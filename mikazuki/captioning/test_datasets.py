import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mikazuki.captioning.datasets import (
    CaptionDatasetConflictError,
    CaptionDatasetNotFoundError,
    CaptionDatasetPathError,
    CaptionDatasetRegistry,
)
from mikazuki.captioning.models import (
    CaptionDatasetInspectRequest,
    CaptionTextUpdateRequest,
)


class CaptionDatasetRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary_directory.name)
        self.workspace = self.temp_path / "workspace"
        self.train = self.workspace / "train"
        self.train.mkdir(parents=True)
        self.backups = self.temp_path / "backups"
        self.registry = CaptionDatasetRegistry(
            roots={
                "train": self.train,
                "datasets": self.train,
                "workspace": self.workspace,
            },
            max_snapshots=2,
            backup_root=self.backups,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def make_image(
        self,
        relative_path: str,
        *,
        size: tuple[int, int] = (32, 24),
        image_format: str | None = None,
    ) -> Path:
        path = self.train / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (28, 92, 156)).save(path, format=image_format)
        return path

    def inspect(
        self,
        *,
        path: str = "",
        recursive: bool = True,
        extension: str = ".txt",
        max_images: int = 10_000,
        initial_limit: int = 100,
        root: str = "train",
    ):
        return self.registry.inspect(
            CaptionDatasetInspectRequest(
                root=root,
                path=path,
                recursive=recursive,
                captionExtension=extension,
                maxImages=max_images,
                initialLimit=initial_limit,
            )
        )

    def test_caption_extension_cannot_target_executable_or_config_files(self) -> None:
        with self.assertRaisesRegex(ValueError, "安全的文本扩展名"):
            CaptionDatasetInspectRequest(captionExtension=".py")
        self.assertEqual(
            CaptionDatasetInspectRequest(captionExtension="caption").captionExtension,
            ".caption",
        )

    def test_enumerates_five_training_formats_recursively_in_stable_order(self) -> None:
        self.make_image("z.BMP")
        self.make_image("A.JPG")
        self.make_image("nested/c.jpeg")
        self.make_image("nested/d.PNG")
        self.make_image("nested/e.webp")
        (self.train / "ignored.gif").write_bytes(b"GIF89a")
        (self.train / "notes.txt").write_text("not an image", encoding="utf-8")

        response = self.inspect()

        self.assertEqual(response.dataset.total, 5)
        self.assertEqual(
            [item.relativePath for item in response.items],
            ["A.JPG", "nested/c.jpeg", "nested/d.PNG", "nested/e.webp", "z.BMP"],
        )
        self.assertTrue(all(item.width == 32 and item.height == 24 for item in response.items))

    def test_non_recursive_scan_skips_nested_and_hidden_entries(self) -> None:
        self.make_image("visible.png")
        self.make_image("nested/nested.jpg")
        self.make_image(".hidden.png")
        self.make_image(".hidden/inside.jpg")

        flat = self.inspect(recursive=False)
        recursive = self.inspect(recursive=True)

        self.assertEqual([item.relativePath for item in flat.items], ["visible.png"])
        self.assertEqual(
            [item.relativePath for item in recursive.items],
            ["nested/nested.jpg", "visible.png"],
        )

    def test_scan_limit_marks_snapshot_truncated(self) -> None:
        for index in range(3):
            self.make_image(f"{index}.png")

        response = self.inspect(max_images=2)

        self.assertEqual(response.dataset.total, 2)
        self.assertTrue(response.dataset.truncated)

    def test_thousand_image_inspect_returns_only_a_bounded_initial_gallery_page(self) -> None:
        for index in range(1_205):
            self.make_image(f"page/{index:04d}.png", size=(4, 4))

        default_page = self.inspect()
        small_page = self.inspect(initial_limit=17)

        self.assertEqual(default_page.dataset.total, 1_205)
        self.assertEqual(len(default_page.items), 100)
        self.assertEqual(len(small_page.items), 17)
        last_page = self.registry.list_items(
            default_page.dataset.id,
            offset=1_200,
            limit=100,
        )
        self.assertEqual(last_page.total, 1_205)
        self.assertEqual(len(last_page.items), 5)

    def test_initial_gallery_limit_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            CaptionDatasetInspectRequest(initialLimit=201)

    def test_dataset_and_item_ids_are_opaque_and_lru_snapshots_expire(self) -> None:
        self.make_image("one.png")
        first = self.inspect()
        second = self.inspect()
        third = self.inspect()

        self.assertTrue(first.dataset.id.startswith("ds_"))
        self.assertNotIn("one.png", first.dataset.id)
        self.assertTrue(first.items[0].id.startswith("item_"))
        self.assertNotIn("one.png", first.items[0].id)
        self.assertNotEqual(first.dataset.id, second.dataset.id)
        self.assertIsNotNone(self.registry.get_snapshot(third.dataset.id))
        with self.assertRaises(CaptionDatasetNotFoundError):
            self.registry.get_snapshot(first.dataset.id)

    def test_absolute_and_parent_traversal_paths_cannot_escape_selected_root(self) -> None:
        outside = self.temp_path / "outside"
        outside.mkdir()
        Image.new("RGB", (8, 8)).save(outside / "outside.png")

        with self.assertRaises(CaptionDatasetPathError):
            self.inspect(path="../outside")
        with self.assertRaises(CaptionDatasetPathError):
            self.inspect(path=str(outside))

        inside = self.train / "inside"
        inside.mkdir()
        allowed = self.inspect(path=str(inside))
        self.assertEqual(allowed.dataset.path, "inside")

    def test_symbolic_links_are_not_followed_and_escape_path_is_rejected(self) -> None:
        outside = self.temp_path / "outside"
        outside.mkdir()
        Image.new("RGB", (8, 8)).save(outside / "outside.png")
        link = self.train / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symbolic links unavailable: {error}")

        response = self.inspect()
        self.assertEqual(response.dataset.total, 0)
        with self.assertRaises(CaptionDatasetPathError):
            self.inspect(path="linked")

    def test_caption_extension_is_normalized_and_utf8_bom_is_read(self) -> None:
        image = self.make_image("unicode.png")
        image.with_suffix(".caption").write_bytes("角色, 蓝色眼睛".encode("utf-8-sig"))

        response = self.inspect(extension="caption")
        item = response.items[0]

        self.assertEqual(response.dataset.captionExtension, ".caption")
        self.assertTrue(item.captionExists)
        self.assertEqual(item.captionText, "角色, 蓝色眼睛")
        self.assertEqual(response.dataset.withCaption, 1)

        snapshot = self.registry.get_snapshot(response.dataset.id)
        record = snapshot.items[item.id]
        self.assertEqual(snapshot.source_root, self.train.resolve())
        self.assertEqual(snapshot.source_path, self.train.resolve())
        self.assertEqual(record.image_path, image.resolve())
        self.assertEqual(
            self.registry.resolve_image(response.dataset.id, item.id),
            image.resolve(),
        )
        self.assertEqual(record.caption_path, image.with_suffix(".caption").resolve())
        self.assertEqual(record.existing_text, "角色, 蓝色眼睛")
        self.assertEqual(record.relative_path, "unicode.png")
        self.assertEqual(
            set(record.fingerprint or {}),
            {"size", "mtimeNs", "sha256"},
        )

    def test_invalid_utf8_and_corrupt_images_are_reported_per_item(self) -> None:
        image = self.make_image("invalid.png")
        image.with_suffix(".txt").write_bytes(b"\xff\xfe")
        (self.train / "broken.jpg").write_bytes(b"not-a-jpeg")

        response = self.inspect()
        errors = {item.name: item.dict().get("errorCode") for item in response.items}

        self.assertIn("image.invalid", errors["broken.jpg"])
        self.assertIn("caption.invalid", errors["invalid.png"])

    def test_long_utf8_caption_is_truncated_for_preview(self) -> None:
        image = self.make_image("long.png")
        image.with_suffix(".txt").write_text("界" * 100_001, encoding="utf-8")

        item = self.inspect().items[0]

        self.assertTrue(item.captionTruncated)
        self.assertEqual(len(item.captionText), 100_000)

    def test_manual_save_can_repair_invalid_utf8_with_backup(self) -> None:
        image = self.make_image("repair.png")
        caption = image.with_suffix(".txt")
        caption.write_bytes(b"\xff\xfe")
        response = self.inspect()
        item = response.items[0]

        self.assertTrue(item.writable)
        repaired = self.registry.save_caption(
            response.dataset.id,
            item.id,
            CaptionTextUpdateRequest(text="repaired", backupExisting=True),
        )

        self.assertEqual(repaired.captionText, "repaired")
        self.assertIsNone(repaired.error)
        self.assertEqual(caption.read_text(encoding="utf-8"), "repaired")
        backups = list(self.backups.rglob("*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"\xff\xfe")

    def test_same_stem_images_are_both_reported_as_non_writable_conflicts(self) -> None:
        self.make_image("same.jpg")
        self.make_image("same.png")

        response = self.inspect()

        self.assertEqual(response.dataset.total, 2)
        for item in response.items:
            public = item.dict()
            self.assertEqual(public.get("errorCode"), "caption.path_collision")
            self.assertFalse(public.get("writable"))
            record = self.registry.get_record(response.dataset.id, item.id)
            self.assertFalse(record.writable)

    def test_items_support_pagination_caption_filter_error_filter_and_query(self) -> None:
        apple = self.make_image("apple.png")
        apple.with_suffix(".txt").write_text("red fruit", encoding="utf-8")
        self.make_image("banana.png")
        broken = self.make_image("broken.png")
        broken.with_suffix(".txt").write_bytes(b"\xff")
        response = self.inspect()

        first_page = self.registry.list_items(response.dataset.id, offset=0, limit=2)
        with_caption = self.registry.list_items(
            response.dataset.id,
            offset=0,
            limit=10,
            caption_state="with_caption",
        )
        errors = self.registry.list_items(
            response.dataset.id,
            offset=0,
            limit=10,
            caption_state="errors",
        )
        query = self.registry.list_items(
            response.dataset.id,
            offset=0,
            limit=10,
            query="FRUIT",
        )

        self.assertEqual(first_page.total, 3)
        self.assertEqual(len(first_page.items), 2)
        self.assertEqual(with_caption.total, 2)
        self.assertEqual(errors.total, 1)
        self.assertEqual(errors.items[0].name, "broken.png")
        self.assertEqual([item.name for item in query.items], ["apple.png"])

    def test_thumbnail_returns_bounded_jpeg_without_exposing_local_path(self) -> None:
        self.make_image("wide.png", size=(400, 100))
        response = self.inspect()
        item = response.items[0]

        content = self.registry.thumbnail(response.dataset.id, item.id, max_size=80)

        self.assertTrue(content.startswith(b"\xff\xd8"))
        with Image.open(io.BytesIO(content)) as thumbnail:
            self.assertEqual(thumbnail.format, "JPEG")
            self.assertLessEqual(max(thumbnail.size), 80)
        self.assertNotIn(str(self.train), item.thumbnailUrl)

    def test_manual_save_is_atomic_updates_snapshot_and_preserves_backup(self) -> None:
        image = self.make_image("saved.png")
        caption = image.with_suffix(".txt")
        caption.write_text("old caption", encoding="utf-8")
        response = self.inspect()
        item = response.items[0]

        updated = self.registry.save_caption(
            response.dataset.id,
            item.id,
            CaptionTextUpdateRequest(text="new 中文 caption", backupExisting=True),
        )

        self.assertEqual(caption.read_text(encoding="utf-8"), "new 中文 caption")
        self.assertEqual(updated.captionText, "new 中文 caption")
        backups = list(self.backups.rglob("*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b"old caption")
        self.assertEqual(list(caption.parent.glob(f".{caption.name}.*.tmp")), [])

    def test_identical_manual_save_does_not_create_backup(self) -> None:
        image = self.make_image("same.png")
        image.with_suffix(".txt").write_text("unchanged", encoding="utf-8")
        response = self.inspect()

        self.registry.save_caption(
            response.dataset.id,
            response.items[0].id,
            CaptionTextUpdateRequest(text="unchanged", backupExisting=True),
        )

        self.assertEqual(list(self.backups.rglob("*.bak")), [])

    def test_manual_save_detects_external_caption_change(self) -> None:
        image = self.make_image("conflict.png")
        caption = image.with_suffix(".txt")
        caption.write_text("at inspect", encoding="utf-8")
        response = self.inspect()
        caption.write_text("external edit", encoding="utf-8")

        with self.assertRaises(CaptionDatasetConflictError):
            self.registry.save_caption(
                response.dataset.id,
                response.items[0].id,
                CaptionTextUpdateRequest(text="ui edit", backupExisting=True),
            )

        self.assertEqual(caption.read_text(encoding="utf-8"), "external edit")
        self.assertEqual(list(self.backups.rglob("*.bak")), [])

    def test_replace_failure_keeps_original_and_removes_temporary_file(self) -> None:
        image = self.make_image("failure.png")
        caption = image.with_suffix(".txt")
        caption.write_text("original", encoding="utf-8")
        response = self.inspect()

        with patch("mikazuki.captioning.datasets.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                self.registry.save_caption(
                    response.dataset.id,
                    response.items[0].id,
                    CaptionTextUpdateRequest(text="replacement", backupExisting=True),
                )

        self.assertEqual(caption.read_text(encoding="utf-8"), "original")
        self.assertEqual(list(caption.parent.glob(f".{caption.name}.*.tmp")), [])
        self.assertEqual(len(list(self.backups.rglob("*.bak"))), 1)

    def test_collision_item_cannot_be_saved(self) -> None:
        self.make_image("same.jpg")
        self.make_image("same.png")
        response = self.inspect()

        with self.assertRaises(CaptionDatasetConflictError):
            self.registry.save_caption(
                response.dataset.id,
                response.items[0].id,
                CaptionTextUpdateRequest(text="must not be written"),
            )

        self.assertFalse((self.train / "same.txt").exists())


if __name__ == "__main__":
    unittest.main()
