import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AnimaLokrConfigTests(unittest.TestCase):
    def test_vue_training_flow_uses_backend_export_normalization(self):
        page = (ROOT / "frontend/src/pages/TrainingPage.vue").read_text(encoding="utf-8")
        api = (ROOT / "frontend/src/api/training.ts").read_text(encoding="utf-8")
        self.assertIn("trainingApi.normalizeExport", page)
        self.assertIn("/api/config/normalize-for-export", api)

    def test_parameter_converter_strips_invalid_ui_only_lycoris_fields(self):
        params = (ROOT / "frontend/src/training/params.ts").read_text(encoding="utf-8")
        self.assertIn('config.network_module === "lycoris.kohya"', params)
        self.assertIn('`algo=${config.lycoris_algo}`', params)
        self.assertIn("remove(config, UI_PARAMS)", params)


if __name__ == "__main__":
    unittest.main()
