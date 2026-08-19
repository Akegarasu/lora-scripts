<script setup lang="ts">
import type { Component } from 'vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Box,
  Coin,
  Cpu,
  DataAnalysis,
  Document,
  Files,
  MagicStick,
  Monitor,
  Operation,
  Picture,
  Refresh,
  Search,
  Setting,
  Timer,
  TrendCharts,
  VideoPlay,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import ModelAssetForm from '@/components/ModelAssetForm.vue'
import ParamControl from '@/components/ParamControl.vue'
import ParamSearch from '@/components/ParamSearch.vue'
import InfoHint from '@/components/InfoHint.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import type { ParamDefinition, ParamGroup } from '@/api/types'
import { useCatalogStore } from '@/stores/catalog'
import { useDevicesStore } from '@/stores/devices'
import { useDraftStore } from '@/stores/draft'
import { useJobsStore } from '@/stores/jobs'
import CompileInspector from './components/CompileInspector.vue'
import DatasetEditor from './components/DatasetEditor.vue'
import SamplePromptEditor from './components/SamplePromptEditor.vue'

const router = useRouter()
const catalog = useCatalogStore()
const devices = useDevicesStore()
const draft = useDraftStore()
const jobs = useJobsStore()

const searchVisible = ref(false)
const inspectorVisible = ref(false)
const activeSection = ref('runtime')
const editorColumn = ref<HTMLElement | null>(null)
const initialized = ref(false)
const hydrating = ref(false)
const savePending = ref(false)
const densityOptions = [
  { label: '引导', value: 'recommended' },
  { label: '专家', value: 'advanced' },
] as const
let saveTimer: number | undefined
let sectionFrame: number | undefined
let sectionObserver: IntersectionObserver | undefined
let sectionScrollTarget: { id: string; expiresAt: number } | undefined
let hydrationVersion = 0
let manuallyRefreshingView = false

const GROUP_META: Record<string, { description: string; icon: Component }> = {
  training: { description: '训练轮次、批次、精度与随机性。', icon: TrendCharts },
  network: { description: 'LoRA 结构、维度、Alpha 与训练范围。', icon: DataAnalysis },
  optimizer: { description: '学习率、优化器与调度策略。', icon: Coin },
  memory: { description: '缓存、检查点与显存交换策略。', icon: Cpu },
  save: { description: '输出位置、格式和保存频率。', icon: Files },
  model_specific: { description: '当前模型架构专属的训练选项。', icon: MagicStick },
  logging: { description: '日志目录与训练观测集成。', icon: Monitor },
  distributed: { description: '多卡、DeepSpeed 与分布式运行。', icon: Operation },
  caption: { description: 'Caption 增强、丢弃和 Token 行为。', icon: Document },
  advanced: { description: '低频但可精细控制训练的选项。', icon: Setting },
  raw: { description: '尚未产品化分类的原始 sd-scripts 参数。', icon: Box },
}

const GROUP_ORDER = [
  'training',
  'network',
  'optimizer',
  'memory',
  'save',
  'model_specific',
  'logging',
  'caption',
  'distributed',
  'advanced',
  'raw',
]

const modelGroup = computed(() => catalog.modelGroup)
const selectedGroups = computed(() =>
  catalog.nonModelGroups
    .sort((a, b) => {
      const aIndex = GROUP_ORDER.indexOf(a.id)
      const bIndex = GROUP_ORDER.indexOf(b.id)
      return (aIndex < 0 ? 999 : aIndex) - (bIndex < 0 ? 999 : bIndex)
    }),
)

function isEmpty(value: unknown) {
  return value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)
}

function isRequired(param: ParamDefinition) {
  return !!param.required || param.priority === 'required'
}

const requiredParams = computed(() => catalog.allParams.filter((param) => !param.hidden && isRequired(param)))
const missingParams = computed(() =>
  requiredParams.value.filter((param) => isEmpty(draft.getValue(param))),
)
const missingModelParams = computed(() => missingParams.value.filter((param) => param.group === 'model'))
const previewFresh = computed(
  () =>
    !!draft.compileResult &&
    !!catalog.selectedTrainerId &&
    draft.compiledSignature === draft.signature(catalog.selectedTrainerId),
)

const sectionNavItems = computed(() => {
  const items: Array<{ id: string; title: string; icon: Component; count?: number; done: boolean }> = [
    {
      id: 'runtime',
      title: '运行与输出',
      icon: VideoPlay,
      done: !!draft.name.trim() && !!catalog.selectedTrainerId,
    },
  ]
  if (modelGroup.value?.params.length) {
    items.push({
      id: 'model',
      title: '模型资产',
      icon: Box,
      count: modelGroup.value.params.length,
      done: missingModelParams.value.length === 0,
    })
  }
  items.push({
    id: 'dataset',
    title: '训练数据',
    icon: Picture,
    done: !!draft.dataset.root.trim(),
  })
  for (const group of selectedGroups.value) {
    items.push({
      id: group.id,
      title: group.title,
      icon: groupMeta(group).icon,
      count: group.params.length,
      done: group.params.filter(isRequired).every((param) => !isEmpty(draft.getValue(param))),
    })
  }
  items.push({
    id: 'sampling',
    title: '采样预览',
    icon: MagicStick,
    done: !draft.sample.enabled || draft.sample.prompts.some((item) => !!item.prompt.trim()),
  })
  return items
})

const saveLabel = computed(() => {
  if (savePending.value) return '正在保存草稿…'
  if (draft.storageError) return '草稿保存失败'
  if (!draft.lastSavedAt) return '本地草稿已启用'
  const time = new Date(draft.lastSavedAt)
  return Number.isNaN(time.getTime())
    ? '草稿已保存'
    : `已于 ${time.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} 保存`
})

