import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.app.tag_editor_api import router
from mikazuki.captioning.datasets import CaptionDatasetRegistry
from mikazuki.tag_editor.service import TagEditorService


class TagEditorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "workspace"
        self.train = self.workspace / "train"
        self.train.mkdir(parents=True)
        registry = CaptionDatasetRegistry(
            roots={
                "train": self.train,
                "datasets": self.train,
                "workspace": self.workspace,
            },
            backup_root=self.root / "manual-backups",
        )
        self.service = TagEditorService(
            registry=registry,
            history_root=self.root / "history",
        )
        app = FastAPI()
        app.include_router(router, prefix="/api/v2/tag-editor")
        self.client = TestClient(app)
        self.service_patch = patch(
            "mikazuki.app.tag_editor_api.get_tag_editor_service",
            return_value=self.service,
        )
        self.service_patch.start()

    def tearDown(self) -> None:
        self.service_patch.stop()
        self.client.close()
        self.temporary_directory.cleanup()

    def make_image(self, name: str, caption: str | None = None) -> Path:
        image = self.train / name
        image.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 24), (20, 80, 140)).save(image)
        if caption is not None:
            image.with_suffix(".txt").write_text(caption, encoding="utf-8")
        return image

    def inspect(self) -> dict:
        response = self.client.post(
            "/api/v2/tag-editor/datasets/inspect",
            json={"root": "train", "captionExtension": ".txt"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_http_workflow_exposes_detail_suggestions_results_and_rollback(self) -> None:
        image = self.make_image("sample.png", "cat, blue eyes")
        inspected = self.inspect()
        dataset = inspected["dataset"]
        item = inspected["items"][0]

        listed = self.client.get(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/items",
            params={"state": "with", "query": "BLUE", "limit": 10},
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["items"][0]["id"], item["id"])

        detail = self.client.get(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/items/{item['id']}"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["captionText"], "cat, blue eyes")

        suggestions = self.client.get(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/tag-suggestions",
            params={"query": "cat"},
        )
        self.assertEqual(suggestions.status_code, 200, suggestions.text)
        self.assertEqual(suggestions.json()["suggestions"], [{"text": "cat", "count": 1}])

        thumbnail = self.client.get(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/items/{item['id']}/thumbnail",
            params={"size": 64},
        )
        self.assertEqual(thumbnail.status_code, 200, thumbnail.text)
        self.assertEqual(thumbnail.headers["content-type"], "image/jpeg")
        self.assertEqual(thumbnail.headers["cache-control"], "private, max-age=300")

        preview = self.client.post(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/changes/preview",
            json={
                "revision": dataset["revision"],
                "scope": {"mode": "include", "includeIds": [item["id"]]},
                "operations": [{"type": "set", "text": "dog"}],
            },
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        change = preview.json()
        self.assertEqual(change["state"], "previewed")
        self.assertEqual(image.with_suffix(".txt").read_text(encoding="utf-8"), "cat, blue eyes")

        apply_response = self.client.post(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/changes/apply",
            json={
                "changeSetId": change["id"],
                "revision": change["revision"],
                "backupExisting": True,
            },
        )
        self.assertEqual(apply_response.status_code, 200, apply_response.text)
        self.assertEqual(apply_response.json()["state"], "queued")
        self.assertEqual(image.with_suffix(".txt").read_text(encoding="utf-8"), "dog")

        completed = self.client.get(f"/api/v2/tag-editor/changes/{change['id']}")
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["state"], "completed")
        results = self.client.get(
            f"/api/v2/tag-editor/changes/{change['id']}/results",
            params={"offset": 0, "limit": 1},
        )
        self.assertEqual(results.status_code, 200, results.text)
        self.assertEqual(results.json()["items"][0]["state"], "applied")

        history = self.client.get("/api/v2/tag-editor/changes", params={"limit": 10})
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["changes"][0]["id"], change["id"])

        rollback = self.client.post(f"/api/v2/tag-editor/changes/{change['id']}/rollback")
        self.assertEqual(rollback.status_code, 200, rollback.text)
        self.assertEqual(rollback.json()["state"], "rolling_back")
        self.assertEqual(
            image.with_suffix(".txt").read_text(encoding="utf-8"),
            "cat, blue eyes",
        )
        rolled_back = self.client.get(f"/api/v2/tag-editor/changes/{change['id']}")
        self.assertEqual(rolled_back.json()["state"], "rolled_back")

    def test_http_validation_and_missing_or_stale_ids_use_stable_status_codes(self) -> None:
        self.make_image("sample.png", "caption")
        invalid_inspect = self.client.post(
            "/api/v2/tag-editor/datasets/inspect",
            json={"root": "train", "unknownField": True},
        )
        self.assertEqual(invalid_inspect.status_code, 422)

        inspected = self.inspect()
        dataset = inspected["dataset"]
        item = inspected["items"][0]
        invalid_operation = self.client.post(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/changes/preview",
            json={
                "revision": dataset["revision"],
                "scope": {"mode": "include", "includeIds": [item["id"]]},
                "operations": [{"type": "set", "text": "x", "typo": True}],
            },
        )
        self.assertEqual(invalid_operation.status_code, 422)

        stale = self.client.post(
            f"/api/v2/tag-editor/datasets/{dataset['id']}/changes/preview",
            json={
                "revision": "rev_stale",
                "scope": {"mode": "include", "includeIds": [item["id"]]},
                "operations": [{"type": "set", "text": "x"}],
            },
        )
        self.assertEqual(stale.status_code, 409)

        missing_dataset = self.client.get(
            "/api/v2/tag-editor/datasets/ds_missing/items"
        )
        missing_change = self.client.get(
            "/api/v2/tag-editor/changes/chg_abcdefghijklmnop"
        )
        missing_results = self.client.get(
            "/api/v2/tag-editor/changes/chg_abcdefghijklmnop/results"
        )
        self.assertEqual(missing_dataset.status_code, 410)
        self.assertEqual(missing_change.status_code, 404)
        self.assertEqual(missing_results.status_code, 404)


if __name__ == "__main__":
    unittest.main()
