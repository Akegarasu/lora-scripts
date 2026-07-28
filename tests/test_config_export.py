"""Export/preview normalization uses the same adapter as training."""

import unittest

from fastapi.testclient import TestClient

from mikazuki.app.application import app
from mikazuki.utils.config_export import normalize_config_for_export
from mikazuki.utils.config_import import validate_config_import, _looks_like_sd_scripts_toml


class ConfigExportTests(unittest.TestCase):
    def test_lokr_empty_conv_dim_omits_undefined_from_network_args(self):
        config = {
            "model_train_type": "anima-lora",
            "network_module": "lycoris.kohya",
            "lycoris_algo": "lokr",
            "lokr_factor": -1,
            "lora_type": "lokr",
            "conv_dim": "",
            "conv_alpha": "",
            "dropout": "",
        }
        exported, _warnings = normalize_config_for_export(
            config,
            page_train_type="sd3-lora",
        )
        args = exported.get("network_args") or []
        self.assertIn("algo=lokr", args)
        self.assertIn("factor=-1", args)
        self.assertFalse(any("undefined" in item for item in args))
        self.assertFalse(any(item.startswith("conv_dim=") for item in args))

    def test_export_keeps_gui_fields_and_matches_adapter_network_args(self):
        from mikazuki.anima_backend.adapter import adapt_anima_config

        config = {
            "model_train_type": "anima-lora",
            "lora_type": "lokr",
            "network_module": "lycoris.kohya",
            "network_dim": 16,
            "network_alpha": 16,
            "lycoris_algo": "lokr",
            "lokr_factor": -1,
        }
        exported, _ = normalize_config_for_export(
            config,
            page_train_type="sd3-lora",
        )
        adapted, _warnings = adapt_anima_config(
            {k: v for k, v in config.items() if k != "model_train_type"},
        )
        self.assertEqual(exported.get("network_args"), adapted.get("network_args"))
        self.assertEqual(exported.get("model_train_type"), "anima-lora")
        self.assertEqual(exported.get("lora_type"), "lokr")
        self.assertFalse(_looks_like_sd_scripts_toml(exported))

    def test_export_does_not_warn_for_preserved_gui_fields(self):
        config = {
            "model_train_type": "anima-lora",
            "lora_type": "lora",
            "enable_preview": True,
            "positive_prompts": "portrait",
            "custom_gui_field": "preserved for re-import",
        }

        exported, warnings = normalize_config_for_export(
            config,
            page_train_type="sd3-lora",
        )

        self.assertEqual(exported["custom_gui_field"], "preserved for re-import")
        self.assertFalse(
            any(warning.startswith("Unknown field passed through") for warning in warnings)
        )

    def test_gui_export_reimports_on_anima_page(self):
        config = {
            "model_train_type": "anima-lora",
            "network_module": "lycoris.kohya",
            "lycoris_algo": "lokr",
            "lokr_factor": -1,
            "pretrained_model_name_or_path": "./sd-models/anima/anima-base-v1.0.safetensors",
            "train_data_dir": "./train/aki",
            "output_dir": "./output",
            "output_name": "aki",
        }
        exported, _ = normalize_config_for_export(
            config,
            page_train_type="sd3-lora",
        )
        result = validate_config_import("sd3-lora", exported)
        self.assertEqual(result["result"], "ok")
        self.assertIn("model_train_type", result["config"])
        args = result["config"].get("network_args") or []
        self.assertFalse(any("undefined" in item for item in args))

    def test_normalize_for_export_api(self):
        client = TestClient(app)
        response = client.post(
            "/api/config/normalize-for-export",
            json={
                "page_train_type": "sd3-lora",
                "config": {
                    "model_train_type": "anima-lora",
                    "lora_type": "lokr",
                    "network_module": "lycoris.kohya",
                    "lycoris_algo": "lokr",
                    "lokr_factor": -1,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        cfg = payload["data"]["config"]
        self.assertEqual(cfg.get("model_train_type"), "anima-lora")
        self.assertEqual(cfg.get("lora_type"), "lokr")
        args = cfg.get("network_args") or []
        self.assertIn("algo=lokr", args)
        self.assertIn("factor=-1", args)
        self.assertFalse(any("undefined" in item for item in args))


if __name__ == "__main__":
    unittest.main()
