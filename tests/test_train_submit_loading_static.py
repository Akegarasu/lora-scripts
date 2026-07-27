import unittest
from pathlib import Path

from scripts import patch_config_import_layout


class TrainSubmitLoadingStaticTests(unittest.TestCase):
    def test_standard_train_submit_uses_writable_notice_and_restores_state(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("submitLoading=ref(!1)", layout)
        self.assertIn("setSubmitButtonLoading=", layout)
        self.assertIn("trainSubmitButton", layout)
        self.assertIn("if(submitLoading.value)return", layout)
        self.assertIn("submitLoading=ref(!1),submitNotice=ref(null)", layout)
        self.assertIn(
            "submitLoading.value=!0,setSubmitButtonLoading(!0),0;try{submitNotice.value=ElMessage(",
            layout,
        )
        self.assertNotIn("const submitNotice=ElMessage(", layout)
        self.assertNotIn("submitNotice=null,setSubmitButtonLoading=", layout)
        self.assertIn("任务正在提交中，请稍等", layout)
        self.assertIn('duration:0,type:"info"', layout)
        self.assertIn("submitNotice.value&&submitNotice.value.close()", layout)
        self.assertIn("submitNotice.value=null", layout)
        self.assertIn('ElMessage.success("训练已开始")', layout)
        self.assertNotIn('message:"正在提交训练任务...",duration:2e3', layout)
        self.assertIn("setSubmitButtonLoading(!1)", layout)
        self.assertIn(
            'try{submitNotice.value=ElMessage({message:"任务正在提交中，请稍等",duration:0,type:"info"});const _=parseParams(n.value(a.value),t);',
            layout,
        )
        self.assertIn(
            "finally{submitNotice.value&&submitNotice.value.close(),submitNotice.value=null,submitLoading.value=!1",
            layout,
        )
        self.assertIn("loading:submitLoading.value", layout)
        self.assertIn("disabled:submitLoading.value", layout)

    def test_imported_string_learning_rates_are_normalized_before_exponential_formatting(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("let r=e[t].toExponential()", layout)
        self.assertIn(
            'if(typeof v==="string"){const p=parseFloat(v);v=Number.isNaN(p)?v:p}',
            layout,
        )
        self.assertIn('if(typeof v!=="number"||Number.isNaN(v))continue;', layout)
        self.assertIn("let r=v.toExponential()", layout)

    def test_config_import_validation_does_not_mutate_full_replace_source(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("let U=findChangedDataBySchema(clone(cfg),schemaFn);", layout)
        self.assertNotIn("let U=findChangedDataBySchema(cfg,schemaFn);", layout)

    def test_config_import_full_replace_applies_schema_normalized_values(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("let defaults=schemaFn()||{},applied=Object.assign({},defaults)", layout)
        self.assertIn(
            "for(const key in cfg)defaults.hasOwnProperty(key)||(applied[key]=cfg[key])",
            layout,
        )
        self.assertIn("Object.assign(applied,U)", layout)
        self.assertNotIn("Object.assign({},schemaFn(),cfg)", layout)

    def test_check_params_tolerates_missing_optimizer_during_schema_warmup(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('(e.optimizer_type||"").startsWith("DAdapt")', layout)
        self.assertIn('(e.optimizer_type||"").startsWith("prodigy")', layout)

    def test_patch_script_replaces_unsafe_parse_params_re_float_formatting(self):
        label, old, new = next(
            item
            for item in patch_config_import_layout.UPGRADE_REPLACEMENTS
            if item[0] == "parseParamsRe string learning rates"
        )
        original = old + 'if(e.hasOwnProperty("network_args")){}'

        patched = patch_config_import_layout._replace_once(original, label, old, new)

        self.assertNotIn("let r=e[t].toExponential()", patched)
        self.assertIn(
            'if(typeof v==="string"){const p=parseFloat(v);v=Number.isNaN(p)?v:p}',
            patched,
        )
        self.assertIn('if(typeof v!=="number"||Number.isNaN(v))continue;', patched)
        self.assertIn("let r=v.toExponential()", patched)

    def test_layout_preview_infers_enable_preview_from_legacy_fields(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('sample_prompts"].some(r=>r in e', layout)
        self.assertIn("e.enable_preview=!0", layout)
        self.assertIn("m.enable_preview=!0", layout)
        self.assertNotIn('"enable_preview","network_args_custom"', layout)

    def test_patch_script_preview_replacements_are_idempotent(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )
        repatched = layout
        for label, old, new in patch_config_import_layout.PREVIEW_PATCHES:
            repatched = patch_config_import_layout._replace_once(
                repatched, label, old, new
            )
        self.assertEqual(layout, repatched)

    def test_layout_history_row_unwrap_and_preview_pipeline(self):
        layout = Path("frontend/dist/assets/layout.96d49288.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("k.time&&!k.model_train_type", layout)
        self.assertIn("Z=async (_,m)=>{try{const cfg=m==null?null:m.value;", layout)
        self.assertIn("const prev=clone(a.value);a.value=clone(cfg);const g=x();", layout)
        self.assertIn('(e.optimizer_type||"").toLowerCase().startsWith("dada")', layout)
        self.assertIn("filter(Boolean)),e", layout)


if __name__ == "__main__":
    unittest.main()
