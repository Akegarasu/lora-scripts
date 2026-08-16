<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  Clock,
  EditPen,
  FolderOpened,
  MagicStick,
  Picture,
  Refresh,
  Setting,
  VideoPlay,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import type {
  CaptionConflictPolicy,
  CaptionJobCreateRequest,
  CaptionJobState,
  CaptionModelSummary,
  CaptionOutputMode,
} from '@/api/types'
import FilePicker from '@/components/FilePicker.vue'
import { useCaptionStore } from '@/stores/caption'

import CaptionDatasetPanel from './components/CaptionDatasetPanel.vue'
import CaptionJobPanel from './components/CaptionJobPanel.vue'
import CaptionParamControl from './components/CaptionParamControl.vue'

const DRAFT_KEY = 'lora-studio-caption-draft-v2'
const LEGACY_DRAFT_KEY = 'lora-studio-caption-draft-v1'

interface CaptionWorkbenchDraft {
  path: string
  recursive: boolean
  captionExtension: string
  maxImages: number
  modelId: string
  outputMode: CaptionOutputMode
  params: Record<string, unknown>
  instruction: string
  language: string
  additionalTags: string
  excludeTags: string
  prefix: string
  suffix: string
  separator: string
  deduplicate: boolean
  replaceUnderscore: boolean
  replaceUnderscoreExcludes: string
  escapeTags: boolean
  includeConfidence: boolean
  stageBeforeWrite: boolean
  conflictPolicy: CaptionConflictPolicy
  backupExisting: boolean
  saveRawResult: boolean
  device: 'auto' | 'cpu' | 'cuda'
  dtype: 'auto' | 'float32' | 'float16' | 'bfloat16'
  batchSize: number
  scope: 'all' | 'selected'
  name: string
}

const DEFAULT_DRAFT: CaptionWorkbenchDraft = {
  path: '',
  recursive: true,
  captionExtension: '.txt',
  maxImages: 10_000,
  modelId: '',
  outputMode: 'tags',
  params: {},
  instruction: 'Describe this image accurately for image-generation training.',
  language: 'en',
  additionalTags: '',
  excludeTags: '',
  prefix: '',
  suffix: '',
  separator: ', ',
  deduplicate: true,
  replaceUnderscore: true,
  replaceUnderscoreExcludes: '',
  escapeTags: false,
  includeConfidence: false,
  stageBeforeWrite: false,
  conflictPolicy: 'skip',
  backupExisting: true,
  saveRawResult: false,
  device: 'auto',
  dtype: 'auto',
  batchSize: 1,
  scope: 'all',
  name: '',
}

const caption = useCaptionStore()
const route = useRoute()
const router = useRouter()
const draft = reactive<CaptionWorkbenchDraft>(loadDraft())
const pickerVisible = ref(false)
const selectedIds = ref<string[]>([])
const advancedVisible = ref(false)
const lastScanKey = ref('')
const paramsByModel = ref<Record<string, Record<string, unknown>>>({})
let previousModelId = ''
let jobsTimer: number | undefined

const routeJobId = computed(() => {
  const value = route.params.id
  return Array.isArray(value) ? value[0] || '' : value || ''
})
const showingJob = computed(() => route.path.startsWith('/caption/jobs/') && !!routeJobId.value)
const selectedModel = computed(() => caption.models.find((model) => model.id === draft.modelId) || null)
const modelReady = computed(
  () => selectedModel.value && !['unavailable', 'misconfigured'].includes(selectedModel.value.status),
)
const modelGroups = computed(() => {
  const groups = new Map<string, CaptionModelSummary[]>()
  for (const model of caption.models) {
    const label = familyLabel(model.family)
    const items = groups.get(label) || []
    items.push(model)
    groups.set(label, items)
  }
  return [...groups.entries()].map(([label, models]) => ({ label, models }))
})
const regularParamGroups = computed(() =>
  (selectedModel.value?.paramGroups || [])
    .map((group) => ({ ...group, params: group.params.filter((param) => !param.advanced) }))
    .filter((group) => group.params.length > 0),
)
const advancedParamGroups = computed(() =>
  (selectedModel.value?.paramGroups || [])
    .map((group) => ({ ...group, params: group.params.filter((param) => param.advanced) }))
    .filter((group) => group.params.length > 0),
)
const hasPromptPreset = computed(() =>
  (selectedModel.value?.paramGroups || []).some((group) =>
    group.params.some((param) => param.name === 'promptPreset'),
  ),
)
const customInstructionEnabled = computed(
  () => !hasPromptPreset.value || draft.params.promptPreset === 'custom',
)
const scanKey = computed(() =>
  JSON.stringify([draft.path.trim(), draft.recursive, draft.captionExtension.trim(), draft.maxImages]),
)
const scanOutdated = computed(() => !!caption.dataset && lastScanKey.value !== scanKey.value)
const selectionEnabled = computed({
  get: () => draft.scope === 'selected',
  set: (enabled: boolean) => {
    draft.scope = enabled ? 'selected' : 'all'
  },
})
const canStart = computed(
  () =>
    !!caption.dataset &&
    !scanOutdated.value &&
    !!selectedModel.value &&
    !!modelReady.value &&
    !caption.starting &&
    (draft.scope === 'all' || selectedIds.value.length > 0),
)
const history = computed(() => caption.jobs.slice(0, 16))

