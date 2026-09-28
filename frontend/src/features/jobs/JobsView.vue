<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, CopyDocument, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import type { JobRecord, JobState } from '@/api/types'
import JobConsole from '@/components/JobConsole.vue'
import JobStateBadge from '@/components/JobStateBadge.vue'
import { useJobsStore } from '@/stores/jobs'
import { useMetricsStore } from '@/stores/metrics'

import JobMetricsPanel from './metrics/JobMetricsPanel.vue'

type StateFilter = 'all' | JobState
type MonitorTab = 'metrics' | 'logs'

interface ArtifactItem {
  key: string
  label: string
  description: string
  path: string
}

interface EnvironmentItem {
  key: string
  value: string
  description: string
}

const STATE_LABELS: Record<JobState, string> = {
  created: '已创建',
  queued: '排队中',
  running: '运行中',
  succeeded: '成功',
  failed: '失败',
  terminating: '终止中',
  terminated: '已终止',
  canceled: '已取消',
}

const STATE_OPTIONS: JobState[] = [
  'running',
  'queued',
  'succeeded',
  'failed',
  'terminating',
  'terminated',
  'canceled',
  'created',
]

const TERMINAL_STATES = new Set<JobState>(['succeeded', 'failed', 'terminated', 'canceled'])
const TERMINATABLE_STATES = new Set<JobState>(['created', 'queued', 'running'])
const ARTIFACT_DEFINITIONS = [
  {
    key: 'draft',
    label: '训练草稿',
    description: '本次任务提交时的完整结构化配置',
  },
  {
    key: 'trainConfig',
    label: '训练配置',
    description: '实际传给训练器的参数配置',
  },
  {
    key: 'datasetConfig',
    label: '数据集配置',
    description: '本次训练使用的数据集与分桶设置',
  },
  {
    key: 'samplePrompts',
    label: '采样提示词',
    description: '训练期间生成预览图所用的提示词',
  },
  {
    key: 'command',
    label: '命令快照',
    description: '启动参数和运行目录的结构化快照',
  },
] as const
const KNOWN_ARTIFACT_KEYS = new Set<string>(ARTIFACT_DEFINITIONS.map((item) => item.key))
const ENVIRONMENT_DESCRIPTIONS: Record<string, string> = {
  CUDA_VISIBLE_DEVICES: '本次任务可见的 GPU 编号',
  ACCELERATE_DISABLE_RICH: 'Accelerate 富文本输出开关',
  PYTHONUNBUFFERED: 'Python 标准输出缓冲设置',
  USE_LIBUV: '多 GPU 进程通信兼容设置',
}
const ENVIRONMENT_ORDER = [
  'CUDA_VISIBLE_DEVICES',
  'ACCELERATE_DISABLE_RICH',
  'PYTHONUNBUFFERED',
  'USE_LIBUV',
]

const jobs = useJobsStore()
const metrics = useMetricsStore()
const route = useRoute()
const router = useRouter()
const searchQuery = ref('')
const stateFilter = ref<StateFilter>('all')
const monitorTab = ref<MonitorTab>('metrics')
const now = ref(Date.now())
const jobBrowserRef = ref<HTMLElement | null>(null)
const jobDetailRef = ref<HTMLElement | null>(null)

let listTimer: number | undefined
let clockTimer: number | undefined
let suppressNextRouteDetailFocus = false
let observedMetricJobId = ''
let disposed = false

const selected = computed(() => jobs.selectedJobFromList)
const canTerminate = computed(
  () => !!selected.value && TERMINATABLE_STATES.has(selected.value.state) && !jobs.terminating,
)

const stateCounts = computed(() => {
  const counts = new Map<JobState, number>()
  for (const job of jobs.jobs) counts.set(job.state, (counts.get(job.state) || 0) + 1)
  return counts
})

const filterOptions = computed(() => [
  { value: 'all' as StateFilter, label: '全部状态', count: jobs.jobs.length },
  ...STATE_OPTIONS.map((state) => ({
    value: state as StateFilter,
    label: STATE_LABELS[state],
    count: stateCounts.value.get(state) || 0,
  })),
])

const filteredJobs = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase()
  return jobs.jobs.filter((job) => {
    if (stateFilter.value !== 'all' && job.state !== stateFilter.value) return false
    if (!query) return true
    return [
      job.name,
      job.id,
      job.runId,
      job.trainerId,
      STATE_LABELS[job.state],
      job.state,
    ].some((value) => value?.toLocaleLowerCase().includes(query))
  })
})

const hasFilters = computed(() => stateFilter.value !== 'all' || searchQuery.value.trim().length > 0)
const resultSummary = computed(() => {
  if (!hasFilters.value) return `共 ${jobs.jobs.length} 个任务`
  return `找到 ${filteredJobs.value.length} 个，共 ${jobs.jobs.length} 个`
})

const artifactItems = computed<ArtifactItem[]>(() => {
  const artifacts = selected.value?.artifacts || {}
  const expected = ARTIFACT_DEFINITIONS.map((definition) => ({
    ...definition,
    path: artifacts[definition.key]?.trim() || '',
  }))
  const additional = Object.entries(artifacts)
    .filter(([key]) => !KNOWN_ARTIFACT_KEYS.has(key))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, path]) => ({
      key,
      label: key,
      description: '后端记录的附加运行产物',
      path: path?.trim() || '',
    }))
  return [...expected, ...additional]
})

