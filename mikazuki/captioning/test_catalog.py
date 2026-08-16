import unittest

from mikazuki.captioning.adapters import CaptionProvider, WDTaggerProvider
from mikazuki.captioning.catalog import CaptionModelCatalog, builtin_model_descriptors


class CaptionModelCatalogTests(unittest.TestCase):
    def test_catalog_registers_all_legacy_taggers_and_captioners(self):
        catalog = CaptionModelCatalog(
            dependency_checker=lambda module: True,
            cache_checker=lambda descriptor: False,
            device_resolver=lambda descriptor: ["cpu"],
        )
        summaries = catalog.list_models()
        ids = {model.id for model in summaries}
        legacy_tagger_ids = {
            "wd-convnext-v3",
            "wd-swinv2-v3",
            "wd-vit-v3",
            "wd14-convnextv2-v2",
            "wd14-swinv2-v2",
            "wd14-vit-v2",
            "wd14-moat-v2",
            "wd-eva02-large-tagger-v3",
            "wd-vit-large-tagger-v3",
            "cl_tagger_1_01",
        }
        blip2_ids = {
            "blip2-opt-2.7b",
            "blip2-opt-2.7b-coco",
            "blip2-opt-6.7b",
            "blip2-opt-6.7b-coco",
            "blip2-flan-t5-xl",
            "blip2-flan-t5-xl-coco",
            "blip2-flan-t5-xxl",
        }

        self.assertEqual(len(summaries), 25)
        self.assertTrue(legacy_tagger_ids.issubset(ids))
        self.assertTrue(blip2_ids.issubset(ids))
        self.assertIn("blip-large", ids)
        self.assertIn("git-large-coco", ids)
        self.assertIn("smolvlm2-2.2b", ids)
        self.assertIn("qwen2.5-vl-7b", ids)
        self.assertIn("joycaption-beta-one", ids)
        self.assertIn("toriigate-v0.4-2b", ids)
        self.assertIn("llava-onevision-0.5b", ids)
        self.assertIn("qwen3-vl-4b", ids)
        self.assertEqual(catalog.response().defaultModelId, "wd-vit-v3")

    def test_dependency_availability_is_evaluated_when_listing(self):
        available_modules = {"numpy", "PIL", "huggingface_hub", "torch", "transformers"}
        catalog = CaptionModelCatalog(
            dependency_checker=lambda module: module in available_modules,
            cache_checker=lambda descriptor: False,
            device_resolver=lambda descriptor: ["cpu"],
        )

        wd = catalog.get("wd-vit-v3")
        blip = catalog.get("blip-large")
        self.assertEqual(wd.status, "unavailable")
        self.assertIn("onnxruntime/onnxruntime-gpu", wd.missingDependencies)
        self.assertEqual(wd.capabilities.devices, [])
        self.assertEqual(blip.status, "downloadable")
        self.assertEqual(blip.capabilities.devices, ["cpu"])

    def test_cache_state_is_dynamic_and_provider_factory_is_lazy(self):
        cached_ids = {"wd-vit-v3"}
        catalog = CaptionModelCatalog(
            dependency_checker=lambda module: True,
            cache_checker=lambda descriptor: descriptor.id in cached_ids,
            device_resolver=lambda descriptor: ["cpu", "cuda"],
        )
        summary = catalog.get("wd-vit-v3")
        self.assertEqual(summary.status, "ready")
        self.assertEqual(summary.capabilities.devices, ["cpu", "cuda"])

        downloads = []
        provider = catalog.create_provider(
            "wd-vit-v3",
            download_fn=lambda **kwargs: downloads.append(kwargs) or "unused",
            session_factory=lambda *args, **kwargs: None,
            available_providers_fn=lambda: ["CPUExecutionProvider"],
        )
        self.assertIsInstance(provider, WDTaggerProvider)
        self.assertIsInstance(provider, CaptionProvider)
        self.assertFalse(provider.loaded)
        self.assertEqual(downloads, [])

    def test_response_prefers_an_already_cached_model_over_a_download(self):
        catalog = CaptionModelCatalog(
            dependency_checker=lambda module: True,
            cache_checker=lambda descriptor: descriptor.id == "wd-convnext-v3",
            device_resolver=lambda descriptor: ["cpu"],
        )

        self.assertEqual(catalog.response().defaultModelId, "wd-convnext-v3")

    def test_builtin_descriptors_have_unique_ids(self):
        descriptors = builtin_model_descriptors()
        self.assertEqual(len(descriptors), len({descriptor.id for descriptor in descriptors}))

    def test_vlm_compatibility_metadata_matches_supported_runtime(self):
        descriptors = {descriptor.id: descriptor for descriptor in builtin_model_descriptors()}
        self.assertEqual(descriptors["joycaption-beta-one"].min_transformers, "4.51.0")
        self.assertEqual(descriptors["llava-onevision-0.5b"].capabilities.languages, ["en", "zh"])

    def test_dynamic_params_are_defaulted_and_strictly_validated(self):
        catalog = CaptionModelCatalog(
            dependency_checker=lambda module: True,
            cache_checker=lambda descriptor: False,
            device_resolver=lambda descriptor: ["cpu"],
        )
        values = catalog.validate_params("wd-vit-v3", {"threshold": 0.42})
        self.assertEqual(values["threshold"], 0.42)
        self.assertEqual(values["characterThreshold"], 0.6)
        with self.assertRaisesRegex(ValueError, "不支持以下参数"):
            catalog.validate_params("wd-vit-v3", {"unknown": True})
        with self.assertRaisesRegex(ValueError, "不能大于"):
            catalog.validate_params("wd-vit-v3", {"threshold": 2.0})
        with self.assertRaisesRegex(ValueError, "必须是数字"):
            catalog.validate_params("wd-vit-v3", {"threshold": True})

    def test_catalog_explains_transformers_version_boundary(self):
        catalog = CaptionModelCatalog(
            dependency_checker=lambda module: True,
            cache_checker=lambda descriptor: False,
            device_resolver=lambda descriptor: ["cpu"],
        )
        qwen3 = catalog.get("qwen3-vl-4b")
        self.assertEqual(qwen3.status, "unavailable")
        self.assertIn("4.57.0", qwen3.statusReason)
        self.assertFalse(qwen3.trustRemoteCode)


if __name__ == "__main__":
    unittest.main()
