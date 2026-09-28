import re
import unittest

from mikazuki.catalog.loader import CatalogService


class CatalogIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = CatalogService()

    def test_generated_catalog_keeps_full_argument_sets(self) -> None:
        minimum_param_counts = {
            "sd.lora": 190,
            "sdxl.lora": 190,
            "sd3.lora": 210,
            "flux.lora": 210,
            "chroma.lora": 210,
            "lumina.lora": 210,
            "hunyuan_image.lora": 210,
            "anima.lora": 220,
        }

        for trainer_id, minimum_count in minimum_param_counts.items():
            with self.subTest(trainer_id=trainer_id):
                trainer = self.catalog.get_trainer(trainer_id)
                self.assertIsNotNone(trainer)
                assert trainer is not None
                self.assertGreaterEqual(len(trainer.params), minimum_count)

    def test_common_and_trainer_overlays_merge_in_order(self) -> None:
        trainer = self.catalog.get_trainer("flux.lora")

        self.assertIsNotNone(trainer)
        assert trainer is not None
        learning_rate = trainer.params["learning_rate"]
        self.assertEqual(learning_rate.label, "总学习率")
        self.assertEqual(learning_rate.group, "optimizer")
        self.assertEqual(learning_rate.priority, "recommended")
        self.assertEqual(learning_rate.effectiveDefault, 0.0001)
        self.assertEqual(trainer.defaultNetworkModule, "networks.lora_flux")
        self.assertEqual(trainer.params["network_module"].effectiveDefault, "networks.lora_flux")
        flux_model = trainer.params["pretrained_model_name_or_path"]
        self.assertEqual(flux_model.control, "fileOrFolder")
        self.assertIsNone(flux_model.fileKind)
        sd_trainer = self.catalog.get_trainer("sd.lora")
        assert sd_trainer is not None
        self.assertEqual(
            sd_trainer.params["pretrained_model_name_or_path"].control,
            "modelSource",
        )
        self.assertEqual(sd_trainer.params["vae"].control, "modelSource")
        self.assertIsNone(sd_trainer.params["vae"].fileKind)
        sdxl_trainer = self.catalog.get_trainer("sdxl.lora")
        assert sdxl_trainer is not None
        self.assertEqual(sdxl_trainer.params["vae"].control, "modelSource")
        self.assertIsNone(sdxl_trainer.params["vae"].fileKind)
        anima_trainer = self.catalog.get_trainer("anima.lora")
        assert anima_trainer is not None
        self.assertEqual(anima_trainer.params["qwen3"].control, "fileOrFolder")
        self.assertIsNone(anima_trainer.params["qwen3"].fileKind)

    def test_trainer_specific_dataset_and_optimization_defaults(self) -> None:
        expected_dataset_defaults = {
            "sd.lora": ([512, 512], 64),
            "sdxl.lora": ([1024, 1024], 32),
            "sd3.lora": ([1024, 1024], 32),
            "flux.lora": ([1024, 1024], 32),
            "chroma.lora": ([1024, 1024], 32),
            "lumina.lora": ([1024, 1024], 16),
            "hunyuan_image.lora": ([1024, 1024], 32),
            "anima.lora": ([1024, 1024], 16),
        }

        summaries = {summary.id: summary for summary in self.catalog.list_trainers()}
        for trainer_id, (resolution, bucket_step) in expected_dataset_defaults.items():
            with self.subTest(trainer_id=trainer_id):
                trainer = self.catalog.get_trainer(trainer_id)
                assert trainer is not None
                self.assertEqual(trainer.datasetDefaults["resolution"], resolution)
                self.assertEqual(trainer.datasetDefaults["bucketResoSteps"], bucket_step)
                self.assertEqual(summaries[trainer_id].datasetDefaults, trainer.datasetDefaults)

        sd3 = self.catalog.get_trainer("sd3.lora")
        lumina = self.catalog.get_trainer("lumina.lora")
        hunyuan = self.catalog.get_trainer("hunyuan_image.lora")
        sdxl = self.catalog.get_trainer("sdxl.lora")
        assert sd3 is not None and lumina is not None and hunyuan is not None and sdxl is not None
        self.assertEqual(sd3.params["network_dim"].effectiveDefault, 16)
        self.assertEqual(lumina.params["network_dim"].effectiveDefault, 8)
        self.assertEqual(lumina.params["optimizer_type"].effectiveDefault, "AdamW")
        self.assertFalse(hunyuan.params["fp8_scaled"].effectiveDefault)
        self.assertTrue(sdxl.params["gradient_checkpointing"].effectiveDefault)

    def test_suggested_selects_preserve_custom_values(self) -> None:
        trainer = self.catalog.get_trainer("sd.lora")
        assert trainer is not None

        optimizer = trainer.params["optimizer_type"]
        scheduler = trainer.params["lr_scheduler"]
        self.assertEqual(optimizer.control, "select")
        self.assertIn("AdamW8bit", optimizer.choices or [])
        self.assertTrue(optimizer.extra.get("allowCustomChoice"))
        self.assertEqual(scheduler.control, "select")
        self.assertIn("cosine_with_restarts", scheduler.choices or [])
        self.assertTrue(scheduler.extra.get("allowCustomChoice"))
        self.assertEqual(
            trainer.params["huggingface_repo_visibility"].choices,
            ["private", "public"],
        )

        for trainer_id in ("hunyuan_image.lora", "anima.lora"):
            attention_trainer = self.catalog.get_trainer(trainer_id)
            assert attention_trainer is not None
            self.assertNotIn("sageattn", attention_trainer.params["attn_mode"].choices or [])

    def test_all_view_exposes_hidden_metadata_without_showing_it_in_product_views(self) -> None:
        all_names = {
            param["name"]
            for group in self.catalog.get_param_groups("flux.lora", view="all")
            for param in group["params"]
        }
        recommended_names = {
            param["name"]
            for group in self.catalog.get_param_groups("flux.lora", view="recommended")
            for param in group["params"]
        }

        self.assertIn("sample_sampler", all_names)
        self.assertNotIn("sample_sampler", recommended_names)

    def test_every_visible_parameter_has_a_chinese_product_description(self) -> None:
        chinese_text = re.compile(r"[\u3400-\u9fff]")
        missing = []

        for summary in self.catalog.list_trainers():
            trainer = self.catalog.get_trainer(summary.id)
            assert trainer is not None
            for param in trainer.params.values():
                if param.hidden:
                    continue
                if not param.description or chinese_text.search(param.description) is None:
                    missing.append(f"{trainer.id}.{param.name}")

        self.assertEqual(
            missing,
            [],
            "visible parameters without a Chinese product description: "
            + ", ".join(missing),
        )

    def test_recommended_view_focuses_on_training_controls_for_each_model(self) -> None:
        for summary in self.catalog.list_trainers():
            with self.subTest(trainer=summary.id):
                names = {
                    param["name"]
                    for group in self.catalog.get_param_groups(summary.id, view="recommended")
                    for param in group["params"]
                }
                self.assertTrue({
                    "learning_rate", "max_train_steps", "max_train_epochs",
                    "save_every_n_steps", "gradient_accumulation_steps",
                    "gradient_checkpointing", "cache_latents",
                }.issubset(names))
                self.assertTrue({
                    "network_module", "save_precision", "max_grad_norm",
                    "model_prediction_type", "guidance_scale", "show_timesteps",
                }.isdisjoint(names))
                is_sd = summary.id in {"sd.lora", "sdxl.lora"}
                for name in ("text_encoder_lr", "unet_lr", "min_snr_gamma"):
                    self.assertEqual(name in names, is_sd, name)
                self.assertEqual("no_half_vae" in names, summary.id == "sdxl.lora")
                self.assertEqual(
                    "fp8_base" in names,
                    summary.id in {"flux.lora", "chroma.lora", "sd3.lora"},
                )

    def test_diagnostic_and_experimental_options_remain_opt_in(self) -> None:
        for summary in self.catalog.list_trainers():
            trainer = self.catalog.get_trainer(summary.id)
            assert trainer is not None
            with self.subTest(trainer=summary.id):
                module = trainer.params["network_module"]
                self.assertEqual(module.effectiveDefault, trainer.defaultNetworkModule)
                self.assertFalse(module.required)
                if "show_timesteps" in trainer.params:
                    supports_preview = summary.id in {"flux.lora", "chroma.lora", "anima.lora"}
                    self.assertEqual(
                        trainer.params["show_timesteps"].priority,
                        "dangerous" if supports_preview else "hidden",
                    )
                    for name in ("show_timesteps", "show_timesteps_resolution", "show_timesteps_offset"):
                        self.assertEqual(trainer.params[name].hidden, not supports_preview)
                        self.assertIsNone(trainer.params[name].effectiveDefault)

        anima = self.catalog.get_trainer("anima.lora")
        assert anima is not None
        self.assertEqual(anima.params["compile_dynamic"].choices, ["true", "false", "auto"])
        for name in (
            "compile", "compile_backend", "compile_mode", "compile_dynamic",
            "compile_fullgraph", "compile_cache_size_limit", "cuda_allow_tf32",
            "cuda_cudnn_benchmark", "qwen_image_vae_2d",
        ):
            with self.subTest(parameter=name):
                self.assertEqual(anima.params[name].priority, "advanced")
                self.assertIsNone(anima.params[name].effectiveDefault)

    def test_anima_finetune_only_rates_are_preserved_but_not_offered_for_lora(self) -> None:
        def names(view: str) -> set:
            return {
                param["name"]
                for group in self.catalog.get_param_groups("anima.lora", view=view)
                for param in group["params"]
            }

        finetune_rates = {"self_attn_lr", "cross_attn_lr", "mlp_lr", "mod_lr", "llm_adapter_lr"}
        self.assertTrue(finetune_rates.issubset(names("all")))
        self.assertTrue(finetune_rates.isdisjoint(names("advanced")))
        self.assertIn("network_args", names("advanced"))

    def test_overlays_only_reference_real_parser_parameters(self) -> None:
        params_by_trainer = {
            summary.id: set(self.catalog.get_trainer(summary.id).params)
            for summary in self.catalog.list_trainers()
        }
        all_params = set().union(*params_by_trainer.values())
        unknown = [
            f"common.{name}"
            for name in self.catalog._common_overlay.get("params", {})
            if name not in all_params
        ]

        for trainer_id, overlay in self.catalog._trainer_overlays.items():
            unknown.extend(
                f"{trainer_id}.{name}"
                for name in overlay.get("params", {})
                if name not in params_by_trainer[trainer_id]
            )

        self.assertEqual(
            unknown,
            [],
            "overlay entries without a matching parser parameter: "
            + ", ".join(unknown),
        )


if __name__ == "__main__":
    unittest.main()