const availableArtifactItems = computed(() => artifactItems.value.filter((item) => item.path))

const environmentItems = computed<EnvironmentItem[]>(() => {
  const entries = Object.entries(selected.value?.env || {})
  return entries
    .sort(([left], [right]) => {
      const leftIndex = ENVIRONMENT_ORDER.indexOf(left)
      const rightIndex = ENVIRONMENT_ORDER.indexOf(right)
      if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right)
      if (leftIndex === -1) return 1
      if (rightIndex === -1) return -1
      return leftIndex - rightIndex
    })
    .map(([key, value]) => ({
      key,
      value,
      description: ENVIRONMENT_DESCRIPTIONS[key] || '任务启动时记录的环境变量',
    }))
})

function quoteCommandArgument(argument: string): string {
  if (!argument) return '""'
  if (/^[\w@%+=:,./\\-]+$/u.test(argument)) return argument
  return `"${argument.replaceAll('"', '\\"')}"`
}

const commandText = computed(() =>
  (selected.value?.command || []).map(quoteCommandArgument).join(' '),
)
const commandPreview = computed(() =>
  (selected.value?.command || []).map(quoteCommandArgument).join(' \\\n  '),
)

const timeFormatter = new Intl.DateTimeFormat('zh-CN', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})
const monthDayFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})
const fullTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

function routeId(): string {
  const id = route.params.id
  return Array.isArray(id) ? id[0] : id || ''
}

function parseTime(value?: string): number | undefined {
  if (!value) return undefined
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? undefined : timestamp
}

function sameLocalDay(left: Date, right: Date) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  )
}

function formatTime(value?: string): string {
  const timestamp = parseTime(value)
  if (timestamp === undefined) return '—'
  const date = new Date(timestamp)
  const today = new Date(now.value)
  if (sameLocalDay(date, today)) return `今天 ${timeFormatter.format(date)}`

  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (sameLocalDay(date, yesterday)) return `昨天 ${timeFormatter.format(date)}`
  return monthDayFormatter.format(date)
}

function formatFullTime(value?: string): string {
  const timestamp = parseTime(value)
  return timestamp === undefined ? '时间未知' : fullTimeFormatter.format(new Date(timestamp))
}

