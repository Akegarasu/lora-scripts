import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image

from mikazuki.app import caption_api
from mikazuki.captioning.datasets import CaptionDatasetRegistry
from mikazuki.captioning.models import (
    CaptionDatasetInspectRequest,
    CaptionJobCreateRequest,
    CaptionJobSummary,
)
from mikazuki.captioning.store import CaptionStore


class CaptionApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "workspace"
        self.dataset = self.workspace / "train"
        self.dataset.mkdir(parents=True)
        self.image = self.dataset / "sample.png"
        Image.new("RGB", (24, 16), (40, 90, 140)).save(self.image)
        self.registry = CaptionDatasetRegistry(
            roots={
                "train": self.dataset,
                "datasets": self.dataset,
                "workspace": self.workspace,
            }
        )
        self.store = CaptionStore(self.root / "caption.sqlite3", reconcile=False)
        self._create_job(
            "caption_api",
            source_root=self.dataset,
            image_path=self.image,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_job(self, job_id: str, *, source_root: Path, image_path: Path) -> None:
        request = CaptionJobCreateRequest(
            datasetId=f"ds_{job_id}",
            modelId="fake-model",
            outputMode="caption",
        )
        summary = CaptionJobSummary(
            id=job_id,
            modelId=request.modelId,
            modelTitle="Fake model",
            outputMode=request.outputMode,
            state="awaiting_review",
            message="review",
            revision=1,
            datasetId=request.datasetId,
            logPath=str(self.root / "caption-api.log"),
            total=1,
            createdAt="2026-08-01T12:00:00+08:00",
        )
        self.store.create_job(
            summary,
            request,
            [
                {
                    "id": "item_api",
                    "name": image_path.name,
                    "relative_path": image_path.name,
                    "image_path": image_path,
                    "caption_path": source_root / "sample.txt",
                    "existing_text": "",
                    "existing_fingerprint": None,
                    "source_root": source_root,
                    "state": "succeeded",
                }
            ],
        )

    async def test_basic_model_job_item_and_log_endpoints_without_loading_model(self) -> None:
        model_response = {"models": [], "defaultModelId": "fake-model"}
        fake_catalog = type("Catalog", (), {"response": lambda self: model_response})()
        with (
            patch("mikazuki.app.caption_api.get_caption_model_catalog", return_value=fake_catalog),
            patch("mikazuki.app.caption_api.get_caption_store", return_value=self.store),
            patch("mikazuki.app.caption_api.tail_log", return_value=(7, ["worker ready"])),
        ):
            models = await caption_api.list_caption_models()
            jobs = await caption_api.list_caption_jobs(limit=10)
            job = await caption_api.get_caption_job("caption_api")
            items = await caption_api.list_caption_job_items(
                "caption_api",
                offset=0,
                limit=10,
                state=None,
                query="",
            )
            logs = await caption_api.get_caption_job_logs("caption_api", tail=100)

        self.assertEqual(models, model_response)
        self.assertEqual(jobs.jobs[0].id, "caption_api")
        self.assertEqual(job.logPath, str(self.root / "caption-api.log"))
        self.assertEqual(items.items[0].id, "item_api")
        self.assertEqual(logs, {"jobId": "caption_api", "cursor": 7, "lines": ["worker ready"]})

    async def test_dataset_inspect_accepts_parent_path_outside_browse_root(self) -> None:
        outside = self.workspace / "escape"
        outside.mkdir()
        Image.new("RGB", (12, 10), (10, 20, 30)).save(outside / "outside.png")

        with patch(
            "mikazuki.app.caption_api.get_caption_dataset_registry",
            return_value=self.registry,
        ):
            inspected = await caption_api.inspect_caption_dataset(
                CaptionDatasetInspectRequest(root="train", path="../escape")
            )

        self.assertEqual(inspected.dataset.total, 1)
        self.assertEqual(inspected.dataset.path, outside.resolve().as_posix())

    async def test_dataset_inspect_list_and_thumbnail_endpoints(self) -> None:
        with patch(
            "mikazuki.app.caption_api.get_caption_dataset_registry",
            return_value=self.registry,
        ):
            inspected = await caption_api.inspect_caption_dataset(
                CaptionDatasetInspectRequest(root="train")
            )
            listed = await caption_api.list_caption_dataset_items(
                inspected.dataset.id,
                offset=0,
                limit=10,
                query="",
                caption_state="all",
            )
            thumbnail = await caption_api.get_caption_dataset_thumbnail(
                inspected.dataset.id,
                inspected.items[0].id,
                size=128,
            )

        self.assertEqual(listed.total, 1)
        self.assertEqual(thumbnail.media_type, "image/jpeg")
        self.assertTrue(thumbnail.body.startswith(b"\xff\xd8"))

    async def test_unknown_opaque_dataset_item_and_job_ids_return_not_found(self) -> None:
        inspected = self.registry.inspect(CaptionDatasetInspectRequest(root="train"))
        with patch(
            "mikazuki.app.caption_api.get_caption_dataset_registry",
            return_value=self.registry,
        ):
            with self.assertRaises(HTTPException) as missing_dataset:
                await caption_api.list_caption_dataset_items(
                    "../not-a-dataset",
                    offset=0,
                    limit=10,
                    query="",
                    caption_state="all",
                )
            with self.assertRaises(HTTPException) as missing_item:
                await caption_api.get_caption_dataset_thumbnail(
                    inspected.dataset.id,
                    "../not-an-item",
                    size=128,
                )

        with patch("mikazuki.app.caption_api.get_caption_store", return_value=self.store):
            with self.assertRaises(HTTPException) as missing_job:
                await caption_api.get_caption_job("../not-a-job")

        self.assertEqual(missing_dataset.exception.status_code, 410)
        self.assertEqual(missing_item.exception.status_code, 404)
        self.assertEqual(missing_job.exception.status_code, 404)

    async def test_job_thumbnail_rejects_stored_path_outside_source_root(self) -> None:
        outside = self.root / "outside.png"
        Image.new("RGB", (8, 8), (1, 2, 3)).save(outside)
        self._create_job("caption_escape", source_root=self.dataset, image_path=outside)

        with patch("mikazuki.app.caption_api.get_caption_store", return_value=self.store):
            with self.assertRaises(HTTPException) as raised:
                await caption_api.get_caption_job_item_thumbnail(
                    "caption_escape",
                    "item_api",
                    size=128,
                )
        self.assertEqual(raised.exception.status_code, 400)

    async def test_job_thumbnail_rejects_oversized_images_with_bad_request(self) -> None:
        with (
            patch("mikazuki.app.caption_api.get_caption_store", return_value=self.store),
            patch("PIL.Image.MAX_IMAGE_PIXELS", 1),
        ):
            with self.assertRaises(HTTPException) as raised:
                await caption_api.get_caption_job_item_thumbnail("caption_api", "item_api", size=128)
        self.assertEqual(raised.exception.status_code, 400)

    async def test_terminal_job_events_emit_progress_state_and_disable_buffering(self) -> None:
        with patch("mikazuki.app.caption_api.get_caption_store", return_value=self.store):
            response = await caption_api.get_caption_job_events(
                "caption_api", after=0, last_event_id="invalid"
            )
            chunks = [chunk async for chunk in response.body_iterator]
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("id: 1\nevent: progress\ndata: "))
        self.assertTrue(chunks[1].startswith("event: state\ndata: "))
        self.assertIn('"state": "awaiting_review"', chunks[0])
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")


if __name__ == "__main__":
    unittest.main()
