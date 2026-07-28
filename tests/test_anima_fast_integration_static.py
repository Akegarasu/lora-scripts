from __future__ import annotations

import ast
import unittest
from pathlib import Path


class AnimaFastStaticIntegrationTests(unittest.TestCase):
    def test_schema_file_exists_and_uses_fast_train_type(self):
        schema = Path("mikazuki/schema/anima-lora-fast.ts").read_text(encoding="utf-8")
        shared = Path("mikazuki/schema/shared.ts").read_text(encoding="utf-8")

        self.assertIn('default("anima-lora-fast")', schema)
        self.assertIn("ANIMA_FAST_LR_OPTIMIZER", schema)
        fast_optimizer = shared[shared.index("ANIMA_FAST_LR_OPTIMIZER"):]
        self.assertIn('"Automagic"', shared[: shared.index("ANIMA_FAST_LR_OPTIMIZER")])
        self.assertNotIn('"Automagic"', fast_optimizer)
        self.assertNotIn("prodigyplus.ProdigyPlusScheduleFree", fast_optimizer)
        self.assertNotIn('"EmoSens"', fast_optimizer)
        self.assertIn('"EmoSens"', shared[: shared.index("ANIMA_FAST_LR_OPTIMIZER")])
        self.assertIn('Schema.const("lora")', schema)

    def test_fast_schema_exposes_bucket_resolution_controls(self):
        schema = Path("mikazuki/schema/anima-lora-fast.ts").read_text(encoding="utf-8")

        self.assertIn("min_bucket_reso:", schema)
        self.assertIn("max_bucket_reso:", schema)
        self.assertIn("bucket_reso_steps:", schema)
        self.assertIn("bucket_no_upscale:", schema)
        self.assertIn("留空时按训练分辨率自动设置", schema)

    def test_fast_adapter_does_not_whitelist_emosens(self):
        adapter = Path("mikazuki/anima_fast_backend/adapter.py").read_text(encoding="utf-8")
        self.assertIn("FAST_SUPPORTED_OPTIMIZERS", adapter)
        self.assertNotIn('"EmoSens"', adapter)
        self.assertNotIn('"Automagic",', adapter[adapter.index("FAST_SUPPORTED_OPTIMIZERS"): adapter.index("@dataclass")])

    def test_fast_train_type_is_not_legacy_trainer_mapping(self):
        source = Path("mikazuki/app/api.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        mapping = None
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "trainer_mapping":
                        mapping = ast.literal_eval(node.value)
        self.assertIsNotNone(mapping)
        self.assertNotIn("anima-lora-fast", mapping)
        self.assertEqual(mapping["anima-lora"], "./scripts/dev/anima_train_network.py")
        self.assertEqual(mapping["sd3-lora"], "./scripts/dev/anima_train_network.py")

    def test_api_contains_fast_early_branch_and_plugin_routes(self):
        source = Path("mikazuki/app/api.py").read_text(encoding="utf-8")

        self.assertIn("model_train_type == ANIMA_FAST_TRAIN_TYPE", source)
        self.assertIn('"/plugins/anima-lora/status"', source)
        self.assertIn('"/plugins/anima-lora/preflight"', source)
        self.assertIn('"/plugins/anima-lora/dry-run"', source)
        self.assertIn('"/plugins/anima-lora/install/log/stream/{task_id}"', source)
        self.assertLess(source.index("model_train_type == ANIMA_FAST_TRAIN_TYPE"), source.index("trainer_file = trainer_mapping[model_train_type]"))

    def test_frontend_dist_registers_anima_fast_entry(self):
        router = Path("frontend/src/router.ts").read_text(encoding="utf-8")
        page = Path("frontend/src/pages/AnimaFastPage.vue").read_text(encoding="utf-8")
        training = Path("frontend/src/pages/TrainingPage.vue").read_text(encoding="utf-8")
        self.assertIn('"/lora/anima-fast.html"', router)
        self.assertIn('schema-name="anima-lora-fast"', page)
        self.assertIn("animaFastPreflight", training)
        self.assertIn("TrainingPage", page)

    def test_benchmark_example_configs_exist(self):
        examples = Path("docs/examples")
        for name in (
            "anima-lora-benchmark-kohya.toml",
            "anima-lora-benchmark-fast.toml",
            "anima-lora-benchmark-dataset.toml",
        ):
            self.assertTrue((examples / name).is_file(), name)

    def test_anima_fast_docs_mention_license_and_benchmark(self):
        text = Path("docs/anima-fast.md").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("7.1 s/step", text)
        self.assertIn("2.8 s/step", text)
        merge = Path("docs/anima-fast-merge-checklist.md").read_text(encoding="utf-8")
        self.assertIn("sorryhyun/anima_lora", merge)


if __name__ == "__main__":
    unittest.main()
