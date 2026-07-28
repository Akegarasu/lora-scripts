<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { parse, stringify } from "smol-toml"
import DynamicSchemaForm from "../components/DynamicSchemaForm.vue"
import { schemasApi } from "../api/schemas"
import { trainingApi, type TrainingPreset, type TrainingStart } from "../api/training"
import { cloneFormModel, createDefaultModel, serializeModel, validateModel, type AdaptedSchema, type FormField, type FormModel } from "../schema/adapter"
import { loadTrainingSchema } from "../schema/loader"
import { buildTrainingConfig, checkTrainingConfig, hydrateImportedConfig } from "../training/params"

interface HistoryRow { time: string; name?: string; value: FormModel }

const props = defineProps<{ title: string; area: string; schemaName: string }>()
const router = useRouter()
const schema = ref<AdaptedSchema>()
const model = ref<FormModel>({})
const loading = ref(true)
const error = ref("")
const errors = ref<Record<string, string>>({})
const submitting = ref(false)
const historyOpen = ref(false)
const presetsOpen = ref(false)
const history = ref<HistoryRow[]>([])
const presets = ref<TrainingPreset[]>([])
const presetsLoading = ref(false)
const started = ref<TrainingStart>()
const rawConfig = computed(() => schema.value ? serializeModel(schema.value, model.value) : {})
const output = computed(() => buildTrainingConfig(rawConfig.value, props.schemaName))
const diagnostics = computed(() => checkTrainingConfig(output.value))
const outputText = computed(() => stringify(output.value))
const filteredPresets = computed(() => presets.value.filter((item) => !item.metadata.train_type || item.metadata.train_type === props.schemaName))
const trainLogHref = computed(() => started.value ? `${started.value.train_log_path || "/train-log"}?${started.value.train_log_query || `task_id=${encodeURIComponent(started.value.task_id)}`}` : "")

function autosaveKey() { return `configs-${props.schemaName}-autosave` }
function historyKey() { return `configs-${props.schemaName}` }

function loadHistory() {
  try { history.value = JSON.parse(localStorage.getItem(historyKey()) || "[]") }
  catch { history.value = [] }
}

async function applyImportedConfig(config: FormModel, successMessage = "配置已导入") {
  const result = await trainingApi.validateImport(props.schemaName, config)
  if (result.result === "reject") throw new Error(result.errors?.join("\n") || result.message || "配置不适用于当前页面")
  if (result.result === "redirect" && result.target_path) {
    await ElMessageBox.confirm(result.message || "配置属于其他训练页面，是否跳转？", "训练类型不匹配", { confirmButtonText: "跳转并导入", cancelButtonText: "取消", type: "warning" })
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify(result.config || config))
    await router.push(result.target_path)
    return
  }
  model.value = { ...createDefaultModel(schema.value!), ...hydrateImportedConfig(result.config || config) }
  if (result.notice) ElMessage.info(result.notice)
  ElMessage.success(successMessage)
}

async function load() {
  loading.value = true
  error.value = ""
  try {
    const loaded = await loadTrainingSchema(props.schemaName)
    const defaults = createDefaultModel(loaded)
    try {
      const saved = JSON.parse(localStorage.getItem(autosaveKey()) || "null")
      model.value = saved && typeof saved === "object" ? { ...defaults, ...saved } : defaults
    } catch { model.value = defaults }
    const cards = await schemasApi.graphicCards()
    if (cards.length > 1) {
      const options = cards.map((card, index) => typeof card === "object" ? (card.value ?? card.label ?? index) : card)
      const field: FormField = { key: "gpu_ids", type: "array", role: "select", description: "选择用于训练的显卡", options, conditions: [] }
      loaded.sections.push({ id: "gpu-settings", title: "显卡设置", fields: [field] })
    }
    schema.value = loaded
    const pending = sessionStorage.getItem("mikazuki-pending-import")
    if (pending) {
      sessionStorage.removeItem("mikazuki-pending-import")
      await applyImportedConfig(JSON.parse(pending), "已在目标页面导入配置")
    }
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "Schema 加载失败" }
  finally { loading.value = false }
}

function validate() {
  if (!schema.value) return false
  errors.value = validateModel(schema.value, model.value)
  const messages = [...Object.values(errors.value), ...diagnostics.value.errors]
  if (messages.length) { ElMessage.error(messages[0]); return false }
  if (diagnostics.value.warnings.length) ElMessage.warning(diagnostics.value.warnings[0])
  else ElMessage.success("参数校验通过")
  return true
}

function saveHistory() {
  const row: HistoryRow = { time: new Date().toLocaleString(), value: cloneFormModel(model.value) }
  if (typeof model.value.output_name === "string") row.name = model.value.output_name
  history.value.push(row)
  localStorage.setItem(historyKey(), JSON.stringify(history.value))
  ElMessage.success("参数已保存到浏览器历史")
}

function deleteHistory(index: number) {
  history.value.splice(index, 1)
  localStorage.setItem(historyKey(), JSON.stringify(history.value))
}

async function openPresets() {
  presetsOpen.value = true
  if (presets.value.length) return
  presetsLoading.value = true
  try { presets.value = await trainingApi.presets() }
  catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : "预设加载失败") }
  finally { presetsLoading.value = false }
}

function applyPreset(preset: TrainingPreset) {
  model.value = { ...model.value, ...preset.data }
  presetsOpen.value = false
  ElMessage.success(`已应用预设：${preset.metadata.name}`)
}

