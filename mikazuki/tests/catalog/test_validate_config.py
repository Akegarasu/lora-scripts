import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.catalog.validate_config import ConfigValidationError, _flatten_toml, validate_config


class ConfigValidationTests(unittest.TestCase):
    def test_flatten_toml_removes_group_sections(self) -> None:
        flattened = _flatten_toml(
            {
                "model": {"pretrained_model_name_or_path": "model.safetensors"},
                "training": {"max_train_epochs": 10, "learning_rate": 0.0001},
                "seed": 42,
            }
        )

        self.assertEqual(
            flattened,
            {
                "pretrained_model_name_or_path": "model.safetensors",
                "max_train_epochs": 10,
                "learning_rate": 0.0001,
                "seed": 42,
            },
        )

    def test_validate_config_rejects_unknown_keys_before_loading_scripts(self) -> None:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--known")

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "train.toml"
            config_path.write_text("[training]\nknown = 1\nunknown = 2\n", encoding="utf-8")

            with patch("mikazuki.catalog.validate_config._extract_parser", return_value=parser):
                with self.assertRaisesRegex(ConfigValidationError, r"unknown config keys: unknown"):
                    validate_config("sd.lora", config_path)


if __name__ == "__main__":
    unittest.main()
