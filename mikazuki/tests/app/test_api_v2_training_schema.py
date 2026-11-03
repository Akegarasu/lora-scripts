import unittest

import httpx
from fastapi import FastAPI

from mikazuki.app import api_v2
from mikazuki.compiler.models import TrainDraft


class TrainingSchemaApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_schema_exposes_complete_structured_training_inputs(self) -> None:
        app = FastAPI()
        app.include_router(api_v2.router, prefix="/api/v2")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v2/training/schema")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["trainerId"])
        self.assertEqual(schema["properties"]["dataset"], {
            "anyOf": [{"$ref": "#/$defs/SimpleDatasetDraft"}, {"type": "null"}],
            "default": None,
            "title": "Dataset",
        })
        dataset = schema["$defs"]["SimpleDatasetDraft"]["properties"]
        self.assertEqual(dataset["mode"]["enum"], ["simple"])
        self.assertEqual(dataset["captionExtension"]["default"], ".txt")
        self.assertEqual(dataset["numRepeats"]["default"], 1)
        self.assertIn("directly containing", dataset["root"]["description"])
        self.assertIn("does not recursively", dataset["root"]["description"])
        self.assertIn("batchSize", dataset)
        self.assertIn("resolution", dataset)

        def check_references(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertTrue(value["$ref"].startswith("#/$defs/"))
                    self.assertIn(value["$ref"].removeprefix("#/$defs/"), schema["$defs"])
                for child in value.values():
                    check_references(child)
            elif isinstance(value, list):
                for child in value:
                    check_references(child)

        check_references(schema)

    async def test_schema_is_fresh_and_does_not_change_runtime_draft_validation(self) -> None:
        first = await api_v2.get_training_schema()
        first["$defs"]["SimpleDatasetDraft"]["properties"]["mode"]["enum"].append("custom")
        second = await api_v2.get_training_schema()
        self.assertEqual(second["$defs"]["SimpleDatasetDraft"]["properties"]["mode"]["enum"], ["simple"])
        self.assertEqual(
            TrainDraft(trainerId="sd.lora", dataset={"mode": "custom"}).dataset,
            {"mode": "custom"},
        )


if __name__ == "__main__":
    unittest.main()
