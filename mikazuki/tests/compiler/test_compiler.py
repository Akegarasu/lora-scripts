import tempfile
import unittest
from pathlib import Path

import toml

from mikazuki.compiler.compiler import compile_draft
from mikazuki.compiler.models import TrainDraft


def make_draft(**overrides) -> TrainDraft:
    payload = {
        "trainerId": "sd.lora",
        "name": "unit_test_lora",
        "modelAssets": {"pretrained_model_name_or_path": "owner/model"},
        "dataset": {"mode": "simple", "root": "dataset"},
        "params": {},
        "sample": {"enabled": False},
    }
    payload.update(overrides)
    return TrainDraft(**payload)


def flatten_toml(content: str) -> dict:
    flattened = {}
    for value in toml.loads(content).values():
        if isinstance(value, dict):
            flattened.update(value)
    return flattened


class CompilerParameterChainTests(unittest.TestCase):
    def test_partial_dataset_uses_the_selected_trainer_defaults(self) -> None:
        result = compile_draft(
            make_draft(dataset={"mode": "simple", "root": "dataset"}),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(result.errors, [])
        dataset = toml.loads(result.datasetConfig or "")["datasets"][0]
        self.assertEqual(dataset["resolution"], [512, 512])
        self.assertEqual(dataset["max_bucket_reso"], 1024)
        self.assertEqual(dataset["bucket_reso_steps"], 64)

    def test_suggested_select_accepts_a_custom_optimizer_class(self) -> None:
        result = compile_draft(
            make_draft(params={"optimizer_type": "package.optim.CustomOptimizer"}),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(result.errors, [])
        values = flatten_toml(result.trainConfig or "")
        self.assertEqual(values["optimizer_type"], "package.optim.CustomOptimizer")

    def test_small_learning_rates_survive_toml_serialization(self) -> None:
        for learning_rate in (1e-5, 1e-20, 5e-324):
            with self.subTest(learning_rate=learning_rate):
                result = compile_draft(
                    make_draft(params={"learning_rate": learning_rate}),
                    persist=False,
                    validate_paths=False,
                )

                self.assertEqual(result.errors, [])
                values = flatten_toml(result.trainConfig or "")
                self.assertEqual(values["learning_rate"], learning_rate)
                self.assertNotEqual(values["learning_rate"], 0)

    def test_hard_parser_choice_still_rejects_an_unknown_value(self) -> None:
        result = compile_draft(
            make_draft(params={"mixed_precision": "float16"}),
            persist=False,
            validate_paths=False,
        )

        self.assertIn("param.invalid", {error.code for error in result.errors})

    def test_anima_text_cache_allows_whole_caption_dropout_only(self) -> None:
        assets = {
            "pretrained_model_name_or_path": "anima.safetensors",
            "qwen3": "qwen3.safetensors",
            "vae": "vae.safetensors",
        }
        allowed = compile_draft(
            make_draft(
                trainerId="anima.lora",
                modelAssets=assets,
                params={"caption_dropout_rate": 0.1},
            ),
            persist=False,
            validate_paths=False,
        )
        rejected = compile_draft(
            make_draft(
                trainerId="anima.lora",
                modelAssets=assets,
                params={"caption_tag_dropout_rate": 0.1},
            ),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(allowed.errors, [])
        self.assertIn(
            "param.conflict.cache_text_encoder_outputs",
            {error.code for error in rejected.errors},
        )

    def test_step_limit_replaces_overlay_epoch_default_when_epoch_is_absent(self) -> None:
        result = compile_draft(
            make_draft(params={"max_train_steps": 250}),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(result.errors, [])
        values = flatten_toml(result.trainConfig or "")
        self.assertEqual(values["max_train_steps"], 250)
        self.assertNotIn("max_train_epochs", values)

    def test_explicit_null_suppresses_an_effective_default(self) -> None:
        result = compile_draft(
            make_draft(params={"max_train_epochs": None}),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(result.errors, [])
        self.assertNotIn("max_train_epochs", flatten_toml(result.trainConfig or ""))

    def test_explicit_epoch_and_step_limits_are_rejected(self) -> None:
        result = compile_draft(
            make_draft(params={"max_train_epochs": 2, "max_train_steps": 250}),
            persist=False,
            validate_paths=False,
        )

        self.assertIn(
            "param.conflict.training_duration",
            {error.code for error in result.errors},
        )

    def test_structured_dataset_fields_cannot_override_dataset_toml(self) -> None:
        result = compile_draft(
            make_draft(params={"train_data_dir": "wrong", "resolution": "512,512"}),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(result.errors, [])
        values = flatten_toml(result.trainConfig or "")
        self.assertNotIn("train_data_dir", values)
        self.assertNotIn("resolution", values)
        self.assertIn("dataset_config", values)
        self.assertEqual(
            {warning.code for warning in result.warnings},
            {"param.managed"},
        )

    def test_explicit_false_disables_a_true_effective_default(self) -> None:
        result = compile_draft(
            make_draft(params={"cache_latents": False}),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(result.errors, [])
        self.assertNotIn("cache_latents", flatten_toml(result.trainConfig or ""))

    def test_each_run_gets_an_isolated_local_event_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = compile_draft(
                make_draft(),
                persist=False,
                validate_paths=False,
                base_dir=root,
            )
            second = compile_draft(
                make_draft(),
                persist=False,
                validate_paths=False,
                base_dir=root,
            )

        self.assertEqual(first.errors, [])
        self.assertEqual(second.errors, [])
        self.assertIsNotNone(first.runId)
        self.assertIsNotNone(second.runId)
        self.assertNotEqual(first.runId, second.runId)

        first_values = flatten_toml(first.trainConfig or "")
        second_values = flatten_toml(second.trainConfig or "")
        first_expected = root / "logs" / "jobs" / f"job_{first.runId}" / "events"
        second_expected = root / "logs" / "jobs" / f"job_{second.runId}" / "events"
        self.assertEqual(Path(first_values["logging_dir"]), first_expected.resolve())
        self.assertEqual(Path(second_values["logging_dir"]), second_expected.resolve())
        self.assertEqual(first_values["log_prefix"], f"{first.runId}-")
        self.assertEqual(second_values["log_prefix"], f"{second.runId}-")

    def test_custom_logging_root_and_prefix_still_receive_a_job_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = compile_draft(
                make_draft(
                    params={
                        "logging_dir": "custom-events",
                        "log_prefix": "portrait-",
                    }
                ),
                persist=False,
                validate_paths=False,
                base_dir=root,
            )

        self.assertEqual(result.errors, [])
        values = flatten_toml(result.trainConfig or "")
        expected = root / "custom-events" / "jobs" / f"job_{result.runId}" / "events"
        self.assertEqual(Path(values["logging_dir"]), expected.resolve())
        self.assertEqual(values["log_prefix"], f"{result.runId}-")
        self.assertIn(
            "logging.log_prefix.managed",
            {warning.code for warning in result.warnings},
        )

    def test_wandb_also_enables_the_local_event_writer(self) -> None:
        result = compile_draft(
            make_draft(params={"log_with": "wandb"}),
            persist=False,
            validate_paths=False,
        )

        self.assertEqual(result.errors, [])
        self.assertEqual(flatten_toml(result.trainConfig or "")["log_with"], "all")
        self.assertIn(
            "logging.local_events.enabled",
            {warning.code for warning in result.warnings},
        )

    def test_persisted_artifacts_expose_the_event_discovery_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = compile_draft(
                make_draft(),
                persist=True,
                validate_paths=False,
                base_dir=root,
            )

            values = flatten_toml(result.trainConfig or "")
            self.assertEqual(result.errors, [])
            self.assertEqual(result.artifacts.loggingDir, values["logging_dir"])
            self.assertEqual(result.artifacts.logPrefix, values["log_prefix"])
            self.assertTrue(Path(result.artifacts.trainConfig or "").is_file())

    def test_sampling_requires_one_schedule_and_rejects_both(self) -> None:
        no_schedule = compile_draft(
            make_draft(
                sample={
                    "enabled": True,
                    "prompts": [{"prompt": "portrait"}],
                }
            ),
            persist=False,
            validate_paths=False,
        )
        conflicting = compile_draft(
            make_draft(
                sample={
                    "enabled": True,
                    "everyNEpochs": 1,
                    "everyNSteps": 50,
                    "prompts": [{"prompt": "portrait"}],
                }
            ),
            persist=False,
            validate_paths=False,
        )

        self.assertIn("sample.schedule.required", {error.code for error in no_schedule.errors})
        self.assertIn("sample.schedule.conflict", {error.code for error in conflicting.errors})

    def test_output_name_must_be_a_safe_file_name(self) -> None:
        missing = compile_draft(
            make_draft(name=" "),
            persist=False,
            validate_paths=False,
        )
        traversal = compile_draft(
            make_draft(name="../escaped"),
            persist=False,
            validate_paths=False,
        )

        self.assertIn("output.name.required", {error.code for error in missing.errors})
        self.assertIn("output.name.invalid", {error.code for error in traversal.errors})

    def test_model_source_distinguishes_local_files_from_repository_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "image.png").write_bytes(b"not-an-image-but-enough-for-path-validation")

            local_result = compile_draft(
                make_draft(
                    modelAssets={"pretrained_model_name_or_path": "missing.safetensors"},
                    dataset={"mode": "simple", "root": str(dataset)},
                ),
                persist=False,
                validate_paths=True,
                base_dir=root,
            )
            repository_result = compile_draft(
                make_draft(
                    modelAssets={"pretrained_model_name_or_path": "owner/model"},
                    dataset={"mode": "simple", "root": str(dataset)},
                ),
                persist=False,
                validate_paths=True,
                base_dir=root,
            )

        self.assertIn("path.missing", {error.code for error in local_result.errors})
        self.assertNotIn("path.missing", {error.code for error in repository_result.errors})
        self.assertNotIn(
            "params.logging_dir",
            {
                warning.field
                for warning in repository_result.warnings
                if warning.code == "path.missing"
            },
        )

    def test_flux_local_diffusers_directory_is_not_rejected_as_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "image.png").write_bytes(b"image")
            model_dir = root / "flux-diffusers"
            model_dir.mkdir()
            assets = {"pretrained_model_name_or_path": str(model_dir)}
            for name in ("clip_l", "t5xxl", "ae"):
                path = root / f"{name}.safetensors"
                path.write_bytes(b"model")
                assets[name] = str(path)

            result = compile_draft(
                make_draft(
                    trainerId="flux.lora",
                    modelAssets=assets,
                    dataset={"mode": "simple", "root": str(dataset)},
                ),
                persist=False,
                validate_paths=True,
                base_dir=root,
            )

        self.assertNotIn("path.not_file", {error.code for error in result.errors})
        self.assertEqual(result.errors, [])

    def test_anima_qwen3_local_directory_is_not_rejected_as_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "image.png").write_bytes(b"image")
            qwen3_dir = root / "qwen3"
            qwen3_dir.mkdir()
            dit = root / "anima.safetensors"
            dit.write_bytes(b"model")
            vae = root / "vae.safetensors"
            vae.write_bytes(b"model")

            result = compile_draft(
                make_draft(
                    trainerId="anima.lora",
                    modelAssets={
                        "pretrained_model_name_or_path": str(dit),
                        "qwen3": str(qwen3_dir),
                        "vae": str(vae),
                    },
                    dataset={"mode": "simple", "root": str(dataset)},
                ),
                persist=False,
                validate_paths=True,
                base_dir=root,
            )

        self.assertNotIn("path.not_file", {error.code for error in result.errors})
        self.assertEqual(result.errors, [])

    def test_sd_vae_accepts_local_file_directory_and_repository_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset"
            dataset.mkdir()
            (dataset / "image.png").write_bytes(b"image")
            vae_file = root / "vae.safetensors"
            vae_file.write_bytes(b"model")
            vae_dir = root / "vae-diffusers"
            vae_dir.mkdir()

            for trainer_id in ("sd.lora", "sdxl.lora"):
                for vae_source in (str(vae_file), str(vae_dir), "owner/vae-repository"):
                    with self.subTest(trainer_id=trainer_id, vae_source=vae_source):
                        result = compile_draft(
                            make_draft(
                                trainerId=trainer_id,
                                modelAssets={
                                    "pretrained_model_name_or_path": "owner/base-model",
                                    "vae": vae_source,
                                },
                                dataset={"mode": "simple", "root": str(dataset)},
                            ),
                            persist=False,
                            validate_paths=True,
                            base_dir=root,
                        )

                        error_codes = {error.code for error in result.errors}
                        self.assertNotIn("path.not_file", error_codes)
                        self.assertNotIn("path.not_folder", error_codes)
                        self.assertEqual(result.errors, [])


if __name__ == "__main__":
    unittest.main()
