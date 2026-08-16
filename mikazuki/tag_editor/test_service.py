import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from mikazuki.captioning.datasets import CaptionDatasetRegistry
from mikazuki.tag_editor.models import (
    TagEditorAddOperation,
    TagEditorApplyRequest,
    TagEditorInspectRequest,
    TagEditorPreviewRequest,
    TagEditorReplaceOperation,
    TagEditorScope,
    TagEditorSetOperation,
)
from mikazuki.tag_editor.service import (
    TagEditorConflictError,
    TagEditorService,
    TagEditorValidationError,
)


class TagEditorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "workspace"
        self.train = self.workspace / "train"
        self.train.mkdir(parents=True)
        self.history = self.root / "history"
        registry = CaptionDatasetRegistry(
            roots={
                "train": self.train,
                "datasets": self.train,
                "workspace": self.workspace,
            },
            max_snapshots=8,
            backup_root=self.root / "manual-backups",
        )
        self.service = TagEditorService(
            registry=registry,
            history_root=self.history,
            max_snapshots=8,
            max_change_sets=32,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def make_image(self, relative_path: str) -> Path:
        path = self.train / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (24, 16), (40, 90, 140)).save(path)
        return path

    def make_caption(
        self,
        relative_image_path: str,
        text: str | None = None,
        *,
        raw: bytes | None = None,
    ) -> Path:
        image = self.make_image(relative_image_path)
        caption = image.with_suffix(".txt")
        if raw is not None:
            caption.write_bytes(raw)
        elif text is not None:
            caption.write_text(text, encoding="utf-8")
        return caption

    def inspect(self, *, initial_limit: int = 100):
        return self.service.inspect(
            TagEditorInspectRequest(
                root="train",
                initialLimit=initial_limit,
            )
        )

    def item_ids_by_name(self, dataset_id: str) -> dict[str, str]:
        response = self.service.list_items(dataset_id, limit=500)
        return {item.name: item.id for item in response.items}

    def preview(self, inspected, item_ids, operations):
        return self.service.preview(
            inspected.dataset.id,
            TagEditorPreviewRequest(
                revision=inspected.dataset.revision,
                scope=TagEditorScope(mode="include", includeIds=list(item_ids)),
                operations=operations,
            ),
        )

    def apply(self, inspected, preview, *, backup_existing: bool = True):
        queued = self.service.queue_apply(
            inspected.dataset.id,
            TagEditorApplyRequest(
                changeSetId=preview.id,
                revision=preview.revision,
                backupExisting=backup_existing,
            ),
        )
        self.assertEqual(queued.state, "queued")
        return self.service.apply_change_set(preview.id)

    def rollback(self, change_set_id: str):
        queued = self.service.queue_rollback(change_set_id)
        self.assertEqual(queued.state, "rolling_back")
        return self.service.rollback_change_set(change_set_id)

    def manifest(self, change_set_id: str) -> list[dict]:
        path = self.history / change_set_id / "manifest.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_scan_indexes_filters_duplicates_and_tag_suggestions(self) -> None:
        self.make_caption("a.png", "cat, blue eyes")
        self.make_caption("b.png", "cat, blue eyes")
        self.make_caption("blank.png", "  \n")
        self.make_image("missing.png")
        self.make_caption("invalid.png", raw=b"\xff\xfe")

        inspected = self.inspect(initial_limit=2)

        self.assertEqual(inspected.dataset.total, 5)
        self.assertEqual(len(inspected.items), 2)
        self.assertEqual(inspected.dataset.withCaption, 4)
        self.assertEqual(inspected.dataset.missing, 1)
        self.assertEqual(inspected.dataset.empty, 2)
        self.assertEqual(inspected.dataset.errors, 1)
        self.assertEqual(inspected.dataset.duplicates, 2)

        dataset_id = inspected.dataset.id
        duplicates = self.service.list_items(dataset_id, state="duplicate")
        missing = self.service.list_items(dataset_id, state="missing")
        empty = self.service.list_items(dataset_id, state="empty")
        errors = self.service.list_items(dataset_id, state="errors")
        queried = self.service.list_items(dataset_id, query="BLUE EYES")

        self.assertEqual({item.name for item in duplicates.items}, {"a.png", "b.png"})
        self.assertEqual([item.name for item in missing.items], ["missing.png"])
        self.assertEqual({item.name for item in empty.items}, {"blank.png", "invalid.png"})
        self.assertEqual([item.name for item in errors.items], ["invalid.png"])
        self.assertEqual({item.name for item in queried.items}, {"a.png", "b.png"})
        suggestions = self.service.suggest_tags(dataset_id, query="cat")
        self.assertEqual([(item.text, item.count) for item in suggestions.suggestions], [("cat", 2)])

    def test_explicit_and_filter_minus_exclusions_scopes_are_frozen_without_writes(self) -> None:
        existing = self.make_caption("existing.png", "old")
        missing_a = self.make_image("missing-a.png").with_suffix(".txt")
        missing_b = self.make_image("missing-b.png").with_suffix(".txt")
        inspected = self.inspect()
        ids = self.item_ids_by_name(inspected.dataset.id)

        explicit = self.preview(
            inspected,
            [ids["existing.png"], ids["missing-b.png"]],
            [TagEditorSetOperation(type="set", text="selected")],
        )

        self.assertEqual(explicit.matched, 2)
        self.assertEqual({item.name for item in explicit.diffs}, {"existing.png", "missing-b.png"})
        self.assertEqual(existing.read_text(encoding="utf-8"), "old")
        self.assertFalse(missing_a.exists())
        self.assertFalse(missing_b.exists())
        self.assertFalse(self.history.exists())

        filtered = self.service.preview(
            inspected.dataset.id,
            TagEditorPreviewRequest(
                revision=inspected.dataset.revision,
                scope=TagEditorScope(
                    mode="filter",
                    state="missing",
                    exclusions=[ids["missing-b.png"]],
                ),
                operations=[TagEditorSetOperation(type="set", text="filtered")],
            ),
        )
        self.assertEqual(filtered.matched, 1)
        self.assertEqual(filtered.diffs[0].name, "missing-a.png")
        self.assertFalse(missing_a.exists())

    def test_operations_run_in_declared_order(self) -> None:
        self.make_caption("ordered.png", "cat")
        inspected = self.inspect()
        item_id = self.item_ids_by_name(inspected.dataset.id)["ordered.png"]

        preview = self.preview(
            inspected,
            [item_id],
            [
                TagEditorAddOperation(
                    type="add",
                    mode="text",
                    values=["dog"],
                    separator="|",
                ),
                TagEditorReplaceOperation(
                    type="replace",
                    search="cat|dog",
                    replacement="joined",
                    matchCase=True,
                ),
                TagEditorAddOperation(
                    type="add",
                    mode="text",
                    values=["prefix"],
                    position="start",
                    separator=":",
                ),
            ],
        )

        self.assertEqual(preview.diffs[0].before, "cat")
        self.assertEqual(preview.diffs[0].after, "prefix:joined")

    def test_request_models_forbid_unknown_and_ambiguous_fields(self) -> None:
        with self.assertRaises(ValidationError):
            TagEditorInspectRequest(root="train", unexpected=True)
        with self.assertRaises(ValidationError):
            TagEditorScope(
                mode="include",
                includeIds=["item_one"],
                query="cannot-be-combined",
            )
        with self.assertRaises(ValidationError):
            TagEditorScope(mode="include", includeIds=["item_one", "item_one"])
        with self.assertRaises(ValidationError):
            TagEditorPreviewRequest(
                revision="rev_one",
                scope={"mode": "include", "includeIds": ["item_one"]},
                operations=[{"type": "set", "text": "x", "typoField": True}],
            )

    def test_truncated_source_requires_explicit_set_and_preview_never_writes(self) -> None:
        original = "a" * 100_001
        caption = self.make_caption("long.png", original)
        inspected = self.inspect()
        item_id = self.item_ids_by_name(inspected.dataset.id)["long.png"]
        detail = self.service.get_item(inspected.dataset.id, item_id)

        self.assertTrue(detail.sourceTruncated)
        self.assertEqual(len(detail.captionText), 100_000)
        protected = self.preview(
            inspected,
            [item_id],
            [TagEditorAddOperation(type="add", values=["new tag"])],
        )
        self.assertEqual(protected.changed, 0)
        self.assertEqual(protected.conflicts, 1)
        self.assertEqual(caption.read_text(encoding="utf-8"), original)

        replacement = self.preview(
            inspected,
            [item_id],
            [TagEditorSetOperation(type="set", text="intentional replacement")],
        )
        self.assertEqual(replacement.changed, 1)
        self.assertEqual(replacement.diffs[0].after, "intentional replacement")
        self.assertEqual(caption.read_text(encoding="utf-8"), original)

    def test_regex_rejects_unsafe_constructs_and_times_out(self) -> None:
        self.make_caption("regex.png", "a" * 50_000 + "!")
        inspected = self.inspect()
        item_id = self.item_ids_by_name(inspected.dataset.id)["regex.png"]

        with self.assertRaises(TagEditorValidationError):
            self.preview(
                inspected,
                [item_id],
                [
                    TagEditorReplaceOperation(
                        type="replace",
                        search="(a+)+$",
                        replacement="x",
                        useRegex=True,
                    )
                ],
            )

        with self.assertRaisesRegex(TagEditorValidationError, "100"):
            self.preview(
                inspected,
                [item_id],
                [
                    TagEditorReplaceOperation(
                        type="replace",
                        search="(a|aa)+$",
                        replacement="x",
                        useRegex=True,
                    )
                ],
            )

    def test_apply_writes_manifest_and_isolates_external_conflict(self) -> None:
        first = self.make_caption("first.png", "old first")
        second = self.make_caption("second.png", "old second")
        inspected = self.inspect()
        ids = self.item_ids_by_name(inspected.dataset.id)
        preview = self.preview(
            inspected,
            [ids["first.png"], ids["second.png"]],
            [TagEditorSetOperation(type="set", text="new")],
        )
        second.write_text("external edit", encoding="utf-8")

        applied = self.apply(inspected, preview)

        self.assertEqual(applied.state, "partial")
        self.assertEqual(applied.applied, 1)
        self.assertEqual(applied.conflicts, 1)
        self.assertTrue(applied.canRollback)
        self.assertEqual(first.read_text(encoding="utf-8"), "new")
        self.assertEqual(second.read_text(encoding="utf-8"), "external edit")

        manifest = self.manifest(preview.id)
        events = [entry["event"] for entry in manifest]
        self.assertEqual(events, ["intent", "applied", "conflict"])
        applied_event = manifest[1]
        self.assertIsNotNone(applied_event["beforeFingerprint"])
        self.assertIsNotNone(applied_event["afterFingerprint"])
        self.assertTrue(Path(applied_event["backupPath"]).is_file())

        results = self.service.list_change_results(preview.id)
        self.assertEqual(results.total, 2)
        self.assertEqual(
            {item.relativePath: item.state for item in results.items},
            {"first.png": "applied", "second.png": "conflict"},
        )

    def test_existing_caption_rolls_back_exact_bytes_and_rejects_repeated_actions(self) -> None:
        original = b"\xef\xbb\xbforiginal caption"
        caption = self.make_caption("existing.png", raw=original)
        inspected = self.inspect()
        item_id = self.item_ids_by_name(inspected.dataset.id)["existing.png"]
        preview = self.preview(
            inspected,
            [item_id],
            [TagEditorSetOperation(type="set", text="replacement")],
        )
        applied = self.apply(inspected, preview)

        self.assertEqual(applied.state, "completed")
        self.assertEqual(caption.read_bytes(), b"replacement")
        with self.assertRaises(TagEditorConflictError):
            self.service.queue_apply(
                inspected.dataset.id,
                TagEditorApplyRequest(
                    changeSetId=preview.id,
                    revision=preview.revision,
                ),
            )
        with self.assertRaises(TagEditorConflictError):
            self.service.apply_change_set(preview.id)

        rolled_back = self.rollback(preview.id)
        self.assertEqual(rolled_back.state, "rolled_back")
        self.assertEqual(caption.read_bytes(), original)
        with self.assertRaises(TagEditorConflictError):
            self.service.queue_rollback(preview.id)
        with self.assertRaises(TagEditorConflictError):
            self.service.rollback_change_set(preview.id)

    def test_new_caption_rolls_back_by_removing_the_created_sidecar(self) -> None:
        caption = self.make_image("created.png").with_suffix(".txt")
        inspected = self.inspect()
        item_id = self.item_ids_by_name(inspected.dataset.id)["created.png"]
        preview = self.preview(
            inspected,
            [item_id],
            [TagEditorSetOperation(type="set", text="created caption")],
        )

        applied = self.apply(inspected, preview, backup_existing=False)
        self.assertEqual(applied.state, "completed")
        self.assertTrue(applied.canRollback)
        self.assertEqual(caption.read_text(encoding="utf-8"), "created caption")

        rolled_back = self.rollback(preview.id)
        self.assertEqual(rolled_back.state, "rolled_back")
        self.assertFalse(caption.exists())
        archive = self.history / preview.id / "rollback-created" / "created.txt"
        self.assertEqual(archive.read_text(encoding="utf-8"), "created caption")

    def test_rollback_refuses_to_overwrite_post_apply_external_edit(self) -> None:
        caption = self.make_caption("conflict.png", "original")
        inspected = self.inspect()
        item_id = self.item_ids_by_name(inspected.dataset.id)["conflict.png"]
        preview = self.preview(
            inspected,
            [item_id],
            [TagEditorSetOperation(type="set", text="applied")],
        )
        self.apply(inspected, preview)
        caption.write_text("external after apply", encoding="utf-8")

        rolled_back = self.rollback(preview.id)

        self.assertEqual(rolled_back.state, "rollback_partial")
        self.assertEqual(rolled_back.rolledBack, 0)
        self.assertEqual(rolled_back.rollbackConflicts, 1)
        self.assertEqual(caption.read_text(encoding="utf-8"), "external after apply")
        result = self.service.list_change_results(preview.id).items[0]
        self.assertEqual(result.state, "rollback_conflict")

    def test_change_results_are_paginated_after_batch_apply(self) -> None:
        for index in range(5):
            self.make_image(f"page/{index}.png")
        inspected = self.inspect()
        preview = self.service.preview(
            inspected.dataset.id,
            TagEditorPreviewRequest(
                revision=inspected.dataset.revision,
                scope=TagEditorScope(mode="filter", state="missing"),
                operations=[TagEditorSetOperation(type="set", text="batch")],
            ),
        )
        applied = self.apply(inspected, preview, backup_existing=False)
        self.assertEqual(applied.applied, 5)

        first = self.service.list_change_results(preview.id, offset=0, limit=2)
        middle = self.service.list_change_results(preview.id, offset=2, limit=2)
        last = self.service.list_change_results(preview.id, offset=4, limit=2)

        self.assertEqual((first.total, len(first.items)), (5, 2))
        self.assertEqual((middle.total, len(middle.items)), (5, 2))
        self.assertEqual((last.total, len(last.items)), (5, 1))
        self.assertEqual(
            [item.relativePath for item in first.items + middle.items + last.items],
            [f"page/{index}.png" for index in range(5)],
        )
        self.assertTrue(all(item.state == "applied" for item in first.items + middle.items + last.items))
        with self.assertRaises(TagEditorValidationError):
            self.service.list_change_results(preview.id, offset=-1)


if __name__ == "__main__":
    unittest.main()
