import tempfile
import unittest
from pathlib import Path

import toml

from mikazuki.compiler.compiler import compile_draft
from mikazuki.tests.compiler.test_compiler import flatten_toml, make_draft


def moss_draft(**overrides):
    payload = {
        "trainerId": "moss_image.lora",
        "modelAssets": {
            "pretrained_model_name_or_path": "models/moss.safetensors",
            "text_encoder": "models/model-00001-of-00004.safetensors",
            "vae": "models/flux2-vae.safetensors",
        },
    }
    payload.update(overrides)
    return make_draft(**payload)


def compile_moss(**overrides):
    return compile_draft(moss_draft(**overrides), persist=False, validate_paths=False)


class MossImageCompilerTests(unittest.TestCase):
    def test_default_recipe_selects_upstream_script_and_model_inputs(self):
        result = compile_moss()
        self.assertEqual(result.errors, [])
        self.assertIn("scripts/dev/moss_image_train_network.py", result.command)
        config = flatten_toml(result.trainConfig)
        self.assertEqual(config["network_module"], "networks.lora_generic")
        self.assertEqual(config["mixed_precision"], "bf16")
        self.assertTrue(config["network_train_unet_only"])
        self.assertEqual(config["timestep_sampling"], "truncated_logit_normal")
        self.assertEqual(config["logit_mean"], -1.09)
        self.assertEqual(config["logit_std"], 0.95)
        self.assertEqual(config["discrete_flow_shift"], 1.0)
        dataset = toml.loads(result.datasetConfig)["datasets"][0]
        self.assertEqual(dataset["bucket_reso_steps"] % 16, 0)

    def test_all_three_model_files_are_required(self):
        result = compile_moss(modelAssets={})
        fields = {error.field for error in result.errors if error.code == "param.required"}
        self.assertTrue({
            "params.pretrained_model_name_or_path", "params.text_encoder", "params.vae",
        }.issubset(fields))

    def test_shard_inputs_are_local_files_not_repository_ids_or_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dataset").mkdir()
            (root / "dataset" / "image.png").touch()
            (root / "models").mkdir()
            assets = {name: "models" for name in moss_draft().modelAssets}
            result = compile_draft(moss_draft(modelAssets=assets), persist=False, base_dir=root)
            self.assertEqual(
                {error.field for error in result.errors if error.code == "path.not_file"},
                {f"params.{name}" for name in assets},
            )

    def test_caption_cache_supports_dropout_and_multiline_but_not_shuffle(self):
        result = compile_moss(params={
            "caption_dropout_rate": 0.1,
            "enable_multiline_caption": True,
            "multiline_caption_separator": "---===---",
        })
        self.assertEqual(result.errors, [])
        config = flatten_toml(result.trainConfig)
        self.assertTrue(config["enable_multiline_caption"])
        self.assertEqual(config["multiline_caption_separator"], "---===---")
        for params in ({"caption_tag_dropout_rate": 0.1}, {"token_warmup_step": 5}):
            with self.subTest(params=params):
                rejected = compile_moss(params=params)
                self.assertIn("param.conflict.cache_text_encoder_outputs", {e.code for e in rejected.errors})
        rejected = compile_moss(dataset={"root": "dataset", "shuffleCaption": True})
        self.assertIn("param.conflict.cache_text_encoder_outputs", {e.code for e in rejected.errors})

    def test_text_encoder_training_requires_both_caches_disabled(self):
        rejected = compile_moss(params={"network_train_unet_only": False})
        self.assertIn("param.requires.moss_image_unet_only", {e.code for e in rejected.errors})
        allowed = compile_moss(params={
            "network_train_unet_only": False,
            "cache_text_encoder_outputs": False,
            "cache_text_encoder_outputs_to_disk": False,
        })
        self.assertEqual(allowed.errors, [])

    def test_model_specific_invalid_combinations_are_rejected(self):
        cases = [
            ({"fp8_base": True}, "param.unsupported.moss_fp8"),
            ({"blocks_to_swap": 41}, "param.max"),
            ({"moss_max_token_length": 4097}, "param.max"),
            ({"compile": True, "torch_compile": True}, "param.conflict.compile"),
            ({"compile": True, "compile_fullgraph": True, "split_attn": True}, "param.conflict.compile_split_attention"),
            ({"attn_mode": "xformers"}, "param.requires.split_attention"),
            ({"sample_uncond_skip_layers": "42"}, "param.invalid.sample_uncond_skip_layers"),
            ({"timestep_cutoff": 0}, "param.positive.truncated_logit_normal"),
            ({"logit_std": 0}, "param.positive.truncated_logit_normal"),
            ({"logit_std": -1}, "param.positive.truncated_logit_normal"),
            ({"discrete_flow_shift": 0}, "param.positive.discrete_flow_shift"),
        ]
        for params, code in cases:
            with self.subTest(params=params):
                result = compile_moss(params=params)
                self.assertIn(code, {error.code for error in result.errors})
        result = compile_moss(dataset={"root": "dataset", "bucketResoSteps": 8})
        self.assertIn("dataset.bucket_step.model_alignment", {error.code for error in result.errors})

    def test_h2d_swap_requires_blocks_and_checkpointing(self):
        allowed = compile_moss(params={"block_swap_h2d_only": True, "blocks_to_swap": 20})
        self.assertEqual(allowed.errors, [])
        rejected = compile_moss(params={"block_swap_h2d_only": True, "gradient_checkpointing": False})
        self.assertTrue({"param.requires.blocks_to_swap", "param.requires.h2d_gradient_checkpointing"}.issubset(
            {error.code for error in rejected.errors}
        ))
        sd3 = compile_draft(make_draft(trainerId="sd3.lora", params={
            "block_swap_h2d_only": True, "blocks_to_swap": 2,
        }), persist=False, validate_paths=False)
        self.assertIn("param.unsupported.block_swap_h2d_only", {error.code for error in sd3.errors})

    def test_empty_skip_layers_survives_toml_and_null_uses_parser_default(self):
        disabled = compile_moss(params={"sample_uncond_skip_layers": ""})
        self.assertEqual(disabled.errors, [])
        self.assertEqual(flatten_toml(disabled.trainConfig)["sample_uncond_skip_layers"], "")
        default = compile_moss(params={"sample_uncond_skip_layers": None})
        self.assertNotIn("sample_uncond_skip_layers", flatten_toml(default.trainConfig))

    def test_preview_uses_fixed_euler_sampler(self):
        sample = {"enabled": True, "everyNEpochs": 1, "prompts": [{"prompt": "A cat"}]}
        for sampler in (None, "euler"):
            result = compile_moss(sample={**sample, "sampler": sampler})
            self.assertEqual(result.errors, [])
            self.assertNotIn("sample_sampler", flatten_toml(result.trainConfig))
        result = compile_moss(sample={**sample, "sampler": "ddim"})
        self.assertIn("sample.sampler.unsupported", {error.code for error in result.errors})

    def test_multiline_preview_stays_on_one_physical_line(self):
        result = compile_moss(sample={
            "enabled": True, "everyNEpochs": 1,
            "prompts": [{"prompt": "A cat\r\non a table", "negativePrompt": "blur\nnoise"}],
        })
        self.assertEqual(result.errors, [])
        self.assertEqual(result.samplePrompts, "A cat\\non a table --n blur\\nnoise\n")
