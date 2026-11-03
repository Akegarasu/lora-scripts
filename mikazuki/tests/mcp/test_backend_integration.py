import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image

from mikazuki.app import api_v2, caption_api
from mikazuki.app.application import app
from mikazuki.captioning.datasets import CaptionDatasetRegistry
from mikazuki.compiler.compiler import compile_draft
from mikazuki.mcp.client import BackendClient
from mikazuki.mcp.server import build_server
from mikazuki.tests.mcp.test_server import content_blocks


def json_result(result):
    return json.loads(next(block.text for block in content_blocks(result) if block.type == "text"))


class MCPBackendIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_inspect_read_and_compile_through_real_backend_without_starting_training(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "train" / "example"
            data.mkdir(parents=True)
            Image.new("RGB", (32, 24), color=(60, 120, 180)).save(data / "example.png")
            (data / "example.txt").write_text("test subject, blue background", encoding="utf-8")
            model = root / "model.safetensors"
            model.write_bytes(b"compile-only placeholder")
            registry = CaptionDatasetRegistry(roots={"train": root / "train", "datasets": root / "train", "workspace": root})

            def compile_fixture(draft, *, persist, validate_paths):
                return compile_draft(draft, persist=persist, validate_paths=validate_paths, base_dir=root)

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http:
                server = build_server(client=BackendClient("http://testserver", client=http))
                with (
                    patch.object(caption_api, "get_caption_dataset_registry", return_value=registry),
                    patch.object(api_v2, "compile_draft", side_effect=compile_fixture),
                ):
                    schema = json_result(await server.call_tool("get_request_schema", {"kind": "training"}))
                    self.assertEqual(schema["schema"]["title"], "TrainDraft")
                    self.assertIn("SimpleDatasetDraft", schema["schema"]["$defs"])
                    self.assertIn({"$ref": "#/$defs/SimpleDatasetDraft"}, schema["schema"]["properties"]["dataset"]["anyOf"])
                    inspected = json_result(await server.call_tool("inspect_dataset", {"path": "example"}))
                    self.assertEqual(inspected["dataset"]["total"], 1)
                    self.assertEqual(inspected["items"][0]["captionText"], "test subject, blue background")
                    self.assertEqual(inspected["items"][0]["width"], 32)
                    image = content_blocks(await server.call_tool("read_dataset_image", {
                        "dataset_id": inspected["dataset"]["id"], "item_id": inspected["items"][0]["id"],
                    }))
                    self.assertTrue(any(block.type == "image" and block.mimeType == "image/jpeg" for block in image))
                    result = json_result(await server.call_tool("compile_training", {"draft": {
                        "trainerId": "sd.lora", "name": "fixture-experiment",
                        "modelAssets": {"pretrained_model_name_or_path": str(model)},
                        "dataset": {"mode": "simple", "root": str(data)},
                        "params": {"learning_rate": 0.0001, "max_train_steps": 10},
                    }}))
                    self.assertEqual(result["errors"], [])
                    self.assertIn("learning_rate", result["trainConfig"])
                    self.assertIn("image_dir", result["datasetConfig"])
                    self.assertIn("accelerate.commands.launch", result["command"])
                    self.assertFalse((root / "config" / "runs").exists())


if __name__ == "__main__":
    unittest.main()