const trainerManifest = computed(() => {
  const hash = catalog.manifestHash || ''
  return hash.length > 12 ? hash.slice(0, 12) : hash || 'catalog'
})

function completeDefinitionsFor(trainerId: string) {
  if (
    !trainerId ||
    catalog.allGroupsTrainerId !== trainerId ||
    !catalog.allGroupsManifestHash ||
    catalog.allGroupsManifestHash !== catalog.manifestHash
  ) {
    return [] as ParamDefinition[]
  }
  return catalog.allParams
}

function persistTrainerDraft(trainerId: string) {
  return draft.persistForTrainer(trainerId, completeDefinitionsFor(trainerId))
}

function groupMeta(group: ParamGroup) {
  return {
    description: group.description || GROUP_META[group.id]?.description || '由参数目录提供的训练选项。',
    icon: GROUP_META[group.id]?.icon || Operation,
  }
}

function formatBytes(value: number) {
  if (!value) return '0 GB'
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function isParamModified(param: ParamDefinition) {
  return draft.isValueModified(param)
}

function resetParam(param: ParamDefinition) {
  draft.resetValue(param)
}

function trainerStatusLabel(status: string) {
  const labels: Record<string, string> = {
    experimental: '实验性',
    preview: '预览',
    beta: '测试版',
    deprecated: '已弃用',
  }
  return labels[status] || status
}

function scrollToSection(id: string) {
  const target = editorColumn.value?.querySelector<HTMLElement>(`#section-${CSS.escape(id)}`)
  if (!target) return

  activeSection.value = id
  sectionScrollTarget = {
    id,
    // Native smooth scrolling is normally shorter than one second. The upper
    // bound prevents an interrupted scroll from pinning the old target forever.
    expiresAt: performance.now() + 1600,
  }
  target.scrollIntoView({ behavior: scrollBehavior(), block: 'start' })
}

function scrollBehavior(): ScrollBehavior {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

async function refreshVisibleParams() {
  await catalog.loadParams()
  await nextTick()
  setupSectionObserver()
}

async function revealIssueParam(targetId: string) {
  if (!targetId.startsWith('param-')) return

  const paramName = targetId.slice('param-'.length)
  const param = catalog.allParams.find((item) => item.name === paramName)
  if (!param || param.hidden || catalog.visibleParams.some((item) => item.name === paramName)) return

  const visibleInAdvanced = ['required', 'recommended', 'advanced', 'dangerous', 'raw'].includes(
    param.priority,
  )
  if (!visibleInAdvanced || catalog.view === 'advanced') return

  manuallyRefreshingView = true
  try {
    catalog.view = 'advanced'
    await nextTick()
    await refreshVisibleParams()
  } finally {
    manuallyRefreshingView = false
  }
}

async function locateIssue(targetId: string) {
  inspectorVisible.value = false
  await nextTick()
  let target = document.getElementById(targetId)
  if (!target) {
    await revealIssueParam(targetId)
    target = document.getElementById(targetId)
  }
  if (!target) return

  target.scrollIntoView({ behavior: scrollBehavior(), block: 'center' })
  const focusTarget =
    target.matches('input, textarea, select, button, [tabindex]')
      ? target
      : target.querySelector<HTMLElement>(
          'input:not([disabled]), textarea:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )

  if (focusTarget instanceof HTMLElement) {
    focusTarget.focus({ preventScroll: true })
    return
  }

  target.setAttribute('tabindex', '-1')
  target.focus({ preventScroll: true })
  target.addEventListener('blur', () => target.removeAttribute('tabindex'), { once: true })
}

function workbenchSections() {
  const validIds = new Set(sectionNavItems.value.map((item) => item.id))
  return Array.from(
    editorColumn.value?.querySelectorAll<HTMLElement>('[data-workbench-section]') || [],
  ).filter((section) => {
    const id = section.dataset.workbenchSection
    return !!id && validIds.has(id)
  })
}

function sectionScrollMargin(section: HTMLElement) {
  const value = Number.parseFloat(window.getComputedStyle(section).scrollMarginTop)
  return Number.isFinite(value) ? value : 0
}

function viewportAtBottom() {
  const scroller = document.scrollingElement
  if (!scroller) return false
  return scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2
}

function syncActiveSection() {
  const sections = workbenchSections()
  if (!sections.length) return

  const now = performance.now()
  if (sectionScrollTarget) {
    const target = sections.find(
      (section) => section.dataset.workbenchSection === sectionScrollTarget?.id,
    )
    const targetReached =
      !!target &&
      (Math.abs(target.getBoundingClientRect().top - sectionScrollMargin(target)) <= 4 ||
        (target === sections.at(-1) && viewportAtBottom()))

    if (!targetReached && now < sectionScrollTarget.expiresAt) {
      // Keep the clicked chapter highlighted while native smooth scrolling
      // crosses other observer bands.
      activeSection.value = sectionScrollTarget.id
      return
    }
    sectionScrollTarget = undefined
  }

  // scrollIntoView honours scroll-margin-top. Use the same line for deciding
  // which section owns the viewport instead of relying on callback entry order.
  const activationLine = sectionScrollMargin(sections[0]) + 2
  let current = sections[0]
  for (const section of sections) {
    if (section.getBoundingClientRect().top > activationLine) break
    current = section
  }
  if (viewportAtBottom()) current = sections.at(-1) || current

  const id = current.dataset.workbenchSection
  if (id) activeSection.value = id
}

function scheduleSectionSync() {
  if (sectionFrame !== undefined) return
  sectionFrame = window.requestAnimationFrame(() => {
    sectionFrame = undefined
    syncActiveSection()
  })
}

function cancelSectionScrollTarget() {
  sectionScrollTarget = undefined
}

function setupSectionObserver() {
  sectionObserver?.disconnect()
  const sections = workbenchSections()
  if (!sections.length) return
  syncActiveSection()
  if (typeof IntersectionObserver === 'undefined') return

  sectionObserver = new IntersectionObserver(
    () => scheduleSectionSync(),
    { rootMargin: '-1px 0px -1px 0px', threshold: [0, 0.01] },
  )
  sections.forEach((section) => sectionObserver?.observe(section))
}

async function loadTrainerDraft(trainerId: string, restoreSaved = true) {
  if (!trainerId) return
  const version = ++hydrationVersion
  activeSection.value = 'runtime'
  sectionScrollTarget = undefined
  sectionObserver?.disconnect()
  hydrating.value = true
  try {
    await Promise.all([catalog.loadParams(), catalog.loadAllParams()])
    if (version !== hydrationVersion || catalog.selectedTrainerId !== trainerId) return
    const definitions = completeDefinitionsFor(trainerId)
    if (!definitions.length) return
    draft.resetForTrainer(
      definitions,
      trainerId,
      catalog.manifestHash,
      restoreSaved,
      catalog.selectedTrainer?.datasetDefaults ?? {},
    )
  } finally {
    if (version === hydrationVersion) hydrating.value = false
  }
  // The editor is hidden by the hydration skeleton. Observe it only after the
  // skeleton has yielded and Vue has mounted the new trainer's section DOM.
  await nextTick()
  if (version !== hydrationVersion || catalog.selectedTrainerId !== trainerId) return
  setupSectionObserver()
}

async function refreshCatalog() {
  if (catalog.selectedTrainerId) {
    persistTrainerDraft(catalog.selectedTrainerId)
  }
  if (!catalog.trainers.length || !catalog.selectedTrainerId) {
    await catalog.loadTrainers()
  }
  if (catalog.selectedTrainerId) {
    await Promise.all([catalog.loadParams(), catalog.loadAllParams(), devices.loadGpus()])
    const definitions = completeDefinitionsFor(catalog.selectedTrainerId)
    if (definitions.length) {
      if (draft.manifestHash) {
        draft.reconcileForCatalog(definitions, catalog.manifestHash, catalog.selectedTrainerId)
      } else {
        draft.resetForTrainer(
          definitions,
          catalog.selectedTrainerId,
          catalog.manifestHash,
          true,
          catalog.selectedTrainer?.datasetDefaults ?? {},
        )
      }
    }
  } else {
    await devices.loadGpus()
  }
  await nextTick()
  setupSectionObserver()
  if (catalog.error || devices.error) {
    ElMessage.warning('部分信息刷新失败，请查看页面提示后重试')
  } else {
    ElMessage.success('参数目录与设备信息已刷新')
  }
}

function saveDraftNow() {
  if (!catalog.selectedTrainerId) return
  if (saveTimer !== undefined) window.clearTimeout(saveTimer)
  const saved = persistTrainerDraft(catalog.selectedTrainerId)
  savePending.value = false
  if (!saved || draft.storageError) {
    ElMessage.error(draft.storageError || '草稿保存失败，请检查浏览器存储权限')
  } else {
    ElMessage.success('草稿已保存到本机')
  }
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) {
    cancelSectionScrollTarget()
  }
  if (!(event.ctrlKey || event.metaKey)) return
  const key = event.key.toLowerCase()
  if (key === 'k') {
    event.preventDefault()
    searchVisible.value = true
  } else if (key === 's') {
    event.preventDefault()
    saveDraftNow()
  }
}

async function compilePreview() {
  const result = await draft.compile(catalog.selectedTrainerId, { validatePaths: false })
  if (!result) {
    ElMessage.error('未能完成配置预检')
    return
  }
  if (result.errors.length) {
    ElMessage.error(`预检发现 ${result.errors.length} 个问题`)
    inspectorVisible.value = true
  } else if (result.warnings.length) {
    ElMessage.warning(`预检完成，有 ${result.warnings.length} 条提醒`)
  } else {
    ElMessage.success('配置预检通过')
  }
}

async function startTraining() {
  if (!catalog.selectedTrainerId || missingParams.value.length || !draft.dataset.root.trim() || !draft.name.trim()) {
    inspectorVisible.value = true
    ElMessage.warning('请先补全训练器、必要资产、数据集与输出名称')
    return
  }

  const result = await draft.compile(catalog.selectedTrainerId, { validatePaths: true })
  if (!result) {
    inspectorVisible.value = true
    ElMessage.error('完整校验请求失败')
    return
  }
  if (result.errors.length) {
    inspectorVisible.value = true
    ElMessage.error(`完整校验发现 ${result.errors.length} 个问题`)
    return
  }

  try {
    const warningText = result.warnings.length ? `，并带有 ${result.warnings.length} 条非阻塞提醒` : ''
    await ElMessageBox.confirm(
      `将以“${draft.name}”创建 ${catalog.selectedTrainer?.title || catalog.selectedTrainerId} 训练任务${warningText}。启动后请在任务中心查看日志。`,
      '确认开始训练',
      {
        confirmButtonText: '开始训练',
        cancelButtonText: '返回检查',
        type: result.warnings.length ? 'warning' : 'info',
        autofocus: false,
      },
    )
  } catch {
    return
  }

  await jobs.startJob(draft.buildDraft(catalog.selectedTrainerId))
  const job = jobs.startResult?.job
  if (job) {
    persistTrainerDraft(catalog.selectedTrainerId)
    ElMessage.success('训练任务已创建')
    await router.push(`/jobs/${job.id}`)
  } else if (jobs.error) {
    if (jobs.startResult?.compile) {
      draft.compileResult = jobs.startResult.compile
      draft.compiledSignature = draft.signature(catalog.selectedTrainerId)
    }
    inspectorVisible.value = true
    ElMessage.error(jobs.error)
  }
}

async function resetDraft() {
  const definitions = completeDefinitionsFor(catalog.selectedTrainerId)
  if (!definitions.length) {
    ElMessage.warning('完整参数目录尚未加载，暂时无法重置草稿')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将清除 ${catalog.selectedTrainer?.title || '当前训练器'} 的本地草稿，并恢复推荐默认值。`,
      '重置当前草稿',
      {
        confirmButtonText: '确认重置',
        cancelButtonText: '取消',
        type: 'warning',
        autofocus: false,
      },
    )
  } catch {
    return
  }
  draft.resetToDefaults(
    definitions,
    catalog.selectedTrainerId,
    catalog.manifestHash,
    catalog.selectedTrainer?.datasetDefaults ?? {},
  )
  ElMessage.success('已恢复推荐默认值')
}

function onBeforeUnload() {
  if (catalog.selectedTrainerId) persistTrainerDraft(catalog.selectedTrainerId)
}

onMounted(async () => {
  await catalog.loadTrainers()
  if (catalog.selectedTrainerId) {
    void devices.loadGpus()
    await loadTrainerDraft(catalog.selectedTrainerId)
  }
  initialized.value = true
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('keydown', onGlobalKeydown)
  window.addEventListener('scroll', scheduleSectionSync, { passive: true })
  window.addEventListener('resize', scheduleSectionSync, { passive: true })
  window.addEventListener('wheel', cancelSectionScrollTarget, { passive: true })
  window.addEventListener('touchstart', cancelSectionScrollTarget, { passive: true })
})

watch(
  () => catalog.selectedTrainerId,
  async (trainerId, previousTrainerId) => {
    if (!trainerId || trainerId === previousTrainerId) return
    catalog.rememberSelectedTrainer(trainerId)
    if (!initialized.value) return
    if (previousTrainerId) persistTrainerDraft(previousTrainerId)
    searchVisible.value = false
    await loadTrainerDraft(trainerId)
    window.scrollTo({ top: 0, behavior: scrollBehavior() })
  },
)

watch(
  () => catalog.view,
  async () => {
    if (!initialized.value || manuallyRefreshingView) return
    await refreshVisibleParams()
  },
)

watch(
  () => (catalog.selectedTrainerId ? draft.signature(catalog.selectedTrainerId) : ''),
  () => {
    if (!initialized.value || hydrating.value || !catalog.selectedTrainerId) return
    savePending.value = true
    if (saveTimer !== undefined) window.clearTimeout(saveTimer)
    saveTimer = window.setTimeout(() => {
      persistTrainerDraft(catalog.selectedTrainerId)
      savePending.value = false
    }, 700)
  },
  { flush: 'post' },
)

onBeforeUnmount(() => {
  if (saveTimer !== undefined) window.clearTimeout(saveTimer)
  if (sectionFrame !== undefined) window.cancelAnimationFrame(sectionFrame)
  if (catalog.selectedTrainerId) persistTrainerDraft(catalog.selectedTrainerId)
  sectionObserver?.disconnect()
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('scroll', scheduleSectionSync)
  window.removeEventListener('resize', scheduleSectionSync)
  window.removeEventListener('wheel', cancelSectionScrollTarget)
  window.removeEventListener('touchstart', cancelSectionScrollTarget)
})
</script>

<template>
  <section class="train-page">
    <header class="page-header">
      <div class="page-title">
        <div class="title-line">
          <h1>训练工作台</h1>
          <span
            class="draft-state"
            :class="{ error: draft.storageError, pending: savePending && !draft.storageError }"
            aria-live="polite"
          >
            <span aria-hidden="true" />
            {{ saveLabel }}
          </span>
        </div>
      </div>

      <SegmentedControl
        class="density-switch"
        :model-value="catalog.view"
        :options="densityOptions"
        accessible-label="参数密度"
        @update:model-value="(value) => (catalog.view = value as 'recommended' | 'advanced')"
      />

      <div class="page-actions">
        <el-button text :icon="Search" @click="searchVisible = true">搜索参数</el-button>
        <el-button text :icon="Refresh" :loading="catalog.loading || devices.loading" @click="refreshCatalog">
          刷新
        </el-button>
        <el-button text @click="resetDraft">重置草稿</el-button>
      </div>
    </header>

    <el-alert
      v-if="catalog.error"
      class="catalog-alert"
      type="error"
      :title="catalog.error"
      show-icon
      :closable="false"
    />

    <section v-if="!catalog.loading && !catalog.trainers.length" class="catalog-empty">
      <el-empty description="未能加载训练器目录">
        <p>请确认后端服务可用，然后重新获取训练器与参数信息。</p>
        <el-button type="primary" :loading="catalog.loading" @click="refreshCatalog">重新加载</el-button>
      </el-empty>
    </section>

    <section v-if="catalog.trainers.length" class="trainer-panel">
      <div class="trainer-control">
        <label for="trainer-select">
          <span>训练器</span>
        </label>
        <el-select
          id="trainer-select"
          v-model="catalog.selectedTrainerId"
          class="trainer-select"
          filterable
          :disabled="hydrating"
          :loading="catalog.loading"
          placeholder="选择训练器"
          popper-class="trainer-select-popper"
        >
          <el-option
            v-for="trainer in catalog.trainers"
            :key="trainer.id"
            :label="trainer.title"
            :value="trainer.id"
          >
            <div class="trainer-option">
              <span>
                <strong>{{ trainer.title }}</strong>
                <small>{{ trainer.id }}</small>
              </span>
              <span
                v-if="trainer.status !== 'stable'"
                class="trainer-status-tag"
                :title="`状态：${trainerStatusLabel(trainer.status)}`"
              >
                {{ trainerStatusLabel(trainer.status) }}
              </span>
            </div>
          </el-option>
        </el-select>
      </div>

      <div class="trainer-context">
        <span class="context-item">
          <small>模型族</small>
          <strong>{{ catalog.selectedTrainer?.family?.toUpperCase() || '—' }}</strong>
        </span>
        <span class="context-item">
          <small>任务</small>
          <strong>{{ catalog.selectedTrainer?.task || '—' }}</strong>
        </span>
        <span class="context-item manifest">
          <small>参数目录</small>
          <strong>{{ trainerManifest }}</strong>
        </span>
      </div>

    </section>

    <div v-if="catalog.trainers.length && (hydrating || (catalog.loading && !catalog.groups.length))" class="loading-shell">
      <el-skeleton :rows="10" animated />
    </div>

    <div
      v-else-if="catalog.trainers.length"
      v-loading="catalog.loading"
      class="workbench-layout"
      element-loading-text="正在更新参数目录"
    >
      <nav class="section-rail" aria-label="训练配置章节">
        <div class="rail-heading">
          <span>配置流程</span>
        </div>
        <button
          v-for="item in sectionNavItems"
          :key="item.id"
          type="button"
          class="rail-item"
          :class="{ active: activeSection === item.id, done: item.done }"
          @click="scrollToSection(item.id)"
        >
          <span class="rail-icon"><el-icon><component :is="item.icon" /></el-icon></span>
          <span class="rail-copy">
            <strong>{{ item.title }}</strong>
          </span>
        </button>
      </nav>

      <main ref="editorColumn" class="editor-column">
        <section
          id="section-runtime"
          class="config-section"
          data-workbench-section="runtime"
        >
          <header class="section-header">
            <span class="section-icon"><el-icon><VideoPlay /></el-icon></span>
            <div>
              <h2>运行与输出</h2>
            </div>
            <span class="section-state" :class="{ complete: draft.name.trim() }">
              {{ draft.name.trim() ? '已命名' : '需要名称' }}
            </span>
          </header>

          <div class="section-body runtime-grid">
            <label class="form-field output-field" for="output-name">
              <span>
                <strong>输出名称</strong>
                <em>必填</em>
              </span>
              <el-input
                id="output-name"
                v-model="draft.name"
                clearable
                maxlength="128"
                show-word-limit
                placeholder="例如 aki_flux_style_v1"
              />
            </label>

            <label class="form-field" for="cpu-threads">
              <span><strong>CPU 线程</strong></span>
              <el-input-number
                id="cpu-threads"
                v-model="draft.runtime.numCpuThreadsPerProcess"
                :min="1"
                :max="128"
                controls-position="right"
              />
              <small>每个训练进程用于数据加载的线程数。</small>
            </label>

            <label class="form-field gpu-field" for="gpu-select">
              <span class="label-with-info">
                <strong>运行 GPU</strong>
                <InfoHint
                  content="留空时沿用当前环境；多选时会配置 Accelerate 多卡启动参数。"
                  label="运行 GPU 补充信息"
                />
              </span>
              <el-select
                id="gpu-select"
                v-model="draft.runtime.gpuIds"
                multiple
                clearable
                filterable
                collapse-tags
                collapse-tags-tooltip
                :loading="devices.loading"
                placeholder="自动选择可见 GPU"
              >
                <el-option
                  v-for="gpu in devices.gpus"
                  :key="gpu.id"
                  :label="`GPU ${gpu.id} · ${gpu.name}`"
                  :value="gpu.id"
                >
                  <div class="gpu-option">
                    <span>
                      <strong>GPU {{ gpu.id }} · {{ gpu.name }}</strong>
                      <small>{{ formatBytes(gpu.vramFree) }} 可用 / {{ formatBytes(gpu.vramTotal) }}</small>
                    </span>
                    <span
                      class="gpu-meter"
                      :style="{ '--free': `${Math.round((gpu.vramFree / gpu.vramTotal) * 100)}%` }"
                    />
                  </div>
                </el-option>
              </el-select>
              <small v-if="devices.error" class="field-warning">{{ devices.error }}</small>
              <small v-else-if="!devices.loading && !devices.gpus.length">未检测到 CUDA GPU，启动前请检查运行环境。</small>
            </label>
          </div>
        </section>

        <section
          v-if="modelGroup?.params.length"
          id="section-model"
          class="config-section"
          data-workbench-section="model"
        >
          <header class="section-header">
            <span class="section-icon"><el-icon><Box /></el-icon></span>
            <div>
              <h2>模型资产</h2>
            </div>
            <span class="section-state" :class="{ complete: !missingModelParams.length }">
              {{ missingModelParams.length ? `缺少 ${missingModelParams.length} 项` : '必要项完整' }}
            </span>
          </header>
          <div class="section-body">
            <ModelAssetForm :params="modelGroup.params" />
          </div>
        </section>

        <section
          id="section-dataset"
          class="config-section"
          data-workbench-section="dataset"
        >
          <header class="section-header">
            <span class="section-icon"><el-icon><Picture /></el-icon></span>
            <div>
              <h2>训练数据</h2>
            </div>
            <span class="section-state" :class="{ complete: draft.dataset.root.trim() }">
              {{ draft.dataset.root.trim() ? '目录已选择' : '需要目录' }}
            </span>
          </header>
          <div class="section-body">
            <DatasetEditor />
          </div>
        </section>

        <section
          v-for="(group, groupIndex) in selectedGroups"
          :id="`section-${group.id}`"
          :key="group.id"
          class="config-section"
          :data-workbench-section="group.id"
        >
          <header class="section-header">
            <span class="section-icon"><el-icon><component :is="groupMeta(group).icon" /></el-icon></span>
            <div>
              <h2>{{ group.title }}</h2>
            </div>
            <span class="section-state neutral">{{ group.params.length }} 项</span>
          </header>

          <div class="section-body parameter-list">
            <div
              v-for="param in group.params"
              :id="`param-${param.name}`"
              :key="param.name"
              class="parameter-row"
              :class="{ dangerous: param.priority === 'dangerous' }"
            >
              <div class="parameter-copy">
                <div class="parameter-title">
                  <strong>{{ param.label || param.name }}</strong>
                  <el-tag v-if="isRequired(param)" size="small" type="danger" effect="plain">必填</el-tag>
                  <el-tag v-else-if="param.priority === 'dangerous'" size="small" type="danger" effect="light">
                    高风险
                  </el-tag>
                  <el-tag v-else-if="param.priority === 'advanced'" size="small" type="info" effect="plain">
                    高级
                  </el-tag>
                  <el-tag v-if="param.deprecated" size="small" type="warning" effect="plain">
                    已弃用
                  </el-tag>
                  <el-tag v-if="isParamModified(param)" size="small" type="primary" effect="light">
                    已修改
                  </el-tag>
                </div>
                <code>{{ param.name }}</code>
                <p v-if="param.description || param.help">{{ param.description || param.help }}</p>
              </div>
              <div class="parameter-control">
                <ParamControl
                  :param="param"
                  :model-value="draft.getValue(param)"
                  @update:model-value="draft.setValue(param, $event)"
                />
                <button v-if="isParamModified(param)" type="button" class="reset-param" @click="resetParam(param)">
                  恢复默认
                </button>
              </div>
            </div>
          </div>
        </section>

        <section
          id="section-sampling"
          class="config-section"
          data-workbench-section="sampling"
        >
          <header class="section-header">
            <span class="section-icon"><el-icon><MagicStick /></el-icon></span>
            <div>
              <h2>采样预览</h2>
            </div>
            <span class="section-state" :class="{ complete: draft.sample.enabled, neutral: !draft.sample.enabled }">
              {{ draft.sample.enabled ? `${draft.sample.prompts.length} 组提示词` : '未启用' }}
            </span>
          </header>
          <div class="section-body">
            <SamplePromptEditor />
          </div>
        </section>
      </main>

      <div class="desktop-inspector">
        <CompileInspector
          :missing-params="missingParams"
          :preview-fresh="previewFresh"
          @compile="compilePreview"
          @locate="locateIssue"
          @start="startTraining"
        />
      </div>
    </div>

    <button class="mobile-launch" type="button" @click="inspectorVisible = true">
      <span>
        <small>检查与启动</small>
        <strong>
          <template v-if="missingParams.length || !draft.dataset.root.trim()">
            仍有未完成项目
          </template>
          <template v-else-if="previewFresh">当前配置已预检</template>
          <template v-else>准备检查配置</template>
        </strong>
      </span>
      <span class="mobile-launch-icon"><el-icon><Timer /></el-icon></span>
    </button>

    <el-drawer
      v-model="inspectorVisible"
      class="inspector-drawer"
      title="检查与启动"
      size="390px"
      append-to-body
    >
      <CompileInspector
        :missing-params="missingParams"
        :preview-fresh="previewFresh"
        @compile="compilePreview"
        @locate="locateIssue"
        @start="startTraining"
      />
    </el-drawer>

    <ParamSearch v-model="searchVisible" />
  </section>
</template>

<style scoped>
.train-page {
  width: 100%;
  max-width: var(--page-max);
  min-height: 100dvh;
  margin: 0 auto;
  overflow-x: clip;
  padding: 30px 30px 70px;
}

.page-header {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.title-line {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 5px;
}

.page-title h1 {
  margin: 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: var(--font-page-title);
  font-weight: 560;
  letter-spacing: 0;
  line-height: 1.15;
}

.page-title > p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.draft-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 3px 8px;
  border: 1px solid color-mix(in srgb, var(--success) 26%, var(--border));
  border-radius: 6px;
  background: var(--success-soft);
  color: var(--success);
  font-size: 10px;
  font-weight: 620;
}

.draft-state > span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.draft-state.error {
  border-color: color-mix(in srgb, var(--danger) 26%, var(--border));
  background: var(--danger-soft);
  color: var(--danger);
}

.draft-state.pending {
  border-color: color-mix(in srgb, var(--info) 24%, var(--border));
  background: var(--info-soft);
  color: var(--info);
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.page-actions :deep(.el-button) {
  border: 0;
  background: transparent;
}

.page-actions :deep(.el-button:hover),
.page-actions :deep(.el-button:focus-visible) {
  background: var(--surface-hover);
  color: var(--text-strong);
}

.density-switch {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
}

.catalog-alert {
  margin-top: 18px;
}

.catalog-empty {
  min-height: min(560px, 62dvh);
  display: grid;
  place-items: center;
  margin-top: 26px;
  padding: 32px;
  border: 0;
  border-radius: 0;
  background: transparent;
  text-align: center;
}

.catalog-empty p {
  max-width: 430px;
  margin: -4px auto 18px;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.trainer-panel {
  display: grid;
  grid-template-columns: minmax(360px, 1.25fr) minmax(300px, 0.8fr);
  align-items: center;
  gap: 22px;
  margin-top: 26px;
  padding: 8px 0 20px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.trainer-control {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 14px;
}

.trainer-control > label {
  display: grid;
  gap: 2px;
}

.trainer-control > label > span {
  color: var(--text-strong);
  font-size: 11px;
  font-weight: 650;
}

.trainer-control > label > small {
  color: var(--text-muted);
  font-size: 9px;
  white-space: nowrap;
}

.trainer-select {
  min-width: 0;
  width: 100%;
}

.trainer-option,
.gpu-option {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.trainer-option > span,
.gpu-option > span:first-child {
  min-width: 0;
  display: grid;
}

.trainer-option strong,
.gpu-option strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trainer-option small,
.gpu-option small {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 9px;
}

.trainer-status-tag {
  flex: 0 0 auto;
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border: 1px solid color-mix(in srgb, var(--warning) 30%, var(--border));
  border-radius: 6px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12px;
  font-weight: 650;
  line-height: 1;
  white-space: nowrap;
}

:global(.trainer-select-popper .el-select-dropdown__item) {
  height: auto;
  min-height: 52px;
  display: flex;
  align-items: center;
  padding: 7px 12px;
  line-height: 1.35;
}

:global(.trainer-select-popper .el-select-dropdown__item.is-selected) {
  background: var(--brand-soft);
}

.trainer-context {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
}

.context-item {
  min-width: 0;
  display: grid;
  gap: 2px;
  padding-left: 11px;
  border-left: 1px solid var(--border-subtle);
}

.context-item small {
  color: var(--text-muted);
  font-size: 8px;
}

.context-item strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 10px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-item.manifest strong {
  font-family: var(--font-mono);
  font-size: 9px;
}

.loading-shell {
  max-width: 900px;
  margin: 28px auto;
  padding: 28px;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.workbench-layout {
  display: grid;
  grid-template-columns: 160px minmax(720px, 1fr) 280px;
  align-items: start;
  gap: 20px;
  margin-top: 22px;
}

.section-rail {
  position: sticky;
  top: 18px;
  display: grid;
  gap: 3px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.rail-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  justify-content: flex-start;
  padding: 5px 10px 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.rail-item {
  position: relative;
  width: 100%;
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 6px 10px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 140ms ease,
    color 140ms ease,
    border-color 140ms ease;
}

.rail-item:hover {
  background: var(--surface-hover);
  color: var(--text-strong);
}

.rail-item.active {
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.rail-icon {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 0;
  background: transparent;
  font-size: 15px;
}

.active .rail-icon {
  background: transparent;
}

.rail-copy {
  min-width: 0;
  display: grid;
  gap: 0;
}

.rail-copy strong {
  overflow: hidden;
  font-size: 13px;
  font-weight: 520;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editor-column {
  min-width: 0;
  display: grid;
  gap: 0;
}

.config-section {
  scroll-margin-top: 22px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.section-header {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto;
  align-items: center;
  gap: 13px;
  min-height: 64px;
  padding: 18px 4px 10px;
  border-bottom: 0;
  background: transparent;
}

.section-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: var(--surface-sunken);
  color: var(--brand-strong);
  font-size: 17px;
}

.section-header h2 {
  margin: 0;
  color: var(--text-strong);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
}

.section-header p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.4;
}

.section-state {
  min-height: 26px;
  display: inline-flex;
  align-items: center;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 9px;
  font-weight: 620;
  white-space: nowrap;
}

.section-state.complete {
  background: var(--success-soft);
  color: var(--success);
}

.section-state.neutral {
  background: var(--surface-sunken);
  color: var(--text-secondary);
}

.section-body {
  padding: 12px 4px 32px;
}

.runtime-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(150px, 0.65fr);
  gap: 18px 20px;
}

.form-field {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.form-field > span {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.form-field > .label-with-info {
  justify-content: flex-start;
  align-items: center;
  gap: 6px;
}

.form-field strong {
  color: var(--text-strong);
  font-size: 11px;
  font-weight: 630;
}

.form-field em {
  color: var(--danger);
  font-size: 9px;
  font-style: normal;
  font-weight: 600;
}

.form-field > span > small,
.form-field > small {
  color: var(--text-muted);
  font-size: 9px;
  line-height: 1.45;
}

.form-field :deep(.el-input-number) {
  width: 100%;
}

.gpu-field {
  grid-column: 1 / -1;
}

.field-warning {
  color: var(--warning) !important;
}

.gpu-meter {
  width: 54px;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--border-subtle);
}

.gpu-meter::after {
  width: var(--free);
  height: 100%;
  display: block;
  border-radius: inherit;
  background: var(--success);
  content: '';
}

.parameter-list {
  padding-block: 5px;
}

.parameter-row {
  display: grid;
  grid-template-columns: minmax(230px, 0.9fr) minmax(220px, 1.1fr);
  align-items: center;
  gap: 24px;
  min-height: 88px;
  padding: 15px;
  border-bottom: 1px solid var(--border-subtle);
  scroll-margin-top: 20px;
}

.parameter-row:last-child {
  border-bottom: 0;
}

.parameter-row:hover {
  background: color-mix(in srgb, var(--surface-hover) 56%, transparent);
}

.parameter-row.dangerous {
  background: color-mix(in srgb, var(--warning-soft) 28%, transparent);
}

.parameter-copy {
  min-width: 0;
}

.parameter-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
}

.parameter-title strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 650;
}

.parameter-copy code {
  display: block;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 11px;
}

.parameter-copy p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.parameter-control {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.reset-param {
  padding: 4px 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
}

.reset-param:hover {
  color: var(--brand-strong);
}

.desktop-inspector {
  position: sticky;
  top: 18px;
  max-height: calc(100dvh - 36px);
  overflow: auto;
  padding-right: 2px;
}

.mobile-launch {
  position: fixed;
  z-index: 35;
  right: 18px;
  bottom: 18px;
  display: none;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  min-width: 250px;
  padding: 10px 11px 10px 15px;
  border: 1px solid color-mix(in srgb, var(--brand) 30%, transparent);
  border-radius: 10px;
  background: var(--text-strong);
  box-shadow: var(--shadow-md);
  color: var(--surface);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.mobile-launch > span:first-child {
  display: grid;
  gap: 2px;
}

.mobile-launch small {
  opacity: 0.66;
  font-size: 8px;
}

.mobile-launch strong {
  font-size: 11px;
  font-weight: 650;
}

.mobile-launch-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--brand);
  color: white;
}

:global(.inspector-drawer .el-drawer__body) {
  padding: 0 14px 20px;
  background: var(--canvas);
}

@media (max-width: 1500px) {
  .train-page {
    padding-inline: 24px;
  }

  .workbench-layout {
    grid-template-columns: 152px minmax(660px, 1fr) 260px;
    gap: 16px;
  }

  .trainer-panel {
    grid-template-columns: minmax(360px, 1.25fr) minmax(300px, 0.8fr);
  }
}

@media (max-width: 1280px) {
  .trainer-panel {
    grid-template-columns: 1fr;
  }

  .trainer-context {
    display: none;
  }

  .workbench-layout {
    grid-template-columns: 156px minmax(0, 1fr);
  }

  .desktop-inspector {
    display: none;
  }

  .mobile-launch {
    display: grid;
  }
}

@media (max-width: 900px) {
  .train-page {
    padding: 24px 18px 96px;
  }

  .page-header {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
  }

  .page-title {
    grid-column: 1 / -1;
  }

  .density-switch {
    position: static;
    justify-self: start;
    transform: none;
  }

  .trainer-panel {
    grid-template-columns: 1fr;
  }

  .trainer-control {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .workbench-layout {
    grid-template-columns: 1fr;
  }

  .config-section,
  :deep(.asset-card) {
    scroll-margin-top: 68px;
  }

  .section-rail {
    position: sticky;
    z-index: 20;
    top: 0;
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    overflow-x: auto;
    padding: 7px;
    border-bottom: 1px solid var(--border-subtle);
    border-radius: 0;
    background: var(--surface-overlay);
  }

  .rail-heading {
    display: none;
  }

  .rail-item {
    width: auto;
    grid-template-columns: 22px auto;
    min-height: 38px;
    padding: 4px 8px 4px 5px;
  }

  .rail-copy strong {
    font-size: 12px;
  }
}

@media (max-width: 640px) {
  .train-page {
    width: 100vw;
    max-width: 100vw;
    padding: 18px 11px 116px;
  }

  .page-header {
    display: grid;
    gap: 14px;
  }

  .page-title h1 {
    font-size: 28px;
  }

  .title-line {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
  }

  .page-title > p {
    max-width: 36ch;
    font-size: 12px;
  }

  .page-actions {
    width: 100%;
  }

  .page-actions :deep(.el-button) {
    flex: 1;
  }

  .trainer-panel {
    min-width: 0;
    max-width: 100%;
    gap: 15px;
    margin-top: 18px;
    padding: 13px;
  }

  .workbench-layout {
    min-width: 0;
    max-width: 100%;
    margin-top: 14px;
  }

  .config-section {
    min-width: 0;
    max-width: 100%;
    border-radius: 14px;
  }

  .section-header {
    grid-template-columns: 36px minmax(0, 1fr);
    min-height: 72px;
    padding: 12px 13px;
  }

  .section-icon {
    width: 34px;
    height: 34px;
  }

  .section-header p {
    display: none;
  }

  .section-state {
    grid-column: 2;
    justify-self: start;
    margin-top: -6px;
  }

  .section-body {
    padding: 15px 13px;
  }

  .runtime-grid {
    grid-template-columns: 1fr;
  }

  .gpu-field {
    grid-column: auto;
  }

  .parameter-list {
    padding: 0;
  }

  .parameter-row {
    grid-template-columns: 1fr;
    gap: 12px;
    padding: 15px 2px;
  }

  .parameter-control {
    grid-template-columns: 1fr;
  }

  .reset-param {
    justify-self: start;
  }

  .mobile-launch {
    right: 11px;
    bottom: calc(76px + env(safe-area-inset-bottom));
    left: 11px;
    min-width: 0;
  }
}

/* Readability baseline: supporting information stays compact, never microscopic. */
.draft-state,
.trainer-control > label > small,
.trainer-option small,
.gpu-option small,
.rail-heading,
.section-state,
.form-field em,
.form-field > span > small,
.form-field > small,
.parameter-copy code,
.reset-param,
.mobile-launch small {
  font-size: 12px;
}

.trainer-control > label > span,
.context-item strong,
.rail-copy strong,
.section-header p,
.parameter-copy p {
  font-size: 13px;
}

.page-title > p,
.trainer-option strong,
.gpu-option strong,
.form-field strong,
.parameter-title strong,
.mobile-launch strong {
  font-size: 14px;
}

.context-item small,
.context-item.manifest strong {
  font-size: 12px;
}

.section-header h2 {
  font-size: 17px;
}
</style>
