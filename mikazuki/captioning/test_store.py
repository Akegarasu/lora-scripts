import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mikazuki.captioning.models import (
    CaptionCommitRequest,
    CaptionJobCreateRequest,
    CaptionJobSummary,
)
from mikazuki.captioning.store import CaptionStore, CaptionStoreConflict


def _summary(*, state: str = "queued") -> CaptionJobSummary:
    return CaptionJobSummary(
        id="caption_persistence",
        modelId="wd-v1-4-convnext-tagger-v2",
        modelTitle="WD 1.4 ConvNeXt v2",
        outputMode="tags",
        state=state,
        message="queued",
        revision=1,
        datasetId="ds_persistence",
        logPath="C:/logs/caption_persistence.log",
        total=2,
        createdAt="2026-08-01T12:00:00+08:00",
    )


class CaptionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.db_path = self.root / "caption.sqlite3"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_persists_request_items_log_path_and_reconciles_interrupted_job(self) -> None:
        source = self.root / "dataset"
        source.mkdir()
        request = CaptionJobCreateRequest(
            datasetId="ds_persistence",
            modelId="wd-v1-4-convnext-tagger-v2",
            outputMode="tags",
            params={"generalThreshold": 0.42},
        )
        items = [
            {
                "id": f"item_{index}",
                "name": f"{index}.png",
                "relative_path": f"{index}.png",
                "image_path": source / f"{index}.png",
                "caption_path": source / f"{index}.txt",
                "existing_text": "",
                "existing_fingerprint": None,
                "source_root": source,
            }
            for index in range(2)
        ]

        initial = CaptionStore(self.db_path, reconcile=False)
        initial.create_job(_summary(), request, items)
        initial.update_job("caption_persistence", state="generating")
        initial.update_item("caption_persistence", "item_0", state="running")

        restarted = CaptionStore(self.db_path)
        job = restarted.get_job("caption_persistence")
        stored_request = restarted.get_request("caption_persistence")
        running_item = restarted.get_item("caption_persistence", "item_0")
        pending_item = restarted.get_item("caption_persistence", "item_1")

        self.assertIsNotNone(job)
        self.assertEqual(job.state, "interrupted")
        self.assertEqual(job.logPath, "C:/logs/caption_persistence.log")
        self.assertIsNotNone(job.endedAt)
        self.assertEqual(job.failed, 1)
        self.assertEqual(stored_request.params, {"generalThreshold": 0.42})
        self.assertEqual(running_item.state, "failed")
        self.assertIn("服务重启", running_item.error)
        self.assertEqual(pending_item.state, "pending")

        restarted_again = CaptionStore(self.db_path)
        self.assertEqual(restarted_again.reconcile_interrupted_jobs(), 0)
        self.assertEqual(restarted_again.get_job("caption_persistence").state, "interrupted")

    def test_queue_commit_atomically_seals_review_edits(self) -> None:
        source = self.root / "dataset"
        source.mkdir()
        store = CaptionStore(self.db_path, reconcile=False)
        request = CaptionJobCreateRequest(
            datasetId="ds_persistence",
            modelId="wd-v1-4-convnext-tagger-v2",
            outputMode="tags",
            output={"stageBeforeWrite": True},
        )
        store.create_job(
            _summary(state="awaiting_review"),
            request,
            [
                {
                    "id": "item_0",
                    "name": "0.png",
                    "relative_path": "0.png",
                    "image_path": source / "0.png",
                    "caption_path": source / "0.txt",
                    "existing_text": "",
                    "existing_fingerprint": None,
                    "source_root": source,
                    "state": "succeeded",
                }
            ],
        )

        edited = store.edit_review_item("caption_persistence", "item_0", "人工复核")
        self.assertTrue(edited.edited)
        queued = store.queue_commit("caption_persistence", CaptionCommitRequest())
        self.assertEqual(queued.state, "queued")
        self.assertEqual(store.get_commit_request(queued.id).itemIds, None)
        with self.assertRaises(CaptionStoreConflict):
            store.edit_review_item("caption_persistence", "item_0", "迟到的编辑")

    def test_direct_partial_job_rejects_review_edit_and_commit(self) -> None:
        source = self.root / "dataset"
        source.mkdir()
        store = CaptionStore(self.db_path, reconcile=False)
        request = CaptionJobCreateRequest(
            datasetId="ds_direct",
            modelId="wd-v1-4-convnext-tagger-v2",
            outputMode="tags",
        )
        store.create_job(
            _summary(state="partial"),
            request,
            [
                {
                    "id": "item_0",
                    "name": "0.png",
                    "relative_path": "0.png",
                    "image_path": source / "0.png",
                    "caption_path": source / "0.txt",
                    "existing_text": "",
                    "existing_fingerprint": None,
                    "source_root": source,
                    "state": "succeeded",
                }
            ],
        )

        with self.assertRaisesRegex(CaptionStoreConflict, "直接写入任务"):
            store.edit_review_item("caption_persistence", "item_0", "不应允许")
        with self.assertRaisesRegex(CaptionStoreConflict, "直接写入任务"):
            store.queue_commit("caption_persistence", CaptionCommitRequest())

    def test_large_jobs_and_item_filters_are_chunked(self) -> None:
        source = self.root / "dataset"
        source.mkdir()
        store = CaptionStore(self.db_path, reconcile=False)
        request = CaptionJobCreateRequest(
            datasetId="ds_persistence",
            modelId="wd-v1-4-convnext-tagger-v2",
            outputMode="tags",
        )
        items = [
            {
                "id": f"item_{index}",
                "name": f"{index}.png",
                "relative_path": f"{index}.png",
                "image_path": source / f"{index}.png",
                "caption_path": source / f"{index}.txt",
                "existing_text": "",
                "existing_fingerprint": None,
                "source_root": source,
            }
            for index in range(3_000)
        ]

        created = store.create_job(_summary(), request, items)
        selected = store.iter_internal_items(
            created.id,
            item_ids=[f"item_{index}" for index in range(40_000)],
        )

        self.assertEqual(created.total, 3_000)
        self.assertEqual(len(selected), 3_000)
        self.assertEqual(selected[0].id, "item_0")
        self.assertEqual(selected[-1].id, "item_2999")

    def test_two_store_instances_keep_incremental_counters_consistent(self) -> None:
        source = self.root / "dataset"
        source.mkdir()
        first = CaptionStore(self.db_path, reconcile=False)
        request = CaptionJobCreateRequest(
            datasetId="ds_persistence",
            modelId="wd-v1-4-convnext-tagger-v2",
            outputMode="tags",
        )
        first.create_job(
            _summary(),
            request,
            [
                {
                    "id": f"item_{index}",
                    "name": f"{index}.png",
                    "relative_path": f"{index}.png",
                    "image_path": source / f"{index}.png",
                    "caption_path": source / f"{index}.txt",
                    "existing_text": "",
                    "existing_fingerprint": None,
                    "source_root": source,
                }
                for index in range(100)
            ],
        )
        second = CaptionStore(self.db_path, reconcile=False)

        def update_range(store: CaptionStore, start: int, state: str) -> None:
            for index in range(start, start + 50):
                store.update_item(
                    "caption_persistence",
                    f"item_{index}",
                    state=state,
                    written=state == "succeeded",
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            succeeded = executor.submit(update_range, first, 0, "succeeded")
            failed = executor.submit(update_range, second, 50, "failed")
            succeeded.result()
            failed.result()

        completed = first.get_job("caption_persistence")
        self.assertEqual(completed.processed, 100)
        self.assertEqual(completed.succeeded, 50)
        self.assertEqual(completed.failed, 50)
        self.assertEqual(completed.written, 50)

        first.cancel_unfinished_items("caption_persistence")
        first.cancel_unfinished_items("caption_persistence")
        unchanged = first.get_job("caption_persistence")
        self.assertEqual(unchanged.processed, 100)

if __name__ == "__main__":
    unittest.main()