async function importFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ""
  if (!file) return
  try {
    const text = await file.text()
    const config = file.name.toLowerCase().endsWith(".json") ? JSON.parse(text) : parse(text)
    await applyImportedConfig(config as FormModel)
  } catch (reason) {
    if (reason !== "cancel" && reason !== "close") ElMessage.error(reason instanceof Error ? reason.message : "配置导入失败")
  }
}

async function exportConfig() {
  if (!validate()) return
  try {
    const normalized = await trainingApi.normalizeExport(props.schemaName, output.value)
    const blob = new Blob([stringify(normalized.config)], { type: "application/toml;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `${String(normalized.config.output_name || props.schemaName)}.toml`
    anchor.click()
    URL.revokeObjectURL(url)
    normalized.warnings.forEach((warning) => ElMessage.warning(warning))
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : "配置导出失败") }
}

async function submit() {
  if (!validate() || submitting.value) return
  try {
    await ElMessageBox.confirm("训练将占用 GPU 并创建后台任务，确认开始？", "开始训练", { confirmButtonText: "开始训练", cancelButtonText: "取消", type: "warning" })
    submitting.value = true
    if (props.schemaName === "anima-lora-fast") {
      const preflight = await trainingApi.animaFastPreflight(output.value)
      if (!preflight.ok) throw new Error(preflight.errors?.join("\n") || "Anima Fast 预检查未通过")
      preflight.warnings?.forEach((warning) => ElMessage.warning(warning))
    }
    started.value = await trainingApi.run(output.value)
    saveHistory()
    ElMessage.success(`训练任务已启动：${started.value.task_id}`)
  } catch (reason) {
    if (reason !== "cancel" && reason !== "close") ElMessage.error(reason instanceof Error ? reason.message : "训练提交失败")
  } finally { submitting.value = false }
}

watch(() => props.schemaName, () => { started.value = undefined; loadHistory(); load() })
watch(model, (value) => localStorage.setItem(autosaveKey(), JSON.stringify(value)), { deep: true })
onMounted(() => { loadHistory(); load() })
onBeforeUnmount(() => localStorage.setItem(autosaveKey(), JSON.stringify(model.value)))
</script>

<template>
  <div class="training-layout schema-training-layout">
    <section class="form-canvas">
      <div class="section-heading"><span>{{ area }}</span><h1>{{ title }}</h1><p>依次填写模型、数据集与训练参数。提交前会执行参数转换、冲突检查和后端训练约束。</p></div>
      <div class="training-toolbar"><button @click="openPresets">训练预设</button><label>导入配置<input type="file" accept=".toml,.json" @change="importFile"></label><button @click="saveHistory">保存参数</button><button @click="historyOpen = true">历史记录</button><button @click="exportConfig">导出 TOML</button></div>
      <div v-if="loading" class="schema-state"><strong>正在加载训练 Schema</strong><span>检查缓存与后端版本…</span></div>
      <div v-else-if="error" class="schema-state schema-error"><strong>Schema 无法加载</strong><span>{{ error }}</span><button @click="load">重试</button></div>
      <DynamicSchemaForm v-else-if="schema" v-model="model" :schema="schema" :errors="errors" />
    </section>
    <aside class="control-panel">
      <div class="panel-copy"><span class="eyebrow">TRAINING CONTROL</span><h2>{{ title }}</h2><p>右侧为实际提交的 TOML。建议先校验参数，再开始后台训练任务。</p></div>
      <div v-if="diagnostics.errors.length || diagnostics.warnings.length" class="param-diagnostics"><p v-for="item in diagnostics.errors" :key="item" class="error">{{ item }}</p><p v-for="item in diagnostics.warnings" :key="item">{{ item }}</p></div>
      <div v-if="started" class="started-task"><strong>任务已启动</strong><code>{{ started.task_id }}</code><a :href="trainLogHref" target="_blank" rel="noreferrer">打开训练日志</a><RouterLink to="/task.html">查看任务页</RouterLink></div>
      <section class="preview-panel"><header><span>TOML 参数预览</span><b>{{ Object.keys(output).length }} 项</b></header><pre>{{ outputText }}</pre></section>
      <button class="secondary-action schema-validate" :disabled="!schema" @click="validate">校验当前参数</button>
      <button class="primary-action train-submit" :disabled="!schema || submitting || diagnostics.errors.length > 0" @click="submit">{{ submitting ? "提交中…" : "开始训练" }}</button>
    </aside>
  </div>

  <el-dialog v-model="historyOpen" title="历史参数" width="min(760px, 92vw)"><div class="config-list"><article v-for="(row, index) in history" :key="`${row.time}-${index}`"><div><strong>{{ row.name || '未命名配置' }}</strong><span>{{ row.time }}</span></div><button @click="model = { ...createDefaultModel(schema!), ...row.value }; historyOpen = false">使用</button><button class="danger" @click="deleteHistory(index)">删除</button></article><p v-if="!history.length">暂无历史参数</p></div></el-dialog>
  <el-dialog v-model="presetsOpen" title="训练预设" width="min(760px, 92vw)"><div v-loading="presetsLoading" class="config-list"><article v-for="preset in filteredPresets" :key="preset.metadata.name"><div><strong>{{ preset.metadata.name }}</strong><span>{{ preset.metadata.description || `${preset.metadata.author || ''} ${preset.metadata.version || ''}` }}</span></div><button @click="applyPreset(preset)">应用</button></article><p v-if="!presetsLoading && !filteredPresets.length">当前训练类型暂无预设</p></div></el-dialog>
</template>
