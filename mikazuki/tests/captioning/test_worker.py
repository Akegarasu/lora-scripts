import os
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
from mikazuki.captioning.writer import file_fingerprint


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
        policy: str = "overwrite",
        existing=None,
        output_mode: str = "caption",
        postprocess=None,
    ) -> None:
        items = []
        for index, red in enumerate(reds):
            image_path = self.dataset / f"image_{index}.png"
            Image.new("RGB", (12, 12), (red, 20, 30)).save(image_path)
            caption_path = image_path.with_suffix(".txt")
            caption_path.unlink(missing_ok=True)
            text = existing[index] if existing is not None else None
            if text is not None:
                caption_path.write_text(text, encoding="utf-8")
            items.append(
                {
                    "id": f"item_{index}",
                    "name": image_path.name,
                    "relative_path": image_path.name,
                    "image_path": image_path,
                    "caption_path": caption_path,
                    "existing_text": text or "",
                    "existing_fingerprint": file_fingerprint(caption_path),
                    "source_root": self.dataset,
                }
            )
        request = CaptionJobCreateRequest(
            datasetId=f"ds_{job_id}",
            modelId="fake-caption-model",
            outputMode=output_mode,
            postprocess=postprocess or {},
            output={
                "stageBeforeWrite": stage_before_write,
                "conflictPolicy": policy,
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

    def test_all_output_policies_through_direct_and_review_workflows(self) -> None:
        expected = {
            "skip": ["caption 11", "", "  original  "],
            "fill_empty": ["caption 11", "caption 22", "  original  "],
            "overwrite": ["caption 11", "caption 22", "caption 33"],
            "prepend": ["caption 11", "caption 22", "caption 33, original"],
            "append": ["caption 11", "caption 22", "original, caption 33"],
        }
        for review in (False, True):
            for policy, texts in expected.items():
                with self.subTest(review=review, policy=policy):
                    job_id = f"caption_policy_{review}_{policy}"
                    self.create_job(
                        [11, 22, 33], job_id=job_id, batch_size=3,
                        stage_before_write=review, save_raw_result=True,
                        policy=policy, existing=[None, "", "  original  "],
                    )
                    manager = _FakeBatchManager()
                    with (
                        patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=manager),
                        patch("mikazuki.captioning.writer.app_root", return_value=self.root),
                    ):
                        generate_job(job_id, self.store)
                        if review:
                            self.assertEqual(self.store.get_job(job_id).state, "awaiting_review")
                            self.assertEqual(self.store.get_job(job_id).written, 0)
                            self.assertFalse((self.dataset / "image_0.txt").exists())
                            self.assertEqual((self.dataset / "image_2.txt").read_text(encoding="utf-8"), "  original  ")
                            self.store.queue_commit(job_id, CaptionCommitRequest())
                            commit_job(job_id, self.store)

                    summary = self.store.get_job(job_id)
                    skipped = 2 if policy == "skip" else 1 if policy == "fill_empty" else 0
                    self.assertEqual(summary.state, "succeeded")
                    self.assertEqual(summary.processed, 3)
                    self.assertEqual(summary.succeeded, 3 - skipped)
                    self.assertEqual(summary.skipped, skipped)
                    self.assertEqual(summary.written, 3 - skipped)
                    self.assertEqual(summary.failed, 0)
                    self.assertEqual(summary.conflicts, 0)
                    self.assertEqual(summary.detailsState, "available")
                    self.assertTrue(manager.unloaded)
                    self.assertEqual(manager.calls[0][0], [11] if policy == "skip" and not review else [11, 22, 33])
                    for index, text in enumerate(texts):
                        self.assertEqual((self.dataset / f"image_{index}.txt").read_text(encoding="utf-8"), text)
                    backup = self.root / "config" / "caption-backups" / job_id / "image_2.txt"
                    if policy in {"overwrite", "prepend", "append"}:
                        self.assertEqual(backup.read_text(encoding="utf-8"), "  original  ")
                    else:
                        self.assertFalse(backup.exists())

    def test_prediction_metadata_and_affixes_survive_review_commit(self) -> None:
        for mode in ("tags", "caption", "hybrid"):
            with self.subTest(mode=mode):
                job_id = f"caption_metadata_{mode}"
                self.create_job(
                    [11], job_id=job_id, batch_size=1, save_raw_result=True,
                    output_mode=mode,
                    postprocess={"prefix": " prefix ", "suffix": " suffix ", "separator": " | "},
                )
                prediction = CaptionPrediction(text=" generated ", tags=[{"text": "tag", "score": 0.8}], raw={"test": 42})
                manager = Mock()
                manager.predict_batch.return_value = [prediction]
                with patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=manager):
                    generate_job(job_id, self.store)
                before = self.store.get_internal_item(job_id, "item_0")
                expected = "generated" if mode == "tags" else "prefix | generated | suffix"
                self.assertEqual(before.generated_text, expected)
                self.assertEqual(before.final_text, expected)
                self.assertIsNotNone(before.elapsed_ms)
                self.store.queue_commit(job_id, CaptionCommitRequest())
                commit_job(job_id, self.store)
                after = self.store.get_internal_item(job_id, "item_0")
                for field in ("generated_text", "tags_json", "raw_json", "elapsed_ms"):
                    self.assertEqual(getattr(after, field), getattr(before, field))
                self.assertEqual((self.dataset / "image_0.txt").read_text(encoding="utf-8"), expected)

    def test_external_changes_are_conflicts_in_both_write_paths(self) -> None:
        for review in (False, True):
            with self.subTest(review=review):
                job_id = f"caption_conflict_{review}"
                self.create_job([11], job_id=job_id, batch_size=1, stage_before_write=review)
                caption = self.dataset / "image_0.txt"
                if not review:
                    caption.write_text("external", encoding="utf-8")
                with patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=_FakeBatchManager()):
                    generate_job(job_id, self.store)
                if review:
                    caption.write_text("external", encoding="utf-8")
                    self.store.queue_commit(job_id, CaptionCommitRequest())
                    commit_job(job_id, self.store)
                summary = self.store.get_job(job_id)
                item = self.store.get_item(job_id, "item_0")
                self.assertEqual(summary.state, "partial" if review else "failed")
                self.assertEqual(summary.conflicts, 1)
                self.assertEqual(summary.written, 0)
                self.assertEqual(item.state, "conflict")
                self.assertIn("扫描后被其他程序修改", item.error)
                self.assertEqual(caption.read_text(encoding="utf-8"), "external")

    def test_write_failure_isolated_from_remaining_items_and_temporary_files_cleaned(self) -> None:
        for review in (False, True):
            with self.subTest(review=review):
                job_id = f"caption_write_failure_{review}"
                self.create_job([11, 22], job_id=job_id, batch_size=2, stage_before_write=review)
                replace = os.replace

                def fail_first(source, destination):
                    if Path(destination).name == "image_0.txt":
                        raise OSError("synthetic write failure")
                    return replace(source, destination)

                manager = _FakeBatchManager()
                with (
                    patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=manager),
                    patch("mikazuki.captioning.writer.os.replace", side_effect=fail_first),
                ):
                    generate_job(job_id, self.store)
                    if review:
                        self.store.queue_commit(job_id, CaptionCommitRequest())
                        commit_job(job_id, self.store)
                summary = self.store.get_job(job_id)
                self.assertEqual((summary.state, summary.failed, summary.written), ("partial", 1, 1))
                self.assertFalse((self.dataset / "image_0.txt").exists())
                self.assertEqual((self.dataset / "image_1.txt").read_text(encoding="utf-8"), "caption 22")
                self.assertEqual(list(self.dataset.glob("*.tmp")), [])
                self.assertTrue(manager.unloaded)

    def test_cancel_during_inference_preserves_completed_work_and_releases_images(self) -> None:
        for review, retain in ((False, False), (False, True), (True, False)):
            with self.subTest(review=review, retain=retain):
                job_id = f"caption_canceled_{review}_{retain}"
                self.create_job([11, 22, 33], job_id=job_id, batch_size=1, stage_before_write=review, save_raw_result=retain)
                manager = Mock()
                images = []

                def predict(*args):
                    images.extend(args[1])
                    if len(images) == 2:
                        self.store.update_job(job_id, state="canceling")
                    return [CaptionPrediction(text="generated")]

                manager.predict_batch.side_effect = predict
                with patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=manager):
                    generate_job(job_id, self.store)
                summary = self.store.get_job(job_id)
                items = self.store.list_items(job_id).items
                self.assertEqual(summary.state, "canceled")
                self.assertIsNotNone(summary.endedAt)
                self.assertEqual(summary.processed, 3)
                self.assertEqual([item.state for item in items], ["succeeded", "canceled", "canceled"])
                self.assertEqual(summary.written, 0 if review else 1)
                self.assertEqual(summary.detailsState, "available" if review or retain else "compacted")
                self.assertEqual(items[0].generatedText, "generated" if review or retain else "")
                manager.unload.assert_called_once()
                for image in images:
                    with self.assertRaises(ValueError):
                        image.getpixel((0, 0))

    def test_commit_options_override_staging_policy_and_backup_default(self) -> None:
        self.create_job([11], job_id="caption_override", batch_size=1, policy="skip", existing=["original"])
        with patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=_FakeBatchManager()):
            generate_job("caption_override", self.store)
        staged = self.store.get_item("caption_override", "item_0")
        self.assertEqual(staged.generatedText, "caption 11")
        self.assertEqual(staged.finalText, "original")
        self.store.queue_commit("caption_override", CaptionCommitRequest(conflictPolicy="append", backupExisting=False))
        with patch("mikazuki.captioning.writer.app_root", return_value=self.root):
            commit_job("caption_override", self.store)
        self.assertEqual((self.dataset / "image_0.txt").read_text(encoding="utf-8"), "original, caption 11")
        self.assertFalse((self.root / "config" / "caption-backups").exists())
        self.assertEqual(self.store.get_job("caption_override").written, 1)

    def test_review_edits_preserve_empty_and_untrimmed_text_even_with_skip_policy(self) -> None:
        for index, text in enumerate(("", "  manual edit  ")):
            with self.subTest(text=text):
                job_id = f"caption_verbatim_{index}"
                self.create_job([11], job_id=job_id, batch_size=1, policy="skip", existing=["original"])
                with patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=_FakeBatchManager()):
                    generate_job(job_id, self.store)
                self.store.edit_review_item(job_id, "item_0", text)
                self.store.queue_commit(job_id, CaptionCommitRequest(backupExisting=False))
                commit_job(job_id, self.store)
                self.assertEqual((self.dataset / "image_0.txt").read_text(encoding="utf-8"), text)
                self.assertEqual(self.store.get_job(job_id).written, 1)
                self.assertEqual(self.store.get_item(job_id, "item_0").finalText, text)

    def test_cancel_during_commit_keeps_written_and_remaining_review_results(self) -> None:
        job_id = "caption_commit_canceled"
        self.create_job([11, 22, 33], job_id=job_id, batch_size=3)
        with patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=_FakeBatchManager()):
            generate_job(job_id, self.store)
        self.store.queue_commit(job_id, CaptionCommitRequest())
        update_item = self.store.update_item

        def cancel_after_write(*args, **fields):
            result = update_item(*args, **fields)
            if fields.get("written"):
                self.store.update_job(job_id, state="canceling")
            return result

        with patch.object(self.store, "update_item", side_effect=cancel_after_write):
            commit_job(job_id, self.store)
        summary = self.store.get_job(job_id)
        items = self.store.list_items(job_id).items
        self.assertEqual((summary.state, summary.written, summary.processed), ("canceled", 1, 3))
        self.assertEqual(summary.detailsState, "available")
        self.assertEqual([item.written for item in items], [True, False, False])
        self.assertEqual([item.finalText for item in items], ["caption 11", "caption 22", "caption 33"])
        self.assertEqual((self.dataset / "image_0.txt").read_text(encoding="utf-8"), "caption 11")
        self.assertFalse((self.dataset / "image_1.txt").exists())


if __name__ == "__main__":
    unittest.main()
