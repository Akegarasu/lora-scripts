import argparse
import unittest

from mikazuki.catalog.inspector import _extract_actions


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


if __name__ == "__main__":
    unittest.main()
