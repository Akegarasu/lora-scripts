import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mikazuki.captioning.models import CaptionJobCreateRequest
from mikazuki.captioning.runner import CaptionRunner
from mikazuki.captioning.store import CaptionStore


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


if __name__ == "__main__":
    unittest.main()
