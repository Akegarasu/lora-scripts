import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from mikazuki.captioning.models import (
    CaptionCommitRequest,
    CaptionJobCreateRequest,
    CaptionJobSummary,
    CaptionPrediction,
)
from mikazuki.captioning.store import CaptionStore
from mikazuki.captioning.worker import commit_job, generate_job


class _FakeBatchManager:
    def __init__(self, *, fail_batch: bool = False, fail_red: int | None = None) -> None:
        self.fail_batch = fail_batch
        self.fail_red = fail_red
        self.calls = []
        self.unloaded = False

    def predict_batch(
        self,
        _model_id,
        images,
        _output_mode,
        _params,
        _prompt,
        _postprocess,
        runtime,
    ):
        reds = [image.getpixel((0, 0))[0] for image in images]
        self.calls.append((reds, runtime.batchSize, runtime.keepModelLoaded))
        if self.fail_batch and len(images) > 1:
            raise RuntimeError("synthetic batch failure")
        if self.fail_red is not None and self.fail_red in reds:
            raise RuntimeError(f"synthetic image failure: {self.fail_red}")
        return [CaptionPrediction(text=f"caption {red}") for red in reds]

    def unload(self) -> None:
        self.unloaded = True


class CaptionWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.store = CaptionStore(self.root / "caption.sqlite3", reconcile=False)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_job(
        self,
        reds,
        *,
        job_id: str,
        batch_size: int,
        stage_before_write: bool = True,
        save_raw_result: bool = False,
    ) -> None:
        items = []
        for index, red in enumerate(reds):
            image_path = self.dataset / f"image_{index}.png"
            Image.new("RGB", (12, 12), (red, 20, 30)).save(image_path)
            items.append(
                {
                    "id": f"item_{index}",
                    "name": image_path.name,
                    "relative_path": image_path.name,
                    "image_path": image_path,
                    "caption_path": image_path.with_suffix(".txt"),
                    "existing_text": "",
                    "existing_fingerprint": None,
                    "source_root": self.dataset,
                }
            )
        request = CaptionJobCreateRequest(
            datasetId=f"ds_{job_id}",
            modelId="fake-caption-model",
            outputMode="caption",
            output={
                "stageBeforeWrite": stage_before_write,
                "conflictPolicy": "overwrite",
                "backupExisting": True,
                "saveRawResult": save_raw_result,
            },
            runtime={"device": "cpu", "batchSize": batch_size},
        )
        summary = CaptionJobSummary(
            id=job_id,
            modelId=request.modelId,
            modelTitle="Fake Caption Model",
            outputMode=request.outputMode,
            state="queued",
            message="queued",
            revision=1,
            datasetId=request.datasetId,
            logPath=str(self.root / f"{job_id}.log"),
            total=len(items),
            createdAt="2026-08-01T12:00:00+08:00",
        )
        self.store.create_job(summary, request, items)

    def test_generate_batches_then_review_edit_and_commit_all_captions(self) -> None:
        self.create_job([11, 22, 33], job_id="caption_review", batch_size=2)
        manager = _FakeBatchManager()

        with patch(
            "mikazuki.captioning.worker.get_caption_model_manager",
            return_value=manager,
        ):
            generate_job("caption_review", self.store)

        generated = self.store.get_job("caption_review")
        self.assertEqual(generated.state, "awaiting_review")
        self.assertEqual(generated.succeeded, 3)
        self.assertEqual([len(call[0]) for call in manager.calls], [2, 1])
        self.assertTrue(all(call[1:] == (2, True) for call in manager.calls))
        self.assertTrue(manager.unloaded)
        self.assertFalse(any(self.dataset.glob("*.txt")))

        edited = self.store.edit_review_item("caption_review", "item_0", "人工修订 Caption")
        self.assertTrue(edited.edited)
        self.store.queue_commit("caption_review", CaptionCommitRequest())
        commit_job("caption_review", self.store)

        committed = self.store.get_job("caption_review")
        self.assertEqual(committed.state, "succeeded")
        self.assertEqual(committed.written, 3)
        self.assertEqual(
            (self.dataset / "image_0.txt").read_text(encoding="utf-8"),
            "人工修订 Caption",
        )
        self.assertEqual(
            (self.dataset / "image_1.txt").read_text(encoding="utf-8"),
            "caption 22",
        )
        self.assertEqual(committed.detailsState, "available")

    def test_direct_write_compacts_successful_item_payloads_after_completion(self) -> None:
        self.create_job(
            [31, 32],
            job_id="caption_direct",
            batch_size=2,
            stage_before_write=False,
        )
        manager = _FakeBatchManager()
        lifecycle = Mock()

        with patch.object(
            self.store,
            "compact_direct_job_items",
            wraps=self.store.compact_direct_job_items,
        ) as compact_call, patch.object(
            self.store,
            "update_job",
            wraps=self.store.update_job,
        ) as update_call:
            lifecycle.attach_mock(compact_call, "compact")
            lifecycle.attach_mock(update_call, "update")
            with patch(
                "mikazuki.captioning.worker.get_caption_model_manager",
                return_value=manager,
            ):
                generate_job("caption_direct", self.store)

        completed = self.store.get_job("caption_direct")
        items = self.store.list_items("caption_direct", offset=0, limit=10).items
        internal = self.store.get_internal_item("caption_direct", "item_0")
        self.assertEqual(completed.state, "succeeded")
        self.assertFalse(completed.reviewMode)
        self.assertEqual(completed.detailsState, "compacted")
        self.assertEqual(completed.written, 2)
        self.assertEqual([item.generatedText for item in items], ["", ""])
        self.assertEqual([item.finalText for item in items], ["", ""])
        self.assertTrue(all(item.written for item in items))
        self.assertEqual(internal.tags_json, "[]")
        self.assertIsNone(internal.existing_fingerprint)
        self.assertIsNone(internal.raw_json)
        self.assertIsNone(internal.written_hash)
        compact_position = next(
            index
            for index, call in enumerate(lifecycle.mock_calls)
            if call[0] == "compact"
        )
        terminal_position = next(
            index
            for index, call in enumerate(lifecycle.mock_calls)
            if call[0] == "update" and call[2].get("state") == "succeeded"
        )
        self.assertLess(compact_position, terminal_position)
        self.assertEqual(
            (self.dataset / "image_0.txt").read_text(encoding="utf-8"),
            "caption 31",
        )

    def test_direct_write_preserves_details_when_raw_retention_is_explicit(self) -> None:
        self.create_job(
            [61],
            job_id="caption_direct_raw",
            batch_size=1,
            stage_before_write=False,
            save_raw_result=True,
        )
        manager = _FakeBatchManager()

        with patch(
            "mikazuki.captioning.worker.get_caption_model_manager",
            return_value=manager,
        ):
            generate_job("caption_direct_raw", self.store)

        completed = self.store.get_job("caption_direct_raw")
        item = self.store.get_item("caption_direct_raw", "item_0")
        self.assertEqual(completed.detailsState, "available")
        self.assertEqual(item.generatedText, "caption 61")
        self.assertEqual(item.finalText, "caption 61")

    def test_failed_batch_falls_back_per_image_and_isolates_bad_prediction(self) -> None:
        self.create_job([41, 42, 43], job_id="caption_fallback", batch_size=3)
        manager = _FakeBatchManager(fail_batch=True, fail_red=42)

        with patch(
            "mikazuki.captioning.worker.get_caption_model_manager",
            return_value=manager,
        ):
            generate_job("caption_fallback", self.store)

        items = self.store.list_items("caption_fallback", offset=0, limit=10).items
        self.assertEqual([len(call[0]) for call in manager.calls], [3, 1, 1, 1])
        self.assertEqual([item.state for item in items], ["succeeded", "failed", "succeeded"])
        self.assertIn("synthetic image failure: 42", items[1].error)
        self.assertEqual(self.store.get_job("caption_fallback").state, "awaiting_review")
        self.assertTrue(manager.unloaded)

        self.store.edit_review_item("caption_fallback", "item_1", "manually repaired")
        self.store.queue_commit(
            "caption_fallback",
            CaptionCommitRequest(conflictPolicy="overwrite"),
        )
        commit_job("caption_fallback", self.store)

        self.assertEqual(self.store.get_job("caption_fallback").state, "succeeded")
        self.assertEqual(
            (self.dataset / "image_1.txt").read_text(encoding="utf-8"),
            "manually repaired",
        )

    def test_partial_selection_stays_reviewable_and_does_not_rewrite_committed_items(self) -> None:
        self.create_job([51, 52, 53], job_id="caption_selection", batch_size=2)
        manager = _FakeBatchManager()
        with patch(
            "mikazuki.captioning.worker.get_caption_model_manager",
            return_value=manager,
        ):
            generate_job("caption_selection", self.store)

        self.store.queue_commit(
            "caption_selection",
            CaptionCommitRequest(itemIds=["item_0"]),
        )
        commit_job("caption_selection", self.store)
        first_commit = self.store.get_job("caption_selection")
        self.assertEqual(first_commit.state, "awaiting_review")
        self.assertEqual(first_commit.written, 1)

        self.store.queue_commit("caption_selection", CaptionCommitRequest())
        commit_job("caption_selection", self.store)
        final = self.store.get_job("caption_selection")
        self.assertEqual(final.state, "succeeded")
        self.assertEqual(final.written, 3)
        self.assertEqual(final.conflicts, 0)
        self.assertEqual(
            (self.dataset / "image_0.txt").read_text(encoding="utf-8"),
            "caption 51",
        )


if __name__ == "__main__":
    unittest.main()
