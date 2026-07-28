import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TrainSubmitSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (ROOT / "frontend/src/pages/TrainingPage.vue").read_text(encoding="utf-8")
        cls.params = (ROOT / "frontend/src/training/params.ts").read_text(encoding="utf-8")

    def test_submit_has_immediate_loading_and_finally_restore(self):
        self.assertIn("submitting.value = true", self.page)
        self.assertIn("if (!validate() || submitting.value) return", self.page)
        self.assertIn("finally { submitting.value = false }", self.page)
        self.assertIn('submitting ? "提交中…" : "开始训练"', self.page)

    def test_training_flow_uses_backend_contracts(self):
        self.assertIn("trainingApi.validateImport", self.page)
        self.assertIn("trainingApi.normalizeExport", self.page)
        self.assertIn("trainingApi.animaFastPreflight", self.page)
        self.assertIn("trainingApi.run", self.page)

    def test_parameter_conversion_keeps_regression_guards(self):
        self.assertIn('optimizer.toLowerCase().startsWith("dada")', self.params)
        self.assertIn("config.enable_preview = true", self.params)
        self.assertIn("Number.parseFloat", self.params)
        self.assertIn("hydrateImportedConfig", self.params)


if __name__ == "__main__":
    unittest.main()
