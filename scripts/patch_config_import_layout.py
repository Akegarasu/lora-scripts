"""Patch vendored layout bundle for cross-page config import validation (#43)."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bump_spa_asset_cache_key import bump_dist_cache_keys

LAYOUT = Path("frontend/dist/assets/layout.96d49288.js")

HELPER_MARKER = "mikazukiApplyImportedConfig=async("

HISTORY_ROW_UNWRAP = (
    'if(k&&typeof k.value==="object"&&k.time&&!k.model_train_type&&'
    "(k.value.model_train_type||k.value.pretrained_model_name_or_path))k=k.value;"
)

HELPER = (
    "mikazukiApplyImportedConfig=async(k,t,schemaFn,a,successMsg,merge,fullReplace)=>{"
    'if(!k||typeof k!=="object")throw new Error("\\u914d\\u7f6e\\u683c\\u5f0f\\u9519\\u8bef\\uff1a\\u9700\\u8981\\u5bf9\\u8c61");'
    + HISTORY_ROW_UNWRAP
    + 'const resp=await fetch("/api/config/validate-import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({page_train_type:t,config:k})});'
    'if(!resp.ok)throw new Error("\\u5bfc\\u5165\\u5931\\u8d25\\uff1a\\u7f51\\u7edc\\u9519\\u8bef");'
    "const payload=await resp.json();"
    'if(payload.status!=="success")throw new Error(payload.message||"\\u5bfc\\u5165\\u5931\\u8d25");'
    "const data=payload.data;"
    'if(data.result==="reject"){ElMessage.error((data.errors||["\\u5bfc\\u5165\\u5931\\u8d25"]).join("\\n"));return!1}'
    'if(data.result==="redirect"){try{await ElMessageBox.confirm(data.message,"\\u914d\\u7f6e\\u7c7b\\u578b\\u4e0d\\u5339\\u914d",{confirmButtonText:"\\u8df3\\u8f6c\\u5e76\\u5bfc\\u5165",cancelButtonText:"\\u53d6\\u6d88",type:"warning"});sessionStorage.setItem("mikazuki-pending-import",JSON.stringify(data.config));location.href=data.target_path;return!1}catch(e){ElMessage.info("\\u5df2\\u53d6\\u6d88\\u5bfc\\u5165");return!1}}'
    "const cfg=data.config||k;"
    "let U=findChangedDataBySchema(clone(cfg),schemaFn);"
    "if(data.forced_train_type)U.model_train_type=data.forced_train_type;"
    "if(fullReplace){let defaults=schemaFn()||{},applied=Object.assign({},defaults);for(const key in cfg)defaults.hasOwnProperty(key)||(applied[key]=cfg[key]);Object.assign(applied,U);if(data.forced_train_type)applied.model_train_type=data.forced_train_type;a.value=applied}else merge?a.value==null?a.value=clone(U):a.value=Object.assign({},a.value,U):a.value=U;"
    "if(data.notice)ElMessage.info({message:data.notice,duration:8e3});"
    'if(successMsg)ElMessage.success(successMsg);else if(data.message&&data.result==="ok")ElMessage.success(data.message);'
    "return!0}"
)

INITIAL_REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "helper anchor",
        "return l},data$1={",
        f"return l}},{HELPER},data$1={{",
    ),
    (
        "toml import",
        (
            "N.onload=D=>{const V=D.target.result;try{let k=TomlParse(V),"
            "U=findChangedDataBySchema(k,n.value);a.value=U,ElMessage.success("
            '"\\u5BFC\\u5165\\u6210\\u529F")}catch(k){console.log(k),'
            'ElMessage.error("\\u5BFC\\u5165\\u5931\\u8D25")}}'
        ),
        (
            "N.onload=async D=>{const V=D.target.result;try{let k=TomlParse(V);"
            "await mikazukiApplyImportedConfig(k,t,n.value,a,"
            '"\\u5BFC\\u5165\\u6210\\u529F")}catch(k){console.log(k),'
            'ElMessage.error(typeof k=="string"?k:k.message||"\\u5BFC\\u5165\\u5931\\u8D25")}}'
        ),
    ),
    (
        "preset merge",
        (
            "$=_=>{let m=findChangedDataBySchema(_,n.value);"
            "a.value==null?a.value=clone(m):a.value=Object.assign({},a.value,m),"
            "console.log(a.value)}"
        ),
        "$=async _=>{await mikazukiApplyImportedConfig(_,t,n.value,a,null,!0)}",
    ),
    (
        "preset apply",
        'W=_=>{$(_),p.value=!1,ElMessage.success("\\u5DF2\\u5C06\\u6A21\\u677F\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570")}',
        (
            'W=async _=>{if(await mikazukiApplyImportedConfig(_,t,n.value,a,'
            '"\\u5DF2\\u5C06\\u6A21\\u677F\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570"))p.value=!1}'
        ),
    ),
    (
        "history apply",
        (
            'Y=(_,m)=>{a.value=clone(m.value),i.value=!1,ElMessage.success('
            '"\\u5DF2\\u5C06\\u5386\\u53F2\\u53C2\\u6570\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570")}'
        ),
        (
            'Y=async (_,m)=>{if(await mikazukiApplyImportedConfig(clone(m.value),t,n.value,a,'
            '"\\u5DF2\\u5C06\\u5386\\u53F2\\u53C2\\u6570\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570"))i.value=!1}'
        ),
    ),
    (
        "pending import on mount",
        "onMounted(async()=>{I(),y()})",
        (
            "onMounted(async()=>{I();const pi=sessionStorage.getItem("
            '"mikazuki-pending-import");if(pi){sessionStorage.removeItem('
            '"mikazuki-pending-import");try{const cfg=JSON.parse(pi);'
            "await mikazukiApplyImportedConfig(cfg,t,n.value,a,"
            '"\\u5df2\\u5728\\u76ee\\u6807\\u9875\\u9762\\u5bfc\\u5165\\u914d\\u7f6e")'
            '}catch(e){console.log(e)}}y()})'
        ),
    ),
]

OLD_HELPER = (
    "mikazukiApplyImportedConfig=async(k,t,schemaFn,a,successMsg,merge,fullReplace)=>{"
    'if(!k||typeof k!=="object")throw new Error("\\u914d\\u7f6e\\u683c\\u5f0f\\u9519\\u8bef\\uff1a\\u9700\\u8981\\u5bf9\\u8c61");'
    'const resp=await fetch("/api/config/validate-import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({page_train_type:t,config:k})});'
    'if(!resp.ok)throw new Error("\\u5bfc\\u5165\\u5931\\u8d25\\uff1a\\u7f51\\u7edc\\u9519\\u8bef");'
    "const payload=await resp.json();"
    'if(payload.status!=="success")throw new Error(payload.message||"\\u5bfc\\u5165\\u5931\\u8d25");'
    "const data=payload.data;"
    'if(data.result==="reject"){ElMessage.error((data.errors||["\\u5bfc\\u5165\\u5931\\u8d25"]).join("\\n"));return!1}'
    'if(data.result==="redirect"){try{await ElMessageBox.confirm(data.message,"\\u914d\\u7f6e\\u7c7b\\u578b\\u4e0d\\u5339\\u914d",{confirmButtonText:"\\u8df3\\u8f6c\\u5e76\\u5bfc\\u5165",cancelButtonText:"\\u53d6\\u6d88",type:"warning"});sessionStorage.setItem("mikazuki-pending-import",JSON.stringify(data.config));location.href=data.target_path;return!1}catch(e){ElMessage.info("\\u5df2\\u53d6\\u6d88\\u5bfc\\u5165");return!1}}'
    "const cfg=data.config||k;"
    "let U=findChangedDataBySchema(cfg,schemaFn);"
    "if(data.forced_train_type)U.model_train_type=data.forced_train_type;"
    "if(fullReplace){let applied=Object.assign({},schemaFn(),cfg);if(data.forced_train_type)applied.model_train_type=data.forced_train_type;a.value=applied}else merge?a.value==null?a.value=clone(U):a.value=Object.assign({},a.value,U):a.value=U;"
    "if(data.notice)ElMessage.info({message:data.notice,duration:8e3});"
    'if(successMsg)ElMessage.success(successMsg);else if(data.message&&data.result==="ok")ElMessage.success(data.message);'
    "return!0}"
)

UPGRADE_REPLACEMENTS: list[tuple[str, str, str]] = [
    (
        "config import clones validation input",
        "let U=findChangedDataBySchema(cfg,schemaFn);",
        "let U=findChangedDataBySchema(clone(cfg),schemaFn);",
    ),
    (
        "config import full replace keeps validated fields during schema warmup",
        "if(fullReplace){let applied=Object.assign({},schemaFn(),U);",
        "if(fullReplace){let defaults=schemaFn()||{},applied=Object.assign({},defaults);for(const key in cfg)defaults.hasOwnProperty(key)||(applied[key]=cfg[key]);Object.assign(applied,U);",
    ),
    (
        "file import accept json + full replace",
        '_.accept=".toml",_.onchange=m=>{const g=m.target.files[0],N=new FileReader;N.onload=async D=>{const V=D.target.result;try{let k=TomlParse(V);await mikazukiApplyImportedConfig(k,t,n.value,a,"\\u5BFC\\u5165\\u6210\\u529F")',
        '_.accept=".toml,.json",_.onchange=m=>{const g=m.target.files[0],N=new FileReader;N.onload=async D=>{const V=D.target.result;try{let k=g.name.toLowerCase().endsWith(".json")?JSON.parse(V):TomlParse(V);await mikazukiApplyImportedConfig(k,t,n.value,a,"\\u5BFC\\u5165\\u6210\\u529F",!1,!0)',
    ),
    (
        "history apply full replace",
        'Y=async (_,m)=>{if(await mikazukiApplyImportedConfig(clone(m.value),t,n.value,a,"\\u5DF2\\u5C06\\u5386\\u53F2\\u53C2\\u6570\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570"))i.value=!1}',
        (
            'Y=async (_,m)=>{try{const cfg=m==null?null:m.value;if(!cfg||typeof cfg!="object"){ElMessage.error("\\u5386\\u53f2\\u8bb0\\u5f55\\u7f3a\\u5c11\\u6709\\u6548\\u914d\\u7f6e\\uff08\\u9700\\u8981 value \\u5b57\\u6bb5\\uff09");return}'
            'if(await mikazukiApplyImportedConfig(clone(cfg),t,n.value,a,"\\u5DF2\\u5C06\\u5386\\u53F2\\u53C2\\u6570\\u5E94\\u7528\\u81F3\\u5F53\\u524D\\u53C2\\u6570",!1,!0))i.value=!1}'
            'catch(e){console.log(e);ElMessage.error(e.message||"\\u5e94\\u7528\\u5386\\u53f2\\u53c2\\u6570\\u5931\\u8d25")}}'
        ),
    ),
    (
        "history json import single object",
        're=()=>{const _=document.createElement("input");_.type="file",_.accept=".json",_.onchange=m=>{const g=m.target.files[0],N=new FileReader;N.onload=D=>{const V=D.target.result;try{const k=JSON.parse(V);k instanceof Array?(l.value=[...l.value,...k],A(),ElMessage.success("\\u5BFC\\u5165\\u6210\\u529F")):ElMessage.error("\\u5BFC\\u5165\\u5931\\u8D25\\uFF1A\\u6587\\u4EF6\\u683C\\u5F0F\\u9519\\u8BEF")}catch{ElMessage.error("\\u5BFC\\u5165\\u5931\\u8D25\\uFF1A\\u6587\\u4EF6\\u683C\\u5F0F\\u9519\\u8BEF")}},N.readAsText(g)},_.click()}',
        (
            're=()=>{const _=document.createElement("input");_.type="file",_.accept=".json",_.onchange=m=>{const g=m.target.files[0],N=new FileReader;N.onload=async D=>{const V=D.target.result;try{const k=JSON.parse(V);if(k instanceof Array){l.value=[...l.value,...k],A(),ElMessage.success("\\u5df2\\u5bfc\\u5165 "+k.length+" \\u6761\\u5386\\u53f2\\u8bb0\\u5f55")}'
            'else if(k&&typeof k=="object"){if(await mikazukiApplyImportedConfig(k,t,n.value,a,"\\u5BFC\\u5165\\u6210\\u529F",!1,!0))i.value=!1}'
            'else ElMessage.error("\\u5BFC\\u5165\\u5931\\u8D25\\uFF1A\\u9700\\u8981\\u5386\\u53f2\\u8bb0\\u5f55\\u6570\\u7ec4\\u6216\\u5355\\u4e2a\\u914d\\u7f6e\\u5bf9\\u8c61")}'
            'catch(e){console.log(e);ElMessage.error(e.message||"\\u5BFC\\u5165\\u5931\\u8D25\\uFF1A\\u6587\\u4EF6\\u683C\\u5F0F\\u9519\\u8BEF")}},N.readAsText(g)},_.click()}'
        ),
    ),
    (
        "pending import full replace",
        'await mikazukiApplyImportedConfig(cfg,t,n.value,a,"\\u5df2\\u5728\\u76ee\\u6807\\u9875\\u9762\\u5bfc\\u5165\\u914d\\u7f6e")',
        'await mikazukiApplyImportedConfig(cfg,t,n.value,a,"\\u5df2\\u5728\\u76ee\\u6807\\u9875\\u9762\\u5bfc\\u5165\\u914d\\u7f6e",!1,!0)',
    ),
    (
        "parseParamsRe string learning rates",
        (
            "parseParamsRe=e=>{for(const t of floatParmas){if(!e.hasOwnProperty(t))continue;"
            "let r=e[t].toExponential();r.length<=6?e[t]=r:e[t]=e[t].toString()}"
        ),
        (
            "parseParamsRe=e=>{for(const t of floatParmas){if(!e.hasOwnProperty(t))continue;"
            'let v=e[t];if(typeof v==="string"){const p=parseFloat(v);v=Number.isNaN(p)?v:p}'
            'if(typeof v!=="number"||Number.isNaN(v))continue;'
            "let r=v.toExponential();r.length<=6?e[t]=r:e[t]=v.toString()}"
        ),
    ),
    (
        "import notice toast",
        "if(successMsg)ElMessage.success(successMsg);return!0}",
        'if(data.notice)ElMessage.info({message:data.notice,duration:8e3});if(successMsg)ElMessage.success(successMsg);else if(data.message&&data.result==="ok")ElMessage.success(data.message);return!0}',
    ),
    (
        "history row unwrap",
        'if(!k||typeof k!=="object")throw new Error("\\u914d\\u7f6e\\u683c\\u5f0f\\u9519\\u8bef\\uff1a\\u9700\\u8981\\u5bf9\\u8c61");const resp=await fetch("/api/config/validate-import"',
        'if(!k||typeof k!=="object")throw new Error("\\u914d\\u7f6e\\u683c\\u5f0f\\u9519\\u8bef\\uff1a\\u9700\\u8981\\u5bf9\\u8c61");'
        + HISTORY_ROW_UNWRAP
        + 'const resp=await fetch("/api/config/validate-import"',
    ),
    (
        "history preview uses main preview pipeline",
        'Z=(_,m)=>{const g=stringify(parseParams(n.value(clone(m.value)),t));ElMessageBox.alert(g,"\\u9884\\u89C8",{confirmButtonText:"\\u786E\\u5B9A",customStyle:{whiteSpace:"pre-line"}})}',
        (
            'Z=async (_,m)=>{try{const cfg=m==null?null:m.value;if(!cfg||typeof cfg!="object"){ElMessage.error("\\u5386\\u53f2\\u8bb0\\u5f55\\u7f3a\\u5c11\\u6709\\u6548\\u914d\\u7f6e");return}'
            "const prev=clone(a.value);a.value=clone(cfg);const g=x();a.value=prev;"
            'ElMessageBox.alert(g,"\\u9884\\u89C8",{confirmButtonText:"\\u786E\\u5B9A",customStyle:{whiteSpace:"pre-line"}})'
            '}catch(e){console.log(e);ElMessage.error(e.message||"\\u9884\\u89c8\\u5931\\u8d25")}}'
        ),
    ),
    (
        "parseParams safe optimizer_type dada",
        'e.optimizer_type.toLowerCase().startsWith("dada")',
        '(e.optimizer_type||"").toLowerCase().startsWith("dada")',
    ),
    (
        "parseParams safe optimizer_type prodigy",
        'e.optimizer_type.toLowerCase()=="prodigy"',
        '(e.optimizer_type||"").toLowerCase()=="prodigy"',
    ),
    (
        "parseParams safe gpu_ids",
        "return e.gpu_ids&&(e.gpu_ids=e.gpu_ids.map(r=>r.match(/GPU (\\d+):/)[1])),e",
        'return e.gpu_ids&&(e.gpu_ids=e.gpu_ids.map(r=>{if(r==null)return"";if(typeof r==="number"||/^\\d+$/.test(String(r)))return String(r);const m=String(r).match(/GPU (\\d+):/);return m?m[1]:String(r)}).filter(Boolean)),e',
    ),
]

PREVIEW_SIGNAL_KEYS = (
    '["prompt_file","sample_width","sample_height","sample_cfg","sample_seed","sample_steps",'
    '"sample_sampler","randomly_choice_prompt","sample_at_first","sample_every_n_epochs",'
    '"sample_every_n_steps","positive_prompts","negative_prompts","sample_prompts"]'
)

PREVIEW_SIGNAL_GUARD_E = (
    f"{PREVIEW_SIGNAL_KEYS}.some(r=>r in e&&e[r]!==\"\"&&e[r]!=null&&e[r]!==undefined"
    "&&(!Array.isArray(e[r])||e[r].length))"
)

PREVIEW_SIGNAL_GUARD_RAW = (
    f"{PREVIEW_SIGNAL_KEYS}.some(r=>r in _&&_[r]!==\"\"&&_[r]!=null&&_[r]!==undefined"
    "&&(!Array.isArray(_[r])||_[r].length))"
)

PREVIEW_PATCHES: list[tuple[str, str, str]] = [
    (
        "checkParams safe optimizer_type DAdapt",
        'e.optimizer_type.startsWith("DAdapt")',
        '(e.optimizer_type||"").startsWith("DAdapt")',
    ),
    (
        "checkParams safe optimizer_type prodigy",
        'e.optimizer_type.startsWith("prodigy")',
        '(e.optimizer_type||"").startsWith("prodigy")',
    ),
    (
        "needDeleteParams drop enable_preview",
        '"enable_block_weights","enable_preview","network_args_custom"',
        '"enable_block_weights","network_args_custom"',
    ),
    (
        "parseParams safe network_args spread",
        "e.network_args=[...e.network_args,...e.network_args_custom]",
        "e.network_args=[...(e.network_args||[]),...e.network_args_custom]",
    ),
    (
        "parseParams safe optimizer_args spread",
        "e.optimizer_args=[...e.optimizer_args,...e.optimizer_args_custom]",
        "e.optimizer_args=[...(e.optimizer_args||[]),...e.optimizer_args_custom]",
    ),
    (
        "parseParams infer enable_preview from legacy preview fields",
        "e.optimizer_args=[...(e.optimizer_args||[]),...e.optimizer_args_custom]),e.enable_preview||(delete e.sample_prompts,delete e.sample_sampler,delete e.sample_every_n_epochs)",
        f"e.optimizer_args=[...(e.optimizer_args||[]),...e.optimizer_args_custom]),({PREVIEW_SIGNAL_GUARD_E})&&(e.enable_preview=!0),e.enable_preview||(delete e.sample_prompts,delete e.sample_sampler,delete e.sample_every_n_epochs)",
    ),
    (
        "T() preview schema backfill",
        "T=()=>{let _=a.value;w.forEach(g=>{_&&_.hasOwnProperty(g)&&_[g]!=null&&(_[g]=_[g].map(N=>N||\"\"))});let m=n.value(_);return w.forEach(g=>{m.hasOwnProperty(g)&&m[g].length==0&&delete m[g]}),m}",
        (
            "T=()=>{let _=clone(a.value);w.forEach(g=>{_&&_.hasOwnProperty(g)&&_[g]!=null&&"
            "(_[g]=Array.isArray(_[g])?_[g].map(N=>N||\"\"):String(_[g]).split(/\\r?\\n/).filter(N=>N))});"
            "let m=n.value(_);w.forEach(g=>{Array.isArray(m[g])&&m[g].length==0&&delete m[g]});"
            f"if(_){{const b={PREVIEW_SIGNAL_KEYS},h={PREVIEW_SIGNAL_GUARD_RAW};"
            "(_.enable_preview===!0||_.enable_preview===\"true\"||_.enable_preview===1||h)&&"
            "(m.enable_preview=!0);if(m.enable_preview)for(const r of b)r in _&&m[r]===undefined&&(m[r]=_[r])}"
            "return m}"
        ),
    ),
]

SUBMIT_FEEDBACK_PATCHES: list[tuple[str, str, str]] = [
    (
        "declare train submit notice handle",
        "submitLoading=ref(!1),setSubmitButtonLoading=",
        "submitLoading=ref(!1),submitNotice=ref(null),setSubmitButtonLoading=",
    ),
    (
        "persistent train submit notice",
        'ElMessage.info({message:"正在提交训练任务...",duration:2e3});try{',
        '0;try{submitNotice.value=ElMessage({message:"任务正在提交中，请稍等",duration:0,type:"info"});',
    ),
    (
        "train started notice",
        'g.status=="success"?ElMessage.success("\\u8BAD\\u7EC3\\u4EFB\\u52A1\\u5DF2\\u63D0\\u4EA4\\u6210\\u529F\\uFF1A"+g.message):ElMessage.error("\\u8BAD\\u7EC3\\u4EFB\\u52A1\\u63D0\\u4EA4\\u5931\\u8D25\\uFF1A"+g.message)',
        'g.status=="success"?ElMessage.success("训练已开始"):ElMessage.error("\\u8BAD\\u7EC3\\u4EFB\\u52A1\\u63D0\\u4EA4\\u5931\\u8D25\\uFF1A"+g.message)',
    ),
    (
        "train submit finally closes notice",
        '}finally{submitLoading.value=!1,setSubmitButtonLoading(!1)}',
        '}finally{submitNotice.value&&submitNotice.value.close(),submitNotice.value=null,submitLoading.value=!1,setSubmitButtonLoading(!1)}',
    ),
]


def _replace_once(text: str, label: str, old: str, new: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = LAYOUT.read_text(encoding="utf-8")
    # Repair previously generated submit-feedback variants before applying rules.
    text = text.replace(
        "const submitNotice=ElMessage(",
        "submitNotice=ElMessage(",
        1,
    )
    text = text.replace(
        "submitLoading=ref(!1),submitNotice=null,setSubmitButtonLoading=",
        "submitLoading=ref(!1),submitNotice=ref(null),setSubmitButtonLoading=",
        1,
    )
    text = text.replace(
        'submitNotice=ElMessage({message:"任务正在提交中，请稍等",duration:0,type:"info"});try{',
        'try{submitNotice.value=ElMessage({message:"任务正在提交中，请稍等",duration:0,type:"info"});',
        1,
    )
    text = text.replace(
        ',try{submitNotice.value=ElMessage(',
        ',0;try{submitNotice.value=ElMessage(',
        1,
    )
    text = text.replace(
        'g.status=="success"?(submitNotice.close(),ElMessage.success("训练已开始")):(submitNotice.close(),ElMessage.error("\\u8BAD\\u7EC3\\u4EFB\\u52A1\\u63D0\\u4EA4\\u5931\\u8D25\\uFF1A"+g.message))',
        'g.status=="success"?ElMessage.success("训练已开始"):ElMessage.error("\\u8BAD\\u7EC3\\u4EFB\\u52A1\\u63D0\\u4EA4\\u5931\\u8D25\\uFF1A"+g.message)',
        1,
    )
    text = text.replace(
        '}catch(m){submitNotice.close(),ElMessage.error(v("networkError")),console.error("There was a problem with the fetch operation:",m)}',
        '}catch(m){ElMessage.error(v("networkError")),console.error("There was a problem with the fetch operation:",m)}',
        1,
    )
    text = text.replace(
        '}finally{submitNotice.close(),submitLoading.value=!1,setSubmitButtonLoading(!1)}',
        '}finally{submitNotice.value&&submitNotice.value.close(),submitNotice.value=null,submitLoading.value=!1,setSubmitButtonLoading(!1)}',
        1,
    )
    already = HELPER_MARKER in text

    if not already:
        for label, old, new in INITIAL_REPLACEMENTS:
            text = _replace_once(text, label, old, new)
    else:
        for label, old, new in UPGRADE_REPLACEMENTS:
            text = _replace_once(text, label, old, new)

    for label, old, new in PREVIEW_PATCHES:
        text = _replace_once(text, label, old, new)

    for label, old, new in SUBMIT_FEEDBACK_PATCHES:
        text = _replace_once(text, label, old, new)

    LAYOUT.write_text(text, encoding="utf-8")
    print("patched", LAYOUT, "(upgrade)" if already else "(initial)")

    bumped = bump_dist_cache_keys()
    print(f"bumped SPA cache key in {bumped} dist file(s)")


if __name__ == "__main__":
    main()