watch(
  draft,
  (value) => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(value))
    } catch {
      /* localStorage may be unavailable in restricted browser contexts */
    }
  },
  { deep: true },
)

watch(
  () => draft.modelId,
  (modelId) => {
    if (previousModelId) paramsByModel.value[previousModelId] = { ...draft.params }
    const model = caption.models.find((item) => item.id === modelId)
    if (!model) return
    previousModelId = modelId
    draft.params = normalizeModelParams(model, paramsByModel.value[modelId] || {})
    if (!model.outputModes.includes(draft.outputMode)) draft.outputMode = model.defaultOutputMode
    if (!model.capabilities.languages.includes(draft.language)) {
      draft.language = model.capabilities.languages[0] || 'en'
    }
    if (draft.device !== 'auto' && !model.capabilities.devices.includes(draft.device)) {
      draft.device = 'auto'
    }
    if (!model.capabilities.batch) draft.batchSize = 1
  },
)

watch(routeJobId, (jobId) => {
  if (showingJob.value && jobId) void caption.selectJob(jobId)
  else {
    caption.stopObservation('idle')
    caption.currentJobId = ''
    caption.currentJob = null
  }
})

onMounted(async () => {
  await Promise.all([caption.loadModels(), caption.loadJobs()])
  const savedModelExists = caption.models.some((model) => model.id === draft.modelId)
  if (!savedModelExists) {
    draft.params = {}
    draft.modelId = caption.defaultModelId || caption.models[0]?.id || ''
  }
  const initialModel = caption.models.find((model) => model.id === draft.modelId)
  if (initialModel) {
    draft.params = normalizeModelParams(initialModel, draft.params)
    if (!initialModel.outputModes.includes(draft.outputMode)) {
      draft.outputMode = initialModel.defaultOutputMode
    }
    if (!initialModel.capabilities.languages.includes(draft.language)) {
      draft.language = initialModel.capabilities.languages[0] || 'en'
    }
    if (
      draft.device !== 'auto' &&
      !initialModel.capabilities.devices.includes(draft.device)
    ) {
      draft.device = 'auto'
    }
    if (!initialModel.capabilities.batch) draft.batchSize = 1
  }
  previousModelId = draft.modelId
  if (showingJob.value && routeJobId.value) await caption.selectJob(routeJobId.value)
  jobsTimer = window.setInterval(() => void caption.loadJobs({ silent: true }), 10_000)
})

onBeforeUnmount(() => {
  caption.stopObservation('idle')
  if (jobsTimer !== undefined) window.clearInterval(jobsTimer)
})

function loadDraft(): CaptionWorkbenchDraft {
  try {
    const current = localStorage.getItem(DRAFT_KEY)
    const raw = current || localStorage.getItem(LEGACY_DRAFT_KEY)
    if (!raw) return { ...DEFAULT_DRAFT }
    const stored = JSON.parse(raw) as Partial<CaptionWorkbenchDraft>
    const migrated = current
      ? stored
      : { ...stored, stageBeforeWrite: false, scope: 'all' as const }
    return {
      ...DEFAULT_DRAFT,
      ...migrated,
      params: migrated.params && typeof migrated.params === 'object' ? migrated.params : {},
    }
  } catch {
    return { ...DEFAULT_DRAFT }
  }
}

function normalizeModelParams(
  model: CaptionModelSummary,
  values: Record<string, unknown>,
): Record<string, unknown> {
  const definitions = model.paramGroups.flatMap((group) => group.params)
  const allowed = new Set(definitions.map((param) => param.name))
  const defaults = Object.fromEntries(definitions.map((param) => [param.name, param.default]))
  const remembered = Object.fromEntries(
    Object.entries(values).filter(([name]) => allowed.has(name)),
  )
  return { ...defaults, ...remembered }
}

function familyLabel(family: string) {
  const labels: Record<string, string> = {
    'wd-tagger': 'WD 动漫标签器',
    'cl-tagger': 'CL 多分类标签器',
    blip: 'BLIP 自然语言描述',
    blip2: 'BLIP-2 多模态模型',
    git: 'GIT 图像描述',
    'deep-danbooru': 'DeepDanbooru 标签器',
    smolvlm2: 'SmolVLM 轻量多模态模型',
    'qwen2.5-vl': 'Qwen2.5-VL 多模态模型',
    joycaption: 'JoyCaption 训练描述模型',
    'qwen2-vl': 'Qwen2-VL 动漫描述模型',
    'llava-onevision': 'LLaVA-OneVision 多模态模型',
    'qwen3-vl': 'Qwen3-VL 多模态模型',
  }
  return labels[family] || family
}

function providerLabel(provider: CaptionModelSummary['provider']) {
  if (provider === 'local-onnx') return '本地 ONNX'
  if (provider === 'local-transformers') return '本地 Transformers'
  return '远程服务'
}

