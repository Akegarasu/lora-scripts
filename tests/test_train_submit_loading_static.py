import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_layout


SOURCE = Path("frontend/src/layout/layout.js")
DIST = Path("frontend/dist/assets/layout.96d49288.js")


class TrainSubmitLoadingStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = SOURCE.read_text(encoding="utf-8")

    def test_dist_is_generated_verbatim_from_layout_source(self):
        self.assertEqual(self.layout, DIST.read_text(encoding="utf-8"))

    def test_build_layout_copies_canonical_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "layout.js"
            with patch.object(build_layout, "OUTPUT", output):
                build_layout.build_layout()
            self.assertEqual(self.layout, output.read_text(encoding="utf-8"))

    def test_standard_train_submit_uses_writable_notice_and_restores_state(self):
        layout = self.layout
        self.assertIn("submitLoading = ref(!1)", layout)
        self.assertIn("submitNotice = ref(null)", layout)
        self.assertIn("if (submitLoading.value) return", layout)
        self.assertNotIn("const submitNotice = ElMessage(", layout)
        self.assertIn("任务正在提交中，请稍等", layout)
        self.assertIn("duration: 0", layout)
        self.assertIn('type: "info"', layout)
        self.assertIn("submitNotice.value && submitNotice.value.close()", layout)
        self.assertIn("submitNotice.value = null", layout)
        self.assertIn('ElMessage.success("训练已开始")', layout)
        self.assertIn("setSubmitButtonLoading(!1)", layout)
        self.assertIn("loading: submitLoading.value", layout)
        self.assertIn("disabled: submitLoading.value", layout)

    def test_imported_string_learning_rates_are_normalized(self):
        layout = self.layout
        self.assertNotIn("let r = e[t].toExponential()", layout)
        self.assertIn('if (typeof v === "string")', layout)
        self.assertIn("const p = parseFloat(v)", layout)
        self.assertIn('if (typeof v !== "number" || Number.isNaN(v)) continue', layout)
        self.assertIn("let r = v.toExponential()", layout)

    def test_config_import_full_replace_uses_normalized_values(self):
        layout = self.layout
        self.assertIn("findChangedDataBySchema(clone(cfg), schemaFn)", layout)
        self.assertIn("let defaults = schemaFn() || {}", layout)
        self.assertIn("Object.assign(applied, U)", layout)

    def test_preview_and_history_guards_remain_present(self):
        layout = self.layout
        self.assertIn('(e.optimizer_type || "").startsWith("DAdapt")', layout)
        self.assertIn('(e.optimizer_type || "").toLowerCase().startsWith("dada")', layout)
        self.assertIn("m.enable_preview = !0", layout)
        self.assertIn("const prev = clone(a.value)", layout)


if __name__ == "__main__":
    unittest.main()
