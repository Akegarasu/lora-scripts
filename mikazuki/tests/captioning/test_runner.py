import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from mikazuki.captioning.datasets import CaptionDatasetRegistry
from mikazuki.captioning.models import (
    CaptionCommitRequest,
    CaptionDatasetInspectRequest,
    CaptionJobCreateRequest,
    CaptionPrediction,
)
from mikazuki.captioning.runner import CaptionRunner
from mikazuki.captioning.store import CaptionStore
from mikazuki.captioning.worker import commit_job, generate_job


class _Catalog:
    def __init__(self) -> None:
        self.validated = None

    def get(self, model_id):
        if model_id != "fake-caption-model":
            return None
        return SimpleNamespace(
            id=model_id,
            title="Fake Caption Model",
            status="ready",
            statusReason=None,
            outputModes=["caption"],
            capabilities=SimpleNamespace(
                devices=["cpu", "cuda"],
                batch=True,
                prompt=True,
                languages=["en"],
            ),
        )

    def validate_params(self, model_id, values):
        self.validated = (model_id, values)
        return {"maxNewTokens": 48}


class _Datasets:
    def __init__(self, source_root: Path) -> None:
        self.source_root = source_root
        image = source_root / "sample.png"
        self.record = SimpleNamespace(
            id="item_runner",
            name="sample.png",
            relative_path="sample.png",
            image_path=image,
            caption_path=image.with_suffix(".txt"),
            existing_text="",
            fingerprint=None,
            writable=True,
            error=None,
        )

    def get_snapshot(self, _dataset_id):
        return SimpleNamespace(source_root=self.source_root)

    def select_records(self, _dataset_id, _item_ids):
        return [self.record]


class _NoProcessRunner(CaptionRunner):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.scheduled = []

    def _schedule(self, job_id: str, *, action: str, use_gpu: bool) -> None:
        self.scheduled.append((job_id, action, use_gpu))


class CaptionRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_utf8_requires_overwrite_or_manual_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dataset = root / "dataset"
            dataset.mkdir()
            image = dataset / "sample.png"
            Image.new("RGB", (8, 8)).save(image)
            caption = image.with_suffix(".txt")
            original = b"\xff\xfecannot decode"
            registry = CaptionDatasetRegistry(
                roots={"train": dataset, "datasets": dataset, "workspace": root},
            )
            store = CaptionStore(root / "caption.sqlite3", reconcile=False)
            runner = _NoProcessRunner(store=store, datasets=registry, catalog=_Catalog())
            cases = [
                (stage, policy, None)
                for stage in (False, True)
                for policy in ("append", "prepend", "fill_empty")
            ] + [(False, "overwrite", None), (True, "append", "manual repair")]
            for stage, policy, edited in cases:
                with self.subTest(stage=stage, policy=policy, edited=edited):
                    caption.write_bytes(original)
                    inspected = registry.inspect(CaptionDatasetInspectRequest(root="train"))
                    created = await runner.start_job(CaptionJobCreateRequest(
                        datasetId=inspected.dataset.id,
                        modelId="fake-caption-model",
                        outputMode="caption",
                        runtime={"device": "cpu"},
                        output={
                            "stageBeforeWrite": stage,
                            "conflictPolicy": "overwrite" if stage else policy,
                        },
                    ))
                    manager = Mock()
                    manager.predict_batch.return_value = [CaptionPrediction(text="generated")]
                    with (
                        patch("mikazuki.captioning.worker.get_caption_model_manager", return_value=manager),
                        patch("mikazuki.captioning.writer.app_root", return_value=root),
                    ):
                        generate_job(created.id, store)
                        if stage:
                            if edited:
                                store.edit_review_item(created.id, inspected.items[0].id, edited)
                            store.queue_commit(created.id, CaptionCommitRequest(conflictPolicy=policy))
                            commit_job(created.id, store)
                    if edited or policy == "overwrite":
                        self.assertEqual(caption.read_text(encoding="utf-8"), edited or "generated")
                        backup = root / "config" / "caption-backups" / created.id / "sample.txt"
                        self.assertEqual(backup.read_bytes(), original)
                        self.assertEqual(store.get_job(created.id).written, 1)
                    else:
                        self.assertEqual(caption.read_bytes(), original)
                        self.assertEqual(store.get_job(created.id).conflicts, 1)
                        self.assertEqual(store.get_job(created.id).written, 0)

    async def test_long_caption_is_preserved_when_appending_or_prepending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dataset = root / "dataset"
            dataset.mkdir()
            image = dataset / "sample.png"
            Image.new("RGB", (8, 8)).save(image)
            caption = image.with_suffix(".txt")
            original = "界" * 100_000 + "KEEP THIS TAIL"
            registry = CaptionDatasetRegistry(
                roots={"train": dataset, "datasets": dataset, "workspace": root},
            )
            store = CaptionStore(root / "caption.sqlite3", reconcile=False)
            runner = _NoProcessRunner(store=store, datasets=registry, catalog=_Catalog())
            for stage in (False, True):
                for policy in ("append", "prepend"):
                    with self.subTest(stage=stage, policy=policy):
                        caption.write_text(original, encoding="utf-8")
                        inspected = registry.inspect(CaptionDatasetInspectRequest(root="train"))
                        request = CaptionJobCreateRequest(
                            datasetId=inspected.dataset.id,
                            modelId="fake-caption-model",
                            outputMode="caption",
                            runtime={"device": "cpu"},
                            output={
                                "stageBeforeWrite": stage,
                                "conflictPolicy": policy,
                                "backupExisting": False,
                            },
                        )
                        created = await runner.start_job(request)
                        manager = Mock()
                        manager.predict_batch.return_value = [CaptionPrediction(text="generated")]
                        with patch(
                            "mikazuki.captioning.worker.get_caption_model_manager",
                            return_value=manager,
                        ):
                            generate_job(created.id, store)
                        if stage:
                            store.queue_commit(created.id, CaptionCommitRequest())
                            commit_job(created.id, store)
                        expected = (
                            f"{original}, generated" if policy == "append"
                            else f"generated, {original}"
                        )
                        self.assertEqual(caption.read_text(encoding="utf-8"), expected)
                        self.assertEqual(store.get_job(created.id).state, "succeeded")

    async def test_start_job_persists_log_path_and_normalized_request_without_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dataset = root / "dataset"
            dataset.mkdir()
            catalog = _Catalog()
            store = CaptionStore(root / "caption.sqlite3", reconcile=False)
            runner = _NoProcessRunner(
                store=store,
                datasets=_Datasets(dataset),
                catalog=catalog,
            )
            request = CaptionJobCreateRequest(
                datasetId="ds_runner",
                modelId="fake-caption-model",
                outputMode="caption",
                params={},
                runtime={"device": "cpu"},
            )

            created = await runner.start_job(request)

            stored = store.get_job(created.id)
            stored_request = store.get_request(created.id)
            self.assertIsNotNone(created.logPath)
            self.assertTrue(created.logPath.endswith(".log"))
            self.assertEqual(stored.logPath, created.logPath)
            self.assertEqual(stored_request.params, {"maxNewTokens": 48})
            self.assertFalse(created.reviewMode)
            self.assertFalse(stored.reviewMode)
            self.assertFalse(stored_request.output.stageBeforeWrite)
            self.assertEqual(runner.scheduled, [(created.id, "generate", False)])
            self.assertEqual(catalog.validated, ("fake-caption-model", {}))

            store.update_job(created.id, state="generating")
            canceled = runner.cancel_job(created.id)
            self.assertEqual(canceled.state, "canceled")
            self.assertEqual(store.get_item(created.id, "item_runner").state, "canceled")


class CaptionRunnerProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        self.store = Mock()
        self.store.get_job.return_value = SimpleNamespace(
            state="queued", logPath=str(self.root / "worker.log")
        )
        self.runner = CaptionRunner(store=self.store, datasets=_Datasets(self.root), catalog=_Catalog())
        self.runner._gpu_lease = Mock()
        self.runner._gpu_lease.acquire.return_value = True
        self.process = Mock()
        self.process.poll.return_value = None
        self.process.wait.side_effect = [RuntimeError("wait failed"), 1]

    def test_wait_failure_terminates_worker_before_releasing_gpu(self) -> None:
        lifecycle = Mock()
        lifecycle.attach_mock(self.runner._gpu_lease.release, "release")
        with (
            patch("mikazuki.captioning.runner.subprocess.Popen", return_value=self.process),
            patch("mikazuki.captioning.runner.kill_proc_tree") as terminate,
        ):
            lifecycle.attach_mock(terminate, "terminate")
            with self.assertRaisesRegex(RuntimeError, "wait failed"):
                self.runner._run_process("caption_process", "generate", True)
        self.assertEqual([call[0] for call in lifecycle.mock_calls], ["terminate", "release"])
        terminate.assert_called_once_with(self.process.pid, including_parent=True)
        self.assertNotIn("caption_process", self.runner._processes)

    def test_failed_cleanup_reports_error_and_preserves_lease_lifecycle(self) -> None:
        with (
            patch("mikazuki.captioning.runner.subprocess.Popen", return_value=self.process),
            patch("mikazuki.captioning.runner.kill_proc_tree", side_effect=RuntimeError("cleanup failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                self.runner._run_process("caption_process", "generate", True)
        self.runner._gpu_lease.release.assert_called_once()
        self.assertNotIn("caption_process", self.runner._processes)

    def test_waiting_for_gpu_does_not_reset_canceled_job_state(self) -> None:
        self.store.get_job.return_value.state = "canceled"
        self.runner._gpu_lease.acquire.side_effect = [False, True]
        with patch("mikazuki.captioning.runner.subprocess.Popen") as popen:
            self.runner._run_process("caption_process", "generate", True)
        popen.assert_not_called()
        self.assertTrue(all(
            call.kwargs.get("state") != "queued"
            for call in self.store.update_job.call_args_list
        ))
        self.runner._gpu_lease.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
