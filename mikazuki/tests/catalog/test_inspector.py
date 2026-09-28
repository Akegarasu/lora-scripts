import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mikazuki.catalog.inspector import _extract_actions, generate_manifest


def int_or_float(value: str):
    number = float(value)
    return int(number) if number.is_integer() and number >= 1 else number


class InspectorActionTests(unittest.TestCase):
    def test_extracts_boolean_integer_or_number_and_numeric_array_actions(self) -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--enabled", action="store_true", help="enable the feature")
        parser.add_argument("--warmup", type=int_or_float, default=0)
        parser.add_argument("--rates", type=float, nargs="+")

        params = _extract_actions(parser, "fake_train")

        self.assertEqual(params["enabled"]["type"], "boolean")
        self.assertEqual(params["enabled"]["action"], "store_true")
        self.assertFalse(params["enabled"]["default"])

        self.assertEqual(params["warmup"]["type"], "integer_or_number")
        self.assertEqual(params["warmup"]["action"], "store")

        self.assertEqual(params["rates"]["type"], "array")
        self.assertEqual(params["rates"]["itemType"], "number")
        self.assertEqual(params["rates"]["nargs"], "+")


class InspectorProvenanceTests(unittest.TestCase):
    def test_upstream_revision_is_recorded_and_invalidates_manifest_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scripts_root = Path(directory)
            with patch("mikazuki.catalog.inspector.TRAINERS", {}):
                original = generate_manifest(scripts_root)
                upstream = {"repository": "https://github.com/kohya-ss/sd-scripts", "commit": "a" * 40}
                source = scripts_root / "UPSTREAM.json"
                source.write_text(json.dumps(upstream), encoding="utf-8")
                first = generate_manifest(scripts_root)
                again = generate_manifest(scripts_root)
                upstream["commit"] = "b" * 40
                source.write_text(json.dumps(upstream), encoding="utf-8")
                updated = generate_manifest(scripts_root)

        self.assertNotIn("upstream", original)
        self.assertEqual(first["upstream"]["commit"], "a" * 40)
        self.assertEqual(first["manifestHash"], again["manifestHash"])
        self.assertNotEqual(first["manifestHash"], updated["manifestHash"])

    def test_invalid_upstream_metadata_does_not_generate_a_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scripts_root = Path(directory)
            (scripts_root / "UPSTREAM.json").write_text("[]", encoding="utf-8")
            with patch("mikazuki.catalog.inspector.TRAINERS", {}):
                with self.assertRaisesRegex(ValueError, "must contain an object"):
                    generate_manifest(scripts_root)


if __name__ == "__main__":
    unittest.main()