function humanizeDuration(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (days > 0) return `${days} 天 ${hours} 小时`
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`
  if (minutes > 0) return `${minutes} 分 ${seconds.toString().padStart(2, '0')} 秒`
  return `${seconds} 秒`
}

function formatDuration(job: JobRecord): string {
  const waiting = job.state === 'created' || job.state === 'queued'
  const start = parseTime(waiting ? job.createdAt : job.startedAt || job.createdAt)
  if (start === undefined) return '时长未知'

  const terminal = TERMINAL_STATES.has(job.state)
  const end = parseTime(job.endedAt)
  if (terminal && end === undefined) return '时长未知'

  const duration = humanizeDuration((end ?? now.value) - start)
  if (waiting) return `已等待 ${duration}`
  if (job.state === 'running') return `已运行 ${duration}`
  if (job.state === 'terminating') return `终止中 · ${duration}`
  return `耗时 ${duration}`
}

function displayName(job: JobRecord) {
  return job.name?.trim() || job.trainerId || '未命名任务'
}

function clearFilters() {
  searchQuery.value = ''
  stateFilter.value = 'all'
}

async function copyText(value: string | undefined, label: string) {
  if (!value?.trim()) {
    ElMessage.warning(`${label}尚未记录`)
    return
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      textarea.remove()
      if (!copied) throw new Error('Clipboard API unavailable')
    }
    ElMessage.success(`已复制${label}`)
  } catch {
    ElMessage.error('复制失败，请检查浏览器的剪贴板权限')
  }
}

async function copyAllArtifacts() {
  if (!selected.value || availableArtifactItems.value.length === 0) {
    ElMessage.warning('当前任务没有可复制的运行产物')
    return
  }

  const lines = [
    `任务 ID：${selected.value.id}`,
    `Run ID：${selected.value.runId || '未记录'}`,
    '',
    ...artifactItems.value.map(
      (item) => `${item.label}（${item.key}）：${item.path || '未生成'}`,
    ),
  ]
  await copyText(lines.join('\n'), '全部产物信息')
}

function usesReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

async function focusDetailOnMobile(expectedJobId?: string) {
  if (!window.matchMedia('(max-width: 900px)').matches) return
  await nextTick()
  if (expectedJobId && selected.value?.id !== expectedJobId) return

  const detail = jobDetailRef.value
  if (!detail) return
  detail.focus({ preventScroll: true })
  detail.scrollIntoView({
    behavior: usesReducedMotion() ? 'auto' : 'smooth',
    block: 'start',
  })
}

async function returnToJobList() {
  if (routeId()) await router.push('/jobs')
  await nextTick()
  const browser = jobBrowserRef.value
  if (!browser) return
  browser.focus({ preventScroll: true })
  browser.scrollIntoView({
    behavior: usesReducedMotion() ? 'auto' : 'smooth',
    block: 'start',
  })
}

async function selectJob(job: JobRecord) {
  if (routeId() === job.id) {
    if (jobs.selectedJobId !== job.id) await jobs.selectJob(job.id)
    await focusDetailOnMobile(job.id)
    return
  }
  await router.push({ name: 'jobs', params: { id: job.id } })
}

function isTerminal(state: JobState) {
  return TERMINAL_STATES.has(state)
}

async function confirmTermination() {
  const job = selected.value
  if (!job || !canTerminate.value) return

  try {
    const queueNotice =
      job.state === 'created' || job.state === 'queued'
        ? '该任务尚在排队，终止请求会立即提交，但状态仍需以后端确认为准。'
        : '训练进程及其子进程将被停止。'
    await ElMessageBox.confirm(
      `将停止“${displayName(job)}”。${queueNotice}这个操作无法撤销。`,
      '确认终止任务？',
      {
        confirmButtonText: '终止任务',
        cancelButtonText: '继续运行',
        type: 'warning',
        closeOnClickModal: false,
      },
    )
  } catch {
    return
  }

  await jobs.terminateSelectedJob()
  if (!jobs.error) ElMessage.success('已发送终止请求')
}

onMounted(async () => {
  const id = routeId()
  // Pre-seed the selection so loadJobs() does not connect to a different job
  // before the deep link is honoured.
  if (id) jobs.selectedJobId = id
  await jobs.loadJobs()
  if (disposed) return
  if (id && routeId() === id) {
    await jobs.selectJob(id)
    if (disposed) return
    await focusDetailOnMobile(id)
  } else if (!routeId() && jobs.selectedJobId && !window.matchMedia('(max-width: 900px)').matches) {
    suppressNextRouteDetailFocus = true
    await router.replace({ name: 'jobs', params: { id: jobs.selectedJobId } })
  }
  if (disposed) return

  // The list is polled only for summary changes; the selected job keeps using SSE.
  listTimer = window.setInterval(() => void jobs.loadJobs({ silent: true }), 5000)
  clockTimer = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onBeforeUnmount(() => {
  disposed = true
  if (listTimer !== undefined) window.clearInterval(listTimer)
  if (clockTimer !== undefined) window.clearInterval(clockTimer)
  jobs.disconnect()
  void metrics.observeJob('')
})

watch(
  () => routeId(),
  async (id) => {
    const shouldFocusDetail = !suppressNextRouteDetailFocus
    suppressNextRouteDetailFocus = false
    if (!id) {
      if (window.matchMedia('(max-width: 900px)').matches) {
        observedMetricJobId = ''
        void metrics.observeJob('')
      }
      return
    }
    if (id !== jobs.selectedJobId) await jobs.selectJob(id)
    if (disposed || routeId() !== id) return
    const job = selected.value
    if (job?.id === id && metrics.jobId !== id) {
      observedMetricJobId = id
      monitorTab.value = 'metrics'
      void metrics.observeJob(id, { terminal: isTerminal(job.state) })
    }
    if (shouldFocusDetail) await focusDetailOnMobile(id)
  },
)

watch(
  selected,
  (job) => {
    if (!routeId() && window.matchMedia('(max-width: 900px)').matches) {
      observedMetricJobId = ''
      void metrics.observeJob('')
      return
    }
    const jobId = job?.id || ''
    if (jobId !== observedMetricJobId) {
      observedMetricJobId = jobId
      monitorTab.value = 'metrics'
    }
    void metrics.observeJob(jobId, { terminal: job ? isTerminal(job.state) : false })
  },
  { immediate: true },
)
</script>

<template>
  <section class="jobs-page" aria-labelledby="jobs-title">
    <header class="jobs-toolbar">
      <div class="page-heading">
        <h1 id="jobs-title">任务中心</h1>
      </div>
      <el-button text :icon="Refresh" :loading="jobs.loading" @click="jobs.loadJobs()">刷新任务</el-button>
    </header>

    <el-alert
      v-if="jobs.error"
      class="jobs-alert"
      type="error"
      :title="jobs.error"
      show-icon
      :closable="false"
    />
    <el-alert
      v-else-if="jobs.listRefreshError"
      class="jobs-alert"
      type="warning"
      :title="jobs.listRefreshError"
      show-icon
      :closable="false"
    />

    <div class="jobs-layout" :class="{ 'route-detail-open': !!routeId() }">
      <section
        ref="jobBrowserRef"
        class="job-browser"
        aria-label="任务列表"
        tabindex="-1"
      >
        <div class="filter-panel">
          <el-input
            v-model="searchQuery"
            :prefix-icon="Search"
            placeholder="搜索名称、训练器或 ID"
            aria-label="搜索任务"
            clearable
          />
          <el-select v-model="stateFilter" aria-label="按任务状态筛选">
            <el-option
              v-for="option in filterOptions"
              :key="option.value"
              :label="`${option.label} · ${option.count}`"
              :value="option.value"
            />
          </el-select>
          <div class="filter-summary" aria-live="polite">
            <span>{{ resultSummary }}</span>
            <button v-if="hasFilters" type="button" @click="clearFilters">重置筛选</button>
          </div>
        </div>

        <div class="job-list">
          <div v-if="jobs.loading && jobs.jobs.length === 0" class="skeleton-list" aria-label="正在加载任务">
            <div v-for="index in 4" :key="index" class="skeleton-card">
              <el-skeleton :rows="2" animated />
            </div>
          </div>

          <el-empty
            v-else-if="jobs.jobs.length === 0"
            class="list-empty"
            :image-size="72"
            description="还没有训练任务"
          >
            <el-button :loading="jobs.loading" @click="jobs.loadJobs()">重新检查</el-button>
          </el-empty>

          <el-empty
            v-else-if="filteredJobs.length === 0"
            class="list-empty"
            :image-size="64"
            description="没有匹配的任务"
          >
            <el-button @click="clearFilters">清除筛选</el-button>
          </el-empty>

          <div v-else class="job-card-list" role="list">
            <article v-for="job in filteredJobs" :key="job.id" role="listitem">
              <button
                class="job-card"
                :class="{ selected: job.id === jobs.selectedJobId }"
                type="button"
                :aria-current="job.id === jobs.selectedJobId ? 'true' : undefined"
                @click="selectJob(job)"
              >
                <span class="job-card-heading">
                  <span class="job-title-block">
                    <strong>{{ displayName(job) }}</strong>
                    <span class="job-id">{{ job.id }}</span>
                  </span>
                  <JobStateBadge :state="job.state" />
                </span>

                <span class="job-card-meta">
                  <span>{{ job.trainerId }}</span>
                  <time :datetime="job.createdAt" :title="formatFullTime(job.createdAt)">
                    {{ formatTime(job.createdAt) }}
                  </time>
                </span>

                <span class="job-card-footer">
                  <span class="duration">{{ formatDuration(job) }}</span>
                  <span v-if="job.exitCode !== undefined" class="exit-code">
                    退出码 {{ job.exitCode }}
                  </span>
                </span>
              </button>
            </article>
          </div>
        </div>
      </section>

      <aside
        ref="jobDetailRef"
        class="job-detail"
        aria-label="任务详情"
        tabindex="-1"
      >
        <template v-if="selected">
          <el-button
            class="mobile-back"
            :icon="ArrowLeft"
            text
            @click="returnToJobList"
          >
            返回任务列表
          </el-button>

          <header class="detail-header">
            <div class="detail-title">
              <div class="detail-name-row">
                <h2>{{ displayName(selected) }}</h2>
                <JobStateBadge :state="selected.state" />
              </div>
              <div class="detail-id-row">
                <span class="detail-id">任务 ID · {{ selected.id }}</span>
                <el-button
                  class="inline-copy"
                  link
                  :icon="CopyDocument"
                  aria-label="复制任务 ID"
                  @click="copyText(selected.id, '任务 ID')"
                >
                  复制
                </el-button>
              </div>
            </div>
            <el-button
              v-if="!isTerminal(selected.state)"
              type="danger"
              plain
              :disabled="!canTerminate"
              :loading="jobs.terminating"
              @click="confirmTermination"
            >
              {{ selected.state === 'terminating' ? '正在终止' : '终止任务' }}
            </el-button>
          </header>

          <el-alert
            v-if="selected.errorMessage"
            class="detail-error"
            type="error"
            title="任务运行失败"
            :description="selected.errorMessage"
            show-icon
            :closable="false"
          />

          <div class="detail-workspace">
            <section class="log-section monitor-section" aria-labelledby="job-monitor-heading">
              <div class="section-heading log-heading monitor-heading">
                <div>
                  <h3 id="job-monitor-heading">{{ monitorTab === 'metrics' ? '训练指标' : '运行日志' }}</h3>
                  <p v-if="monitorTab === 'logs' && jobs.streamStatus === 'connecting'">正在建立实时日志连接</p>
                  <p v-else-if="monitorTab === 'logs' && jobs.streamStatus === 'live'">训练输出会持续追加到这里</p>
                  <p v-else-if="monitorTab === 'logs' && jobs.streamStatus === 'disconnected'">实时连接已中断，当前显示日志快照</p>
                  <p v-else-if="monitorTab === 'logs'">任务已结束，显示最终日志</p>
                </div>
                <div class="monitor-tabs" role="tablist" aria-label="训练监控内容">
                  <button
                    type="button"
                    role="tab"
                    :class="{ active: monitorTab === 'metrics' }"
                    :aria-selected="monitorTab === 'metrics'"
                    @click="monitorTab = 'metrics'"
                  >
                    指标
                    <small v-if="metrics.tags.length">{{ metrics.tags.length }}</small>
                  </button>
                  <button
                    type="button"
                    role="tab"
                    :class="{ active: monitorTab === 'logs' }"
                    :aria-selected="monitorTab === 'logs'"
                    @click="monitorTab = 'logs'"
                  >
                    日志
                  </button>
                </div>
              </div>
              <div class="monitor-content">
                <JobMetricsPanel
                  v-show="monitorTab === 'metrics'"
                  :key="`metrics:${selected.id}`"
                  :trainer-id="selected.trainerId"
                  @show-log="monitorTab = 'logs'"
                />
                <div v-show="monitorTab === 'logs'" class="console-shell">
                  <JobConsole
                    :key="selected.id"
                    :lines="jobs.logLines"
                    :streaming="jobs.streaming"
                    :connection-status="jobs.streamStatus"
                    :stream-error="jobs.streamError"
                    :last-event-at="jobs.lastEventAt"
                    @reconnect="jobs.reconnectSelectedJob"
                  />
                </div>
              </div>
            </section>

            <div class="job-overview" aria-label="任务运行信息">
          <section class="summary-grid" aria-label="任务摘要">
            <div class="summary-item">
              <span>训练器</span>
              <strong>{{ selected.trainerId }}</strong>
            </div>
            <div class="summary-item">
              <span>创建时间</span>
              <time :datetime="selected.createdAt" :title="formatFullTime(selected.createdAt)">
                {{ formatTime(selected.createdAt) }}
              </time>
            </div>
            <div class="summary-item">
              <span>运行时长</span>
              <strong>{{ formatDuration(selected) }}</strong>
            </div>
            <div class="summary-item">
              <span>退出码</span>
              <strong>{{ selected.exitCode ?? '—' }}</strong>
            </div>
          </section>

          <section class="detail-section">
            <div class="section-heading">
              <div>
                <h3>运行信息</h3>
              </div>
            </div>
            <dl class="detail-list">
              <dt>Run ID</dt>
              <dd class="copy-field">
                <span class="monospace" :title="selected.runId || '未记录'">{{ selected.runId || '—' }}</span>
                <el-button
                  class="inline-copy"
                  link
                  :icon="CopyDocument"
                  :disabled="!selected.runId"
                  aria-label="复制 Run ID"
                  @click="copyText(selected.runId, 'Run ID')"
                >
                  复制
                </el-button>
              </dd>
              <dt>开始时间</dt>
              <dd>
                <time v-if="selected.startedAt" :datetime="selected.startedAt" :title="formatFullTime(selected.startedAt)">
                  {{ formatTime(selected.startedAt) }}
                </time>
                <span v-else>尚未开始</span>
              </dd>
              <dt>结束时间</dt>
              <dd>
                <time v-if="selected.endedAt" :datetime="selected.endedAt" :title="formatFullTime(selected.endedAt)">
                  {{ formatTime(selected.endedAt) }}
                </time>
                <span v-else>{{ isTerminal(selected.state) ? '未记录' : '—' }}</span>
              </dd>
              <dt>日志文件</dt>
              <dd class="copy-field">
                <span class="monospace" :title="selected.logPath || '未记录'">{{ selected.logPath || '—' }}</span>
                <el-button
                  class="inline-copy"
                  link
                  :icon="CopyDocument"
                  :disabled="!selected.logPath"
                  aria-label="复制日志文件路径"
                  @click="copyText(selected.logPath, '日志路径')"
                >
                  复制
                </el-button>
              </dd>
            </dl>
          </section>

          <details class="detail-section artifacts-section">
            <summary>
              <span class="diagnostic-summary">
                <strong>运行产物</strong>
              </span>
              <el-tag size="small" effect="plain" type="info">
                {{ availableArtifactItems.length }}/{{ artifactItems.length }} 已生成
              </el-tag>
            </summary>

            <div class="artifact-panel">
              <div class="artifact-toolbar">
                <span>配置、提示词与启动快照</span>
              <el-button
                size="small"
                plain
                :icon="CopyDocument"
                :disabled="availableArtifactItems.length === 0"
                @click="copyAllArtifacts"
              >
                复制全部
              </el-button>
              </div>

            <div class="artifact-list" role="list">
              <article
                v-for="artifact in artifactItems"
                :key="artifact.key"
                class="artifact-item"
                :class="{ missing: !artifact.path }"
                role="listitem"
              >
                <div class="artifact-content">
                  <div class="artifact-title-row">
                    <strong>{{ artifact.label }}</strong>
                    <span class="artifact-key">{{ artifact.key }}</span>
                    <el-tag
                      size="small"
                      effect="plain"
                      :type="artifact.path ? 'success' : 'info'"
                    >
                      {{ artifact.path ? '已生成' : '未生成' }}
                    </el-tag>
                  </div>
                  <p>{{ artifact.description }}</p>
                  <code :title="artifact.path || undefined">
                    {{ artifact.path || '此任务没有生成该产物' }}
                  </code>
                </div>
                <el-button
                  class="artifact-copy"
                  size="small"
                  plain
                  :icon="CopyDocument"
                  :disabled="!artifact.path"
                  :aria-label="`复制${artifact.label}路径`"
                  @click="copyText(artifact.path, `${artifact.label}路径`)"
                >
                  复制路径
                </el-button>
              </article>
            </div>
            </div>
          </details>

          <details v-if="selected.command?.length" class="command-section">
            <summary>
              <span>启动命令</span>
              <small>{{ selected.command.length }} 个参数</small>
            </summary>
            <div class="command-toolbar">
              <span>已按参数边界补充必要引号</span>
              <el-button
                size="small"
                plain
                :icon="CopyDocument"
                @click="copyText(commandText, '启动命令')"
              >
                复制命令
              </el-button>
            </div>
            <pre>{{ commandPreview }}</pre>
          </details>

          <details class="diagnostic-section">
            <summary>
              <span class="diagnostic-summary">
                <strong>运行环境诊断</strong>
              </span>
              <el-tag
                size="small"
                effect="plain"
                :type="environmentItems.length ? 'primary' : 'info'"
              >
                {{ environmentItems.length ? `${environmentItems.length} 项` : '未记录' }}
              </el-tag>
            </summary>

            <div v-if="environmentItems.length" class="environment-list">
              <div v-for="item in environmentItems" :key="item.key" class="environment-item">
                <div>
                  <code>{{ item.key }}</code>
                  <p>{{ item.description }}</p>
                </div>
                <strong :title="item.value">{{ item.value || '空字符串' }}</strong>
              </div>
            </div>
            <div v-else class="environment-empty">
              当前任务没有记录公开的运行环境变量。
            </div>
          </details>

            </div>
          </div>
        </template>

        <el-empty v-else class="detail-empty" :image-size="88" description="选择一个任务查看详情" />
      </aside>
    </div>
  </section>
</template>

<style scoped>
.jobs-page {
  width: 100%;
  max-width: var(--page-max);
  min-height: 100dvh;
  margin: 0 auto;
  background: var(--canvas);
  color: var(--text);
}

.jobs-toolbar {
  position: sticky;
  top: 0;
  z-index: 20;
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 17px clamp(18px, 2.4vw, 34px);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-overlay);
}

.page-heading {
  min-width: 0;
}

.page-heading h1 {
  margin: 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: var(--font-page-title);
  line-height: 1.2;
  font-weight: 560;
  letter-spacing: 0;
}

.page-heading p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.jobs-alert {
  margin: 14px clamp(18px, 2.4vw, 34px) 0;
}

.jobs-layout {
  width: 100%;
  max-width: var(--page-max);
  min-height: calc(100dvh - 92px);
  height: calc(100dvh - 92px);
  display: grid;
  grid-template-columns: minmax(270px, 320px) minmax(0, 1fr);
  margin: 0 auto;
}

.job-browser,
.job-detail {
  min-width: 0;
  min-height: 0;
  scroll-margin-top: 104px;
}

.job-browser:focus,
.job-detail:focus {
  outline: none;
}

.job-browser:focus-visible,
.job-detail:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--brand) 24%, transparent);
  outline-offset: -3px;
}

.job-browser {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface) 82%, transparent);
}

.filter-panel {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 128px;
  gap: 10px;
  padding: 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface);
}

.filter-summary {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 20px;
  color: var(--text-muted);
  font-size: 12px;
}

.filter-summary button {
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--brand-strong);
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}

.filter-summary button:hover,
.filter-summary button:focus-visible {
  color: var(--brand);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.job-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
  scrollbar-color: var(--border-strong) transparent;
}

.job-card-list {
  display: grid;
  gap: 7px;
}

.job-card {
  width: 100%;
  display: grid;
  gap: 11px;
  padding: 14px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 150ms ease,
    background-color 150ms ease,
    box-shadow 150ms ease,
    transform 150ms ease;
}

.job-card:hover {
  border-color: var(--border-subtle);
  background: var(--surface-raised);
  box-shadow: var(--shadow-xs);
}

.job-card:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--brand) 22%, transparent);
  outline-offset: 1px;
}

.job-card.selected {
  border-color: color-mix(in srgb, var(--brand) 26%, var(--border-subtle));
  background: var(--brand-softer);
  box-shadow: inset 3px 0 var(--brand), var(--shadow-xs);
}

.job-card-heading,
.job-card-meta,
.job-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.job-card-heading {
  align-items: flex-start;
}

.job-title-block {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.job-title-block strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-id,
.detail-id,
.monospace {
  font-family: var(--font-mono);
}

.job-id {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-card-meta {
  color: var(--text-muted);
  font-size: 12px;
}

.job-card-meta > span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-card-meta time {
  flex: 0 0 auto;
}

.job-card-footer {
  padding-top: 8px;
  border-top: 1px solid color-mix(in srgb, var(--border-subtle) 70%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
}

.duration {
  font-weight: 600;
}

.exit-code {
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.skeleton-list {
  display: grid;
  gap: 8px;
}

.skeleton-card {
  padding: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.list-empty,
.detail-empty {
  height: 100%;
  min-height: 260px;
}

.list-empty p,
.detail-empty p {
  max-width: 270px;
  margin: -4px auto 12px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.55;
  text-align: center;
}

.job-detail {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 18px clamp(18px, 2vw, 28px) 20px;
  background: color-mix(in srgb, var(--surface) 70%, transparent);
}

.mobile-back.el-button {
  display: none;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 14px;
}

.detail-title {
  min-width: 0;
}

.detail-name-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.detail-name-row h2 {
  min-width: 0;
  overflow: hidden;
  margin: 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: clamp(22px, 2vw, 30px);
  line-height: 1.25;
  font-weight: 560;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-id {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-id-row {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 7px;
}

.inline-copy.el-button {
  flex: 0 0 auto;
  min-height: 24px;
  padding: 2px 4px;
  font-size: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.summary-item {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 5px;
  padding: 10px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  box-shadow: var(--shadow-xs);
}

.summary-item span {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0;
}

.summary-item strong,
.summary-item time {
  min-width: 0;
  overflow: hidden;
  color: var(--text-strong);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-error {
  flex: 0 0 auto;
  margin-bottom: 12px;
}

.detail-workspace {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-areas: 'overview log';
  grid-template-columns: minmax(260px, 310px) minmax(0, 1fr);
  gap: 16px;
}

.job-overview {
  grid-area: overview;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-color: var(--border-strong) transparent;
}

.detail-section,
.command-section,
.diagnostic-section,
.log-section {
  margin-top: 10px;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-heading h3 {
  margin: 0;
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 680;
}

.section-heading p {
  margin: 3px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.detail-list {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 9px 12px;
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
}

.detail-list dt {
  color: var(--text-muted);
}

.detail-list dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--text);
}

.copy-field {
  display: flex;
  align-items: center;
  gap: 8px;
}

.copy-field > span {
  min-width: 0;
  flex: 1;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifacts-section {
  padding: 0;
  overflow: hidden;
  box-shadow: none;
}

.artifact-panel {
  border-top: 1px solid var(--border-subtle);
}

.artifact-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 10px;
  color: var(--text-muted);
  font-size: 12px;
}

.artifact-list {
  display: grid;
  gap: 7px;
  padding: 0 10px 10px;
}

.artifact-item {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: 9px;
  padding: 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.artifact-item.missing {
  background: color-mix(in srgb, var(--surface-sunken) 58%, transparent);
}

.artifact-content {
  min-width: 0;
}

.artifact-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
}

.artifact-title-row strong {
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 680;
}

.artifact-key {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.artifact-title-row :deep(.el-tag),
.diagnostic-section :deep(.el-tag) {
  height: 26px;
  border-radius: 6px;
  font-size: 12px;
}

.artifact-title-row :deep(.el-tag) {
  margin-left: 2px;
}

.artifact-content p {
  margin: 4px 0 7px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.45;
}

.artifact-content code {
  display: block;
  overflow: hidden;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-item.missing .artifact-content code {
  color: var(--text-muted);
  font-family: inherit;
}

.artifact-copy.el-button {
  width: 100%;
}

.command-section {
  padding: 0;
  overflow: hidden;
}

.artifacts-section summary,
.command-section summary,
.diagnostic-section summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  list-style: none;
}

.artifacts-section summary::-webkit-details-marker,
.command-section summary::-webkit-details-marker,
.diagnostic-section summary::-webkit-details-marker {
  display: none;
}

.artifacts-section summary::after,
.command-section summary::after,
.diagnostic-section summary::after {
  flex: 0 0 auto;
  color: var(--text-muted);
  font-size: 16px;
  content: '⌄';
  transition: transform 160ms ease;
}

.artifacts-section[open] summary::after,
.command-section[open] summary::after,
.diagnostic-section[open] summary::after {
  transform: rotate(180deg);
}

.command-section summary small {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
}

.command-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 18px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
  color: var(--text-muted);
  font-size: 12px;
}

.command-section pre {
  max-height: 280px;
  overflow: auto;
  margin: 0;
  padding: 16px 18px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.diagnostic-section {
  padding: 0;
  overflow: hidden;
  box-shadow: none;
}

.diagnostic-section summary {
  padding: 14px 18px;
}

.diagnostic-summary {
  min-width: 0;
  display: grid;
  gap: 3px;
  margin-right: auto;
}

.diagnostic-summary strong {
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 650;
}

.diagnostic-summary small {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
}

.artifacts-section summary :deep(.el-tag),
.diagnostic-section summary :deep(.el-tag) {
  flex: 0 0 auto;
  margin-left: 12px;
}

.environment-list {
  border-top: 1px solid var(--border-subtle);
}

.environment-item {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(120px, auto);
  align-items: center;
  gap: 18px;
  padding: 12px 18px;
  background: var(--surface-sunken);
}

.environment-item + .environment-item {
  border-top: 1px solid var(--border-subtle);
}

.environment-item > div {
  min-width: 0;
}

.environment-item code {
  color: var(--text-strong);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 650;
}

.environment-item p {
  margin: 3px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.environment-item > strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.environment-empty {
  padding: 16px 18px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
  color: var(--text-muted);
  font-size: 12px;
}

.log-section {
  grid-area: log;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-top: 0;
  padding: 0;
  overflow: hidden;
  background: var(--surface);
}

.log-heading {
  flex: 0 0 auto;
  align-items: center;
  min-height: 68px;
  margin: 0;
  padding: 11px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.log-heading p {
  margin-top: 2px;
}

.monitor-heading {
  gap: 12px;
}

.monitor-heading > div:first-child {
  min-width: 0;
}

.monitor-tabs {
  flex: 0 0 auto;
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 0;
  border-radius: 9px;
  background: var(--surface-sunken);
}

.monitor-tabs button {
  min-width: 58px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 6px 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

.monitor-tabs button.active {
  background: var(--surface);
  color: var(--text-strong);
  box-shadow: 0 1px 3px color-mix(in srgb, var(--text-strong) 9%, transparent);
}

.monitor-tabs button:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 1px;
}

.monitor-tabs small {
  min-width: 17px;
  padding: 1px 4px;
  border-radius: 999px;
  background: var(--brand-softer);
  color: var(--brand-strong);
  font-size: 12px;
  line-height: 1.35;
}

.monitor-content {
  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.console-shell {
  min-height: 320px;
  height: 100%;
  flex: 1;
  box-sizing: border-box;
  padding: 12px;
}

@media (max-width: 1180px) {
  .jobs-layout {
    grid-template-columns: minmax(250px, 290px) minmax(0, 1fr);
  }

  .detail-workspace {
    grid-template-columns: minmax(235px, 275px) minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .jobs-layout {
    height: auto;
    min-height: 0;
    grid-template-columns: minmax(0, 1fr);
  }

  .job-browser {
    max-height: 510px;
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .jobs-layout.route-detail-open .job-browser,
  .jobs-layout:not(.route-detail-open) .job-detail {
    display: none;
  }

  .job-list {
    min-height: 260px;
  }

  .job-detail {
    overflow: visible;
    padding-bottom: 34px;
  }

  .detail-workspace {
    display: grid;
    grid-template-areas:
      'log'
      'overview';
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }

  .job-overview {
    overflow: visible;
    padding-right: 0;
  }

  .log-section {
    height: min(68dvh, 720px);
    min-height: 520px;
  }

  .mobile-back.el-button {
    display: inline-flex;
    margin-bottom: 18px;
  }
}

@media (max-width: 640px) {
  .jobs-toolbar {
    position: static;
    min-height: 0;
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
    padding: 15px 16px;
  }

  .jobs-toolbar > :deep(.el-button) {
    align-self: flex-start;
  }

  .page-heading p {
    display: none;
  }

  .jobs-alert {
    margin: 10px 12px 0;
  }

  .filter-panel {
    grid-template-columns: minmax(0, 1fr);
    padding: 12px;
  }

  .filter-summary {
    grid-column: auto;
  }

  .job-list {
    padding: 7px;
  }

  .job-card {
    padding: 12px;
  }

  .job-detail {
    width: 100vw;
    max-width: 100vw;
    box-sizing: border-box;
    overflow-x: hidden;
    scroll-margin-top: 12px;
    padding: 20px 14px 32px;
  }

  .detail-workspace,
  .log-section,
  .monitor-content {
    width: 100%;
    max-width: 100%;
    min-width: 0;
  }

  .mobile-back.el-button {
    width: auto;
    margin-bottom: 14px;
  }

  .detail-header {
    align-items: stretch;
    flex-direction: column;
    gap: 14px;
  }

  .detail-header > :deep(.el-button) {
    width: 100%;
  }

  .detail-name-row h2 {
    white-space: normal;
  }

  .summary-grid {
    gap: 8px;
  }

  .summary-item {
    padding: 11px;
  }

  .detail-section,
  .log-section {
    padding: 14px;
    border-radius: var(--radius-md);
  }

  .log-section {
    padding: 0;
  }

  .monitor-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .monitor-tabs {
    align-self: flex-start;
  }

  .artifacts-section {
    padding: 0;
  }

  .detail-list {
    grid-template-columns: 82px minmax(0, 1fr);
    gap: 9px 12px;
  }

  .artifact-item {
    grid-template-columns: minmax(0, 1fr);
    gap: 11px;
    padding: 12px;
  }

  .artifact-copy.el-button {
    width: 100%;
  }

  .command-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .command-toolbar :deep(.el-button) {
    width: 100%;
  }

  .diagnostic-section summary {
    align-items: flex-start;
  }

  .diagnostic-summary small {
    display: none;
  }

  .environment-item {
    grid-template-columns: minmax(0, 1fr);
    gap: 7px;
  }

  .environment-item > strong {
    text-align: left;
  }

  .console-shell {
    min-height: 380px;
    padding: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .job-card,
  .command-section summary::after,
  .diagnostic-section summary::after {
    transition: none;
  }

  .job-card:hover {
    transform: none;
  }
}

.job-id,
.summary-item span,
.command-section summary small,
.artifact-key {
  font-size: 12px;
}

.filter-summary,
.job-card-meta,
.job-card-footer,
.detail-id,
.section-heading p,
.command-section pre,
.artifact-title-row strong {
  font-size: 13px;
}

.page-heading p,
.job-title,
.summary-item strong,
.summary-item time,
.detail-list,
.command-section summary {
  font-size: 14px;
}

.section-heading h3 {
  font-size: 16px;
}

/* Quiet workspace treatment: surfaces separate regions, borders do not. */
.jobs-toolbar {
  position: static;
  width: min(100%, var(--page-max));
  min-height: 0;
  margin: 0 auto;
  padding: 48px clamp(22px, 3vw, 44px) 24px;
  border: 0;
  background: transparent;
}

.page-heading h1 {
  font-size: var(--font-page-title);
  font-weight: 560;
  letter-spacing: 0;
}

.jobs-layout {
  max-width: var(--page-max);
  height: calc(100dvh - 108px);
  min-height: 620px;
  padding: 0 clamp(22px, 3vw, 44px) 32px;
}

.job-browser {
  border: 0;
  border-radius: 8px;
  background: var(--surface-nav);
}

.filter-panel {
  padding: 14px;
  border: 0;
  background: transparent;
}

.job-card,
.job-card:hover,
.job-card.selected {
  border-color: transparent;
  box-shadow: none;
  transform: none;
}

.job-card:hover,
.job-card.selected {
  background: var(--surface-hover);
}

.skeleton-card {
  border: 0;
  background: var(--surface-sunken);
}

.job-detail {
  padding: 8px 0 24px clamp(24px, 3vw, 42px);
  background: transparent;
}

.summary-grid {
  gap: 0 20px;
  border-top: 1px solid var(--border-subtle);
}

.summary-item {
  padding: 12px 0;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.job-overview > .detail-section,
.job-overview > .command-section,
.job-overview > .diagnostic-section {
  margin-top: 24px;
  padding: 18px 0 0;
  border: 0;
  border-top: 1px solid var(--border-subtle);
  border-radius: 0;
  background: transparent;
}

.job-overview > details > summary {
  padding: 0 0 14px;
}

.artifact-item {
  padding: 12px 0;
  border: 0;
  border-top: 1px solid var(--border-subtle);
  border-radius: 0;
  background: transparent;
}

.artifact-item.missing {
  background: transparent;
}

.log-section {
  border: 0;
  background: var(--surface-sunken);
}

.monitor-tabs {
  border: 0;
}

@media (max-width: 900px) {
  .jobs-layout {
    height: auto;
    min-height: 0;
  }

  .job-detail {
    padding: 24px clamp(18px, 3vw, 32px) 38px;
  }
}

@media (max-width: 640px) {
  .jobs-toolbar {
    padding: 24px 16px 14px;
  }

  .jobs-layout {
    padding: 0 0 86px;
  }

  .job-browser {
    border-radius: 0;
  }

  .job-detail {
    padding: 18px 14px 96px;
  }
}
</style>
