import base64
import json
import unittest

import httpx

from mikazuki.mcp.client import BackendClient
from mikazuki.mcp.server import build_server
from mikazuki.tests.mcp.test_client import PNG


def content_blocks(result):
    # FastMCP v1 returns (content, structured_content) for structured tools.
    return result[0] if isinstance(result, tuple) else result


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.response = {"status": "ok"}
        self.http_status = 200

        def handle(request):
            self.requests.append(request)
            if request.url.path.endswith("/thumbnail") or request.url.path.endswith("/files/content"):
                return httpx.Response(200, content=PNG, headers={"Content-Type": "image/png"})
            return httpx.Response(self.http_status, json=self.response)

        self.http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.backend = BackendClient("http://127.0.0.1:28000", client=self.http)
        self.server = build_server(client=self.backend)
        self.addAsyncCleanup(self.http.aclose)
        self.addAsyncCleanup(self.backend.close)

    async def test_tool_discovery_exposes_training_data_and_monitoring(self):
        tools = {tool.name: tool for tool in await self.server.list_tools()}
        self.assertTrue({
            "compile_training", "start_training", "terminate_training", "get_training_job",
            "get_training_logs", "get_training_metrics", "get_training_artifacts",
            "inspect_dataset", "list_dataset_items", "read_dataset_image", "read_output_image",
            "read_caption_job_image", "get_tag_item",
        }.issubset(tools))
        self.assertFalse(tools["start_training"].annotations.readOnlyHint)
        self.assertTrue(tools["get_training_metrics"].annotations.readOnlyHint)
        self.assertTrue(tools["compile_training"].annotations.readOnlyHint)
        self.assertTrue(tools["start_caption_job"].annotations.destructiveHint)
        self.assertIn("draft", tools["start_training"].inputSchema["properties"])

    async def test_compile_does_not_persist_and_keeps_path_validation(self):
        draft = {"trainerId": "sd.lora", "name": "experiment-01", "params": {"learning_rate": 0.0001}}
        self.response = {"errors": [], "warnings": [], "trainConfig": "learning_rate = 0.0001"}
        await self.server.call_tool("compile_training", {"draft": draft})
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/api/v2/compile")
        self.assertEqual(request.url.params["persist"], "false")
        self.assertEqual(request.url.params["validate_paths"], "true")
        self.assertEqual(json.loads(request.content), draft)

    async def test_submission_uses_existing_backend_queue(self):
        self.response = {"job": {"id": "job_one", "state": "queued"}, "compile": {"errors": []}}
        await self.server.call_tool("start_training", {"draft": {"trainerId": "sd.lora"}})
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].method, "POST")
        self.assertEqual(self.requests[0].url.path, "/api/v2/jobs")
        self.assertEqual(self.requests[0].url.params["validate_paths"], "true")

    async def test_dataset_and_output_images_are_image_blocks(self):
        for name, arguments, path in (
            ("read_dataset_image", {"dataset_id": "ds_1", "item_id": "item_1"}, "/api/v2/caption/datasets/ds_1/items/item_1/thumbnail"),
            ("read_caption_job_image", {"job_id": "caption_1", "item_id": "item_1"}, "/api/v2/caption/jobs/caption_1/items/item_1/thumbnail"),
            ("read_output_image", {"path": "sample/preview.png"}, "/api/v2/files/content"),
        ):
            with self.subTest(tool=name):
                result = content_blocks(await self.server.call_tool(name, arguments))
                image = next(block for block in result if block.type == "image")
                self.assertEqual(base64.b64decode(image.data), PNG)
                self.assertEqual(self.requests[-1].url.path, path)

    async def test_dataset_inspection_forwards_paging_without_writing_captions(self):
        self.response = {"dataset": {"id": "ds_1", "total": 2}, "items": []}
        await self.server.call_tool("inspect_dataset", {"path": "角色", "initial_limit": 2})
        request = self.requests[0]
        self.assertEqual(request.url.path, "/api/v2/caption/datasets/inspect")
        body = json.loads(request.content)
        self.assertEqual(body["path"], "角色")
        self.assertEqual(body["initialLimit"], 2)
        self.assertEqual(body["root"], "train")

    async def test_caption_writes_keep_backups_by_default(self):
        await self.server.call_tool("save_dataset_caption", {"dataset_id": "ds_1", "item_id": "item_1", "text": "new caption"})
        request = self.requests[0]
        self.assertEqual(request.method, "PUT")
        self.assertEqual(json.loads(request.content), {"text": "new caption", "backupExisting": True})

    async def test_file_listing_is_bounded_and_paginated(self):
        self.response = {"items": [{"name": f"image-{i}.png"} for i in range(5)]}
        blocks = content_blocks(await self.server.call_tool("browse_files", {"offset": 2, "limit": 2}))
        payload = json.loads(next(block.text for block in blocks if block.type == "text"))
        self.assertEqual([item["name"] for item in payload["items"]], ["image-2.png", "image-3.png"])
        self.assertEqual(payload["total"], 5)

    async def test_training_schema_uses_backend_enriched_dataset_definition(self):
        self.response = {
            "title": "TrainDraft", "type": "object",
            "properties": {"dataset": {"anyOf": [{"$ref": "#/$defs/SimpleDatasetDraft"}, {"type": "null"}]}},
            "$defs": {"SimpleDatasetDraft": {"type": "object", "properties": {"mode": {"enum": ["simple"]}}}},
        }
        blocks = content_blocks(await self.server.call_tool("get_request_schema", {}))
        payload = json.loads(next(block.text for block in blocks if block.type == "text"))
        self.assertEqual(payload["schema"], self.response)
        self.assertEqual(self.requests[0].url.path, "/api/v2/training/schema")

    async def test_live_caption_request_schema_includes_transitive_definitions(self):
        self.response = {"components": {"schemas": {
            "CaptionJobCreateRequest": {"type": "object", "properties": {"output": {"$ref": "#/components/schemas/CaptionOutputOptions"}}},
            "CaptionOutputOptions": {"type": "object", "properties": {"stageBeforeWrite": {"type": "boolean"}}},
            "Unrelated": {"type": "string"},
        }}}
        blocks = content_blocks(await self.server.call_tool("get_request_schema", {"kind": "caption_job"}))
        payload = json.loads(next(block.text for block in blocks if block.type == "text"))
        self.assertEqual(payload["schema"], {"$ref": "#/components/schemas/CaptionJobCreateRequest"})
        self.assertEqual(set(payload["components"]["schemas"]), {"CaptionJobCreateRequest", "CaptionOutputOptions"})
        self.assertEqual(self.requests[0].url.path, "/openapi.json")

    async def test_zero_log_tail_cannot_request_an_unbounded_log(self):
        for name in ("get_training_logs", "get_caption_logs"):
            with self.subTest(tool=name):
                with self.assertRaises(Exception):
                    await self.server.call_tool(name, {"job_id": "job_1", "tail": 0})
        self.assertEqual(self.requests, [])
        await self.server.call_tool("get_training_logs", {"job_id": "job_1", "tail": 1})
        self.assertEqual(self.requests[0].url.params["tail"], "1")

    async def test_single_tag_item_returns_full_detail_without_client_truncation(self):
        self.response = {"id": "item_1", "captionText": "caption detail " * 400, "sourceTruncated": False}
        blocks = content_blocks(await self.server.call_tool("get_tag_item", {"dataset_id": "tags_1", "item_id": "item_1"}))
        payload = json.loads(next(block.text for block in blocks if block.type == "text"))
        self.assertEqual(payload, self.response)
        self.assertEqual(self.requests[0].url.path, "/api/v2/tag-editor/datasets/tags_1/items/item_1")

    async def test_path_like_identifiers_are_rejected_before_http(self):
        for identifier in ("../jobs", "job/terminate", "job?tail=1", "%2e%2e", ".."):
            with self.subTest(identifier=identifier):
                with self.assertRaises(Exception):
                    await self.server.call_tool("get_training_job", {"job_id": identifier})
        self.assertEqual(self.requests, [])

    async def test_caption_generation_stages_output_by_default(self):
        request = {"datasetId": "ds_1", "modelId": "caption-model", "outputMode": "caption"}
        await self.server.call_tool("start_caption_job", {"request": request})
        sent = self.requests[0]
        self.assertEqual(sent.url.path, "/api/v2/caption/jobs")
        self.assertEqual(json.loads(sent.content)["output"], {
            "stageBeforeWrite": True, "conflictPolicy": "skip", "backupExisting": True,
        })
        self.assertNotIn("output", request)

    async def test_explicit_caption_output_policy_is_preserved(self):
        request = {
            "datasetId": "ds_1", "modelId": "caption-model", "outputMode": "caption",
            "output": {"stageBeforeWrite": False, "conflictPolicy": "append"},
        }
        await self.server.call_tool("start_caption_job", {"request": request})
        self.assertEqual(json.loads(self.requests[0].content)["output"], {
            "stageBeforeWrite": False, "conflictPolicy": "append", "backupExisting": True,
        })

    async def test_tag_apply_requires_the_preview_identity_and_revision(self):
        await self.server.call_tool("apply_tag_changes", {
            "dataset_id": "tags_1", "change_set_id": "change_1", "revision": "revision_1",
        })
        sent = self.requests[0]
        self.assertEqual(sent.url.path, "/api/v2/tag-editor/datasets/tags_1/changes/apply")
        self.assertEqual(json.loads(sent.content), {
            "changeSetId": "change_1", "revision": "revision_1", "backupExisting": True,
        })

    async def test_queue_separates_review_from_active_gpu_work_and_flags_limit(self):
        async def handle(request):
            if request.url.path == "/api/v2/jobs":
                return httpx.Response(200, json={"jobs": [{"id": "train_done", "state": "succeeded"}, {"id": "train_wait", "state": "queued"}]})
            return httpx.Response(200, json={"jobs": [{"id": "cap_review", "state": "awaiting_review"}, {"id": "cap_run", "state": "generating"}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            server = build_server(client=BackendClient(client=http))
            blocks = content_blocks(await server.call_tool("get_queue", {"limit": 2}))
        payload = json.loads(next(block.text for block in blocks if block.type == "text"))
        self.assertEqual([job["id"] for job in payload["training"]], ["train_wait"])
        self.assertEqual([job["id"] for job in payload["caption"]], ["cap_run"])
        self.assertEqual([job["id"] for job in payload["awaitingReview"]], ["cap_review"])
        self.assertTrue(payload["historyMayBeTruncated"])


if __name__ == "__main__":
    unittest.main()