function engineLabel(engine: string) {
  const labels: Record<string, string> = {
    classifier_tagger: '标签分类引擎',
    legacy_image_to_text: '经典图像描述引擎',
    chat_vlm: '对话式多模态引擎',
  }
  return labels[engine] || engine
}

function statusLabel(model: CaptionModelSummary) {
  if (model.status === 'ready') return '已就绪'
  if (model.status === 'downloadable') return '首次使用时下载'
  if (model.status === 'misconfigured') return '配置不完整'
  return '当前不可用'
}

function statusType(model: CaptionModelSummary) {
  if (model.status === 'ready') return 'success'
  if (model.status === 'downloadable') return 'warning'
  return 'danger'
}

function outputModeLabel(mode: CaptionOutputMode) {
  if (mode === 'tags') return '逗号标签'
  if (mode === 'caption') return '自然语言描述'
  return '描述与标签'
}

function languageLabel(language: string) {
  const labels: Record<string, string> = {
    en: '英语',
    zh: '中文',
    ja: '日语',
    booru: 'Danbooru 标签语汇',
  }
  return labels[language] || language
}

function jobStateLabel(state: CaptionJobState) {
  const labels: Record<CaptionJobState, string> = {
    created: '已创建',
    queued: '排队中',
    running: '运行中',
    loading: '加载模型',
    generating: '生成中',
    awaiting_review: '等待复核',
    committing: '写入中',
    succeeded: '已完成',
    partial: '部分完成',
    failed: '失败',
    canceling: '正在取消',
    canceled: '已取消',
    interrupted: '已中断',
  }
  return labels[state]
}

function jobStateType(state: CaptionJobState) {
  if (state === 'succeeded') return 'success'
  if (['failed', 'canceled', 'interrupted'].includes(state)) return 'danger'
  if (['awaiting_review', 'partial'].includes(state)) return 'warning'
  return 'primary'
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function updateParam(name: string, value: unknown) {
  draft.params[name] = value
}

function splitTags(value: string) {
  return value
    .split(/[,\n]/u)
    .map((item) => item.trim())
    .filter(Boolean)
}

async function inspectDataset() {
  if (!draft.path.trim()) {
    ElMessage.warning('请先选择图片目录')
    return
  }
  const response = await caption.inspectDataset({
    root: 'train',
    path: draft.path.trim(),
    recursive: draft.recursive,
    captionExtension: draft.captionExtension,
    maxImages: draft.maxImages,
    initialLimit: caption.datasetLimit,
  })
  if (!response) return
  lastScanKey.value = scanKey.value
  selectedIds.value = []
  draft.scope = 'all'
  ElMessage.success(`已扫描 ${response.dataset.total} 张图片`)
}

async function startJob() {
  if (!caption.dataset || !selectedModel.value) return
  if (scanOutdated.value) {
    ElMessage.warning('数据源设置已经变化，请重新扫描')
    return
  }
  if (draft.scope === 'selected' && selectedIds.value.length === 0) {
    ElMessage.warning('请至少选择一张可处理图片')
    return
  }
  const startWarnings: string[] = []
  if (selectedModel.value.status === 'downloadable') {
    const vram = selectedModel.value.recommendedVramGb
      ? `建议至少准备约 ${selectedModel.value.recommendedVramGb} GB 显存。`
      : ''
    startWarnings.push(
      `“${selectedModel.value.title}”尚未缓存，首次任务会从模型仓库下载权重，耗时和磁盘占用取决于模型体积。${vram}`,
    )
  }
  if (
    !draft.stageBeforeWrite &&
    ['overwrite', 'prepend', 'append'].includes(draft.conflictPolicy)
  ) {
    startWarnings.push('当前策略会修改已有 Caption 内容。')
  }
  if (!draft.stageBeforeWrite && !draft.backupExisting) {
    startWarnings.push('直接写入时不会为已有文件创建备份。')
  }
  if (startWarnings.length) {
    try {
      await ElMessageBox.confirm(
        startWarnings.join('\n'),
        selectedModel.value.status === 'downloadable' ? '确认首次下载与写入策略' : '确认写入策略',
        { confirmButtonText: '继续创建任务', cancelButtonText: '返回检查', type: 'warning' },
      )
    } catch {
      return
    }
  }

  const request: CaptionJobCreateRequest = {
    name: draft.name.trim() || undefined,
    datasetId: caption.dataset.id,
    itemIds: draft.scope === 'selected' ? selectedIds.value : undefined,
    modelId: selectedModel.value.id,
    outputMode: draft.outputMode,
    params: { ...draft.params },
    prompt: {
      instruction: draft.instruction,
      language: draft.language,
    },
    postprocess: {
      additionalTags: splitTags(draft.additionalTags),
      excludeTags: splitTags(draft.excludeTags),
      prefix: draft.prefix,
      suffix: draft.suffix,
      separator: draft.separator,
      deduplicate: draft.deduplicate,
      replaceUnderscore: draft.replaceUnderscore,
      replaceUnderscoreExcludes: splitTags(draft.replaceUnderscoreExcludes),
      escapeTags: draft.escapeTags,
      includeConfidence: draft.includeConfidence,
    },
    output: {
      stageBeforeWrite: draft.stageBeforeWrite,
      conflictPolicy: draft.conflictPolicy,
      backupExisting: draft.backupExisting,
      saveRawResult: draft.saveRawResult,
    },
    runtime: {
      device: draft.device,
      dtype: draft.dtype,
      batchSize: draft.batchSize,
      keepModelLoaded: false,
    },
  }
  const job = await caption.createJob(request)
  if (!job) return
  await caption.loadJobs({ silent: true })
  ElMessage.success('Caption 任务已创建')
  await router.push(`/caption/jobs/${encodeURIComponent(job.id)}`)
}

function openHistoryJob(jobId: string) {
  void router.push(`/caption/jobs/${encodeURIComponent(jobId)}`)
}
</script>

<template>
  <CaptionJobPanel v-if="showingJob" />

  <section v-else class="caption-page" aria-labelledby="caption-title">
    <header class="page-header">
      <div class="page-heading">
        <h1 id="caption-title">Caption 工作台</h1>
      </div>
      <div class="header-actions">
        <el-button text :icon="EditPen" @click="router.push('/tag-editor')">
          人工编辑
        </el-button>
        <el-button text :icon="Refresh" :loading="caption.modelsLoading" @click="caption.loadModels()">
          刷新模型
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="caption.modelsError"
      type="error"
      :title="caption.modelsError"
      description="模型目录加载失败，暂时无法创建 Caption 任务。"
      :closable="false"
      show-icon
    />

    <div class="workbench-layout">
      <main class="configuration-flow">
        <section class="config-section" aria-labelledby="source-title">
          <div class="section-heading">
            <div>
              <h2 id="source-title">选择并检查数据集</h2>
              <p>扫描只读取图片和同名 Caption，不会修改任何文件。</p>
            </div>
          </div>

          <div class="source-form">
            <label class="field field-wide">
              <span class="field-label">图片目录 <em>必填</em></span>
              <el-input v-model="draft.path" clearable placeholder="train 目录中的图片文件夹">
                <template #append>
                  <el-button :icon="FolderOpened" @click="pickerVisible = true">浏览</el-button>
                </template>
              </el-input>
              <small>出于安全考虑，目录必须位于项目的 train 根目录中。</small>
            </label>

            <label class="field">
              <span class="field-label">Caption 后缀</span>
              <el-select v-model="draft.captionExtension">
                <el-option label=".txt（训练常用）" value=".txt" />
                <el-option label=".caption" value=".caption" />
                <el-option label=".tags" value=".tags" />
              </el-select>
              <small>读取和写入与图片同名的描述文件。</small>
            </label>

            <label class="option-card">
              <span>
                <strong>扫描子文件夹</strong>
                <small>递归处理目录中的分组数据集；隐藏目录和符号链接会跳过。</small>
              </span>
              <el-switch v-model="draft.recursive" />
            </label>

            <label class="field">
              <span class="field-label">扫描图片上限</span>
              <el-input-number
                v-model="draft.maxImages"
                :min="1"
                :max="50000"
                :step="1000"
                controls-position="right"
              />
              <small>超大型数据集建议拆分任务，便于复核和恢复。</small>
            </label>

            <div class="scan-action">
              <el-button
                type="primary"
                :icon="Picture"
                :loading="caption.datasetLoading"
                :disabled="!draft.path.trim()"
                @click="inspectDataset"
              >
                扫描数据集
              </el-button>
              <span v-if="scanOutdated" class="outdated-warning">
                <el-icon><WarningFilled /></el-icon>
                设置已变化，请重新扫描
              </span>
            </div>
          </div>

          <CaptionDatasetPanel
            v-model:selected-ids="selectedIds"
            v-model:selection-enabled="selectionEnabled"
          />
        </section>

        <section class="config-section" aria-labelledby="model-title">
          <div class="section-heading">
            <div>
              <h2 id="model-title">选择识别模型</h2>
            </div>
          </div>

          <div class="model-picker-grid">
            <label class="field field-wide">
              <span class="field-label">模型</span>
              <el-select
                v-model="draft.modelId"
                filterable
                :loading="caption.modelsLoading"
                placeholder="选择 Caption 模型"
              >
                <el-option-group v-for="group in modelGroups" :key="group.label" :label="group.label">
                  <el-option
                    v-for="model in group.models"
                    :key="model.id"
                    :label="`${model.title} · ${statusLabel(model)}`"
                    :value="model.id"
                    :disabled="model.status === 'unavailable' || model.status === 'misconfigured'"
                  />
                </el-option-group>
              </el-select>
            </label>

            <article v-if="selectedModel" class="model-summary">
              <div class="model-summary-heading">
                <div>
                  <span>{{ familyLabel(selectedModel.family) }}</span>
                  <h3>{{ selectedModel.title }}</h3>
                </div>
                <el-tag :type="statusType(selectedModel)">{{ statusLabel(selectedModel) }}</el-tag>
              </div>
              <p>{{ selectedModel.description }}</p>
              <div class="model-facts">
                <span>{{ providerLabel(selectedModel.provider) }}</span>
                <span>{{ engineLabel(selectedModel.engine) }}</span>
                <span v-if="selectedModel.recommendedVramGb">建议显存 {{ selectedModel.recommendedVramGb }} GB</span>
                <span>{{ selectedModel.capabilities.batch ? '支持批处理' : '逐张处理' }}</span>
                <span v-if="selectedModel.license">许可：{{ selectedModel.license }}</span>
                <span v-if="selectedModel.minTransformers">Transformers ≥ {{ selectedModel.minTransformers }}</span>
                <span v-if="selectedModel.gated">需接受模型许可</span>
                <span v-if="selectedModel.requiresHfToken">需配置 Hugging Face Token</span>
                <span v-if="selectedModel.trustRemoteCode">会加载模型仓库代码</span>
                <span v-if="selectedModel.experimental">实验性模型</span>
              </div>
              <p v-if="selectedModel.statusReason" class="model-status-reason">{{ selectedModel.statusReason }}</p>
              <p v-if="selectedModel.missingDependencies.length" class="model-dependencies">
                缺少依赖：{{ selectedModel.missingDependencies.join('、') }}
              </p>
              <div v-if="selectedModel.warnings.length" class="model-warnings" role="note">
                <p v-for="warning in selectedModel.warnings" :key="warning">
                  <el-icon><WarningFilled /></el-icon>
                  <span>{{ warning }}</span>
                </p>
              </div>
              <a
                v-if="selectedModel.homepage"
                class="model-homepage"
                :href="selectedModel.homepage"
                target="_blank"
                rel="noreferrer"
              >
                查看模型主页与许可说明
              </a>
            </article>

            <label v-if="selectedModel && selectedModel.outputModes.length > 1" class="field field-wide">
              <span class="field-label">输出形式</span>
              <el-radio-group v-model="draft.outputMode">
                <el-radio-button v-for="mode in selectedModel.outputModes" :key="mode" :value="mode">
                  {{ outputModeLabel(mode) }}
                </el-radio-button>
              </el-radio-group>
              <small>标签适合动漫 LoRA；自然描述适合写实素材和语义更丰富的训练。</small>
            </label>
          </div>

          <div v-for="group in regularParamGroups" :key="group.id" class="param-group">
            <div class="param-group-heading">
              <h3>{{ group.title }}</h3>
              <p>{{ group.description }}</p>
            </div>
            <div class="param-grid">
              <CaptionParamControl
                v-for="param in group.params"
                :key="param.name"
                :param="param"
                :model-value="draft.params[param.name]"
                @update:model-value="updateParam(param.name, $event)"
              />
            </div>
          </div>

          <div v-if="selectedModel?.capabilities.prompt" class="prompt-block">
            <div class="param-group-heading">
              <h3>多模态指令</h3>
              <p>告诉模型关注哪些信息。指令本身不会被写入 Caption。</p>
            </div>
            <div class="param-grid">
              <label class="field field-wide">
                <span class="field-label">识别指令</span>
                <el-input
                  v-model="draft.instruction"
                  type="textarea"
                  :rows="4"
                  maxlength="8000"
                  show-word-limit
                  :disabled="!customInstructionEnabled"
                  placeholder="例如：准确描述主体、服装、动作、构图与光线。"
                />
                <small v-if="customInstructionEnabled">模型通常更擅长英语指令；需要中文输出时可在指令中明确要求。</small>
                <small v-else>当前使用内置提示预设；将“提示预设”切换为“自定义指令”后可编辑。</small>
              </label>
              <label class="field">
                <span class="field-label">输出语言</span>
                <el-select v-model="draft.language">
                  <el-option
                    v-for="language in selectedModel.capabilities.languages"
                    :key="language"
                    :label="languageLabel(language)"
                    :value="language"
                  />
                </el-select>
                <small>只显示模型 catalog 声明支持的语言。</small>
              </label>
            </div>
          </div>

          <button
            v-if="advancedParamGroups.length"
            class="advanced-toggle"
            type="button"
            @click="advancedVisible = !advancedVisible"
          >
            <el-icon><Setting /></el-icon>
            {{ advancedVisible ? '收起模型高级参数' : '展开模型高级参数' }}
          </button>

          <div v-if="advancedVisible" class="advanced-area">
            <div v-for="group in advancedParamGroups" :key="group.id" class="param-group">
              <div class="param-group-heading">
                <h3>{{ group.title }} · 高级</h3>
                <p>{{ group.description }}</p>
              </div>
              <div class="param-grid">
                <CaptionParamControl
                  v-for="param in group.params"
                  :key="param.name"
                  :param="param"
                  :model-value="draft.params[param.name]"
                  @update:model-value="updateParam(param.name, $event)"
                />
              </div>
            </div>
          </div>
        </section>

        <section class="config-section" aria-labelledby="output-title">
          <div class="section-heading">
            <div>
              <h2 id="output-title">整理结果并创建任务</h2>
            </div>
          </div>

          <div class="param-group">
            <div class="param-group-heading">
              <h3>结果整理</h3>
              <p>
                {{ draft.outputMode === 'caption'
                  ? '自然语言描述只应用统一前缀和后缀，不执行标签清理。'
                  : '这些规则在标签模型输出之后执行，再组成最终 Caption。' }}
              </p>
            </div>
            <div class="param-grid">
              <label v-if="draft.outputMode !== 'caption'" class="field">
                <span class="field-label">固定附加标签</span>
                <el-input v-model="draft.additionalTags" clearable placeholder="例如 trigger_name, 1girl" />
                <small>逗号或换行分隔；这些标签总会加入结果。</small>
              </label>
              <label v-if="draft.outputMode !== 'caption'" class="field">
                <span class="field-label">排除标签</span>
                <el-input v-model="draft.excludeTags" clearable placeholder="例如 watermark, text" />
                <small>从模型结果中移除不希望进入训练的标签。</small>
              </label>
              <label class="field">
                <span class="field-label">统一前缀</span>
                <el-input v-model="draft.prefix" clearable placeholder="可选" />
              </label>
              <label class="field">
                <span class="field-label">统一后缀</span>
                <el-input v-model="draft.suffix" clearable placeholder="可选" />
              </label>
              <label v-if="draft.outputMode !== 'caption'" class="field">
                <span class="field-label">标签分隔符</span>
                <el-input v-model="draft.separator" maxlength="32" />
                <small>通常使用英文逗号加空格。</small>
              </label>
              <label v-if="draft.outputMode !== 'caption'" class="option-card">
                <span>
                  <strong>去除重复标签</strong>
                  <small>保留第一次出现的位置，避免重复 Token。</small>
                </span>
                <el-switch v-model="draft.deduplicate" />
              </label>
              <label v-if="draft.outputMode !== 'caption'" class="option-card">
                <span>
                  <strong>下划线替换为空格</strong>
                  <small>让 Danbooru 标签更接近自然文本格式。</small>
                </span>
                <el-switch v-model="draft.replaceUnderscore" />
              </label>
              <label
                v-if="draft.outputMode !== 'caption' && draft.replaceUnderscore"
                class="field"
              >
                <span class="field-label">保留下划线的标签</span>
                <el-input
                  v-model="draft.replaceUnderscoreExcludes"
                  clearable
                  placeholder="例如 character_name, series_name"
                />
                <small>逗号或换行分隔；命中的完整标签不会把下划线替换为空格。</small>
              </label>
              <label v-if="draft.outputMode !== 'caption'" class="option-card">
                <span>
                  <strong>转义标签特殊字符</strong>
                  <small>为反斜杠和圆括号添加转义；仅在训练语法需要时开启。</small>
                </span>
                <el-switch v-model="draft.escapeTags" />
              </label>
              <label
                v-if="draft.outputMode !== 'caption' && selectedModel?.capabilities.scores"
                class="option-card"
              >
                <span>
                  <strong>写入置信度权重</strong>
                  <small>把分数写成训练权重；普通数据集通常保持关闭。</small>
                </span>
                <el-switch v-model="draft.includeConfidence" />
              </label>
            </div>
          </div>

          <div class="param-group">
            <div class="param-group-heading">
              <h3>执行与写入</h3>
            </div>
            <div class="param-grid">
              <label class="field">
                <span class="field-label">任务名称</span>
                <el-input v-model="draft.name" clearable maxlength="120" placeholder="可选，例如 角色数据集首轮标注" />
              </label>
              <label class="field">
                <span class="field-label">已有 Caption</span>
                <el-select v-model="draft.conflictPolicy">
                  <el-option label="跳过已有文件（推荐）" value="skip" />
                  <el-option label="只填充空文件" value="fill_empty" />
                  <el-option label="覆盖已有内容" value="overwrite" />
                  <el-option label="生成结果放在原内容前" value="prepend" />
                  <el-option label="生成结果追加到原内容后" value="append" />
                </el-select>
                <small>{{ draft.stageBeforeWrite ? '复核提交时仍可重新选择策略。' : '默认跳过已有文件，避免覆盖人工内容。' }}</small>
              </label>
              <label class="field">
                <span class="field-label">推理设备</span>
                <div class="runtime-row">
                  <el-select v-model="draft.device" aria-label="推理设备">
                    <el-option label="自动选择" value="auto" />
                    <el-option
                      label="CPU"
                      value="cpu"
                      :disabled="!selectedModel?.capabilities.devices.includes('cpu')"
                    />
                    <el-option
                      label="CUDA GPU"
                      value="cuda"
                      :disabled="!selectedModel?.capabilities.devices.includes('cuda')"
                    />
                  </el-select>
                  <el-select v-model="draft.dtype" aria-label="推理精度">
                    <el-option label="自动精度" value="auto" />
                    <el-option label="Float32" value="float32" />
                    <el-option label="Float16" value="float16" />
                    <el-option label="BFloat16" value="bfloat16" />
                  </el-select>
                </div>
                <small>低精度可降低显存占用，但需模型和设备支持。</small>
              </label>
              <label class="field">
                <span class="field-label">推理 Batch Size</span>
                <el-input-number
                  v-model="draft.batchSize"
                  :min="1"
                  :max="64"
                  :disabled="selectedModel?.capabilities.batch === false"
                  controls-position="right"
                />
                <small>显存不足时保持为 1；传统 ONNX Tagger 可适当增大。</small>
              </label>
              <label class="option-card">
                <span>
                  <strong>生成后进入可选复核 <el-tag type="info" effect="plain">可选</el-tag></strong>
                  <small>开启后暂存逐图结果，确认后再写入；适合小批量抽样验证。大批量编辑将由 Tag 编辑器承担。</small>
                </span>
                <el-switch v-model="draft.stageBeforeWrite" />
              </label>
              <label class="option-card">
                <span>
                  <strong>覆盖前创建备份</strong>
                  <small>保存已有 Caption 的原始字节和变更记录。</small>
                </span>
                <el-switch v-model="draft.backupExisting" />
              </label>
              <label class="option-card">
                <span>
                  <strong>保留模型原始结果</strong>
                  <small>用于诊断模型输出，会增加任务数据库占用；不影响最终 Caption。</small>
                </span>
                <el-switch v-model="draft.saveRawResult" />
              </label>
            </div>
          </div>

          <div class="start-panel" :class="{ ready: canStart }">
            <div>
              <el-icon><MagicStick /></el-icon>
              <span>
                <strong v-if="canStart">已可以创建 Caption 任务</strong>
                <strong v-else>完成数据集扫描和模型选择后即可开始</strong>
                <small v-if="caption.dataset">
                  {{ draft.scope === 'selected' ? `${selectedIds.length} 张已选图片` : `${caption.dataset.total} 张扫描图片` }}
                  · {{ selectedModel?.title || '未选择模型' }}
                  · {{ draft.stageBeforeWrite ? '先复核后写入' : '生成后直接写入' }}
                </small>
              </span>
            </div>
            <el-button
              type="primary"
              size="large"
              :icon="VideoPlay"
              :disabled="!canStart"
              :loading="caption.starting"
              @click="startJob"
            >
              创建 Caption 任务
            </el-button>
          </div>

          <el-alert
            v-if="caption.currentError"
            type="error"
            :title="caption.currentError"
            :closable="false"
            show-icon
          />
        </section>
      </main>

      <aside class="history-panel" aria-labelledby="history-title">
        <div class="history-heading">
          <div>
            <h2 id="history-title">Caption 历史</h2>
          </div>
          <el-button circle text :icon="Refresh" :loading="caption.jobsLoading" aria-label="刷新历史" @click="caption.loadJobs()" />
        </div>

        <el-alert
          v-if="caption.jobsError"
          type="error"
          :title="caption.jobsError"
          :closable="false"
          show-icon
        />

        <div v-if="history.length" class="history-list">
          <button
            v-for="job in history"
            :key="job.id"
            class="history-item"
            type="button"
            @click="openHistoryJob(job.id)"
          >
            <span class="history-icon"><el-icon><EditPen /></el-icon></span>
            <span class="history-copy">
              <strong>{{ job.name || job.modelTitle }}</strong>
              <span>{{ job.reviewMode ? '可选复核' : '直接写入' }} · {{ job.processed }}/{{ job.total }}</span>
              <small><el-icon><Clock /></el-icon>{{ formatTime(job.createdAt) }}</small>
            </span>
            <el-tag :type="jobStateType(job.state)">{{ jobStateLabel(job.state) }}</el-tag>
          </button>
        </div>

        <div v-else-if="!caption.jobsLoading" class="history-empty">
          <el-icon><MagicStick /></el-icon>
          <strong>还没有 Caption 任务</strong>
          <span>创建任务后可在这里跟踪进度、日志和异常。</span>
        </div>

        <div class="history-help">
          <strong>安全写入说明</strong>
          <p>每个任务固定数据集快照和模型参数；写入时会检查文件指纹并使用原子替换，避免覆盖扫描后发生的人工修改。</p>
        </div>
      </aside>
    </div>

    <FilePicker
      v-model="pickerVisible"
      kind="folder"
      root="train"
      @select="(path) => (draft.path = path)"
    />
  </section>
</template>

<style scoped>
.caption-page {
  width: min(100%, var(--page-max));
  min-height: 100dvh;
  margin: 0 auto;
  padding: 34px clamp(20px, 3vw, 48px) 58px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.eyebrow {
  color: var(--brand-strong);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.page-heading h1 {
  margin: 4px 0 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: var(--font-page-title);
  font-weight: 740;
  letter-spacing: -0.03em;
}

.page-heading p {
  max-width: 760px;
  margin: 7px 0 0;
  color: var(--text-secondary);
  font-size: 15px;
}

.workbench-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  align-items: start;
  gap: 18px;
}

.configuration-flow {
  min-width: 0;
  display: grid;
  gap: 0;
}

.config-section,
.history-panel {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.config-section {
  display: grid;
  gap: 20px;
  padding: 26px 4px 34px;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  gap: 13px;
}

.section-heading h2 {
  margin: 0;
  color: var(--text-strong);
  font-size: 19px;
  font-weight: 600;
}

.section-heading p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 14px;
}

.source-form,
.model-picker-grid,
.param-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 18px;
}

.field {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 7px;
}

.field-wide {
  grid-column: 1 / -1;
}

.field-label {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 640;
}

.field-label em {
  margin-left: 4px;
  color: var(--danger);
  font-size: 13px;
  font-style: normal;
}

.field small,
.option-card small {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
}

.field :deep(.el-input-number) {
  width: 100%;
}

.option-card {
  min-width: 0;
  min-height: 78px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 14px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.option-card > span {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.option-card strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 640;
}

.scan-action {
  display: flex;
  align-items: center;
  gap: 12px;
}

.outdated-warning {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--warning);
  font-size: 13px;
}

.model-summary {
  grid-column: 1 / -1;
  display: grid;
  gap: 10px;
  padding: 15px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.model-summary-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.model-summary-heading span {
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 630;
}

.model-summary-heading h3 {
  margin: 2px 0 0;
  color: var(--text-strong);
  font-size: 18px;
  font-weight: 690;
}

.model-summary > p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.55;
}

.model-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.model-facts span {
  padding: 4px 7px;
  border: 0;
  border-radius: 6px;
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 13px;
}

.model-status-reason {
  color: var(--warning) !important;
}

.model-dependencies {
  color: var(--danger) !important;
}

.model-warnings {
  display: grid;
  gap: 6px;
}

.model-warnings p {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 0;
  color: var(--warning);
  font-size: 13px;
  line-height: 1.5;
}

.model-warnings .el-icon {
  flex: 0 0 auto;
  margin-top: 3px;
}

.model-homepage {
  justify-self: start;
  color: var(--brand-strong);
  font-size: 13px;
  font-weight: 640;
  text-underline-offset: 3px;
}

.param-group,
.prompt-block {
  display: grid;
  gap: 14px;
  padding-top: 18px;
  border-top: 1px solid var(--border-subtle);
}

.param-group-heading h3 {
  margin: 0;
  color: var(--text-strong);
  font-size: 16px;
  font-weight: 680;
}

.param-group-heading p {
  margin: 3px 0 0;
  color: var(--text-muted);
  font-size: 13px;
}

.advanced-toggle {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 0;
  border: 0;
  background: transparent;
  color: var(--brand-strong);
  font: inherit;
  font-size: 14px;
  font-weight: 640;
  cursor: pointer;
}

.advanced-area {
  display: grid;
  gap: 18px;
  padding: 16px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.advanced-area .param-group:first-child {
  padding-top: 0;
  border-top: 0;
}

.runtime-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.start-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.start-panel.ready {
  background: var(--brand-softer);
}

.start-panel > div {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 11px;
}

.start-panel > div > .el-icon {
  color: var(--brand-strong);
  font-size: 25px;
}

.start-panel span {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.start-panel strong {
  color: var(--text-strong);
  font-size: 15px;
}

.start-panel small {
  color: var(--text-muted);
  font-size: 13px;
}

.history-panel {
  position: sticky;
  top: 18px;
  display: grid;
  gap: 14px;
  padding: 4px 0 18px;
}

.history-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.history-heading h2 {
  margin: 2px 0 0;
  color: var(--text-strong);
  font-size: 18px;
  font-weight: 690;
}

.history-list {
  display: grid;
  gap: 7px;
}

.history-item {
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 9px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.history-item:hover {
  border-color: transparent;
  background: var(--surface-hover);
}

.history-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.history-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.history-copy strong,
.history-copy > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-copy strong {
  color: var(--text-strong);
  font-size: 14px;
}

.history-copy > span,
.history-copy small {
  color: var(--text-muted);
  font-size: 13px;
}

.history-copy small {
  display: flex;
  align-items: center;
  gap: 4px;
}

.history-empty {
  min-height: 180px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 7px;
  color: var(--text-muted);
  text-align: center;
}

.history-empty .el-icon {
  font-size: 28px;
}

.history-empty strong {
  color: var(--text-strong);
  font-size: 14px;
}

.history-empty span {
  font-size: 13px;
}

.history-help {
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.history-help strong {
  color: var(--text-strong);
  font-size: 13px;
}

.history-help p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.55;
}

@media (max-width: 1180px) {
  .workbench-layout {
    grid-template-columns: 1fr;
  }

  .history-panel {
    position: static;
  }

  .history-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .caption-page {
    padding: 20px 14px 38px;
  }

  .page-header,
  .start-panel {
    align-items: stretch;
    flex-direction: column;
  }

  .config-section {
    padding: 16px 14px;
  }

  .source-form,
  .model-picker-grid,
  .param-grid,
  .history-list {
    grid-template-columns: 1fr;
  }

  .field-wide {
    grid-column: auto;
  }

  .runtime-row {
    grid-template-columns: 1fr;
  }

  .scan-action {
    align-items: stretch;
    flex-direction: column;
  }

  .start-panel .el-button {
    width: 100%;
  }
}
</style>
